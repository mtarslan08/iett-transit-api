from datetime import UTC, datetime, timedelta, timezone
import asyncio
import json
import time
import xml.etree.ElementTree as ET
import httpx
from zeep import Client

from .config import settings
from .models import LiveSnapshot, Vehicle


class IettProvider:
    """İETT cevabını uygulamanın sabit veri modeline dönüştürür."""

    def __init__(self) -> None:
        self._cached_snapshot: LiveSnapshot | None = None
        self._cache_expires_at = 0.0
        self._refresh_lock = asyncio.Lock()
        self._last_attempt_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_raw_count = 0
        self._last_stale_count = 0
        self._last_error: str | None = None

    async def fetch(self) -> LiveSnapshot:
        now = time.monotonic()
        if self._cached_snapshot and now < self._cache_expires_at:
            return self._cached_snapshot

        async with self._refresh_lock:
            now = time.monotonic()
            if self._cached_snapshot and now < self._cache_expires_at:
                return self._cached_snapshot
            self._last_attempt_at = datetime.now(UTC)
            try:
                snapshot = await self._fetch_uncached()
            except (httpx.HTTPError, ValueError, TypeError):
                self._last_error = "İETT canlı filosu alınamadı"
                if self._cached_snapshot:
                    return self._cached_snapshot
                return LiveSnapshot(
                    fetched_at=datetime.now(UTC), source="unavailable", vehicles=[]
                )
            self._cached_snapshot = snapshot
            self._last_success_at = snapshot.fetched_at
            self._last_error = None
            self._cache_expires_at = time.monotonic() + settings.live_cache_seconds
            return snapshot

    async def fetch_line(self, line_code: str) -> LiveSnapshot | None:
        """İETTNext'in hat bazlı canlı akışını kullanır; hat bilgisi burada doğrulanmıştır."""
        if not settings.iett_next_api_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.iett_request_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.iett_next_api_url.rstrip('/')}/line-vehicles",
                    json={"line": line_code.strip().upper()},
                )
                response.raise_for_status()
                payload = response.json()
            vehicles = []
            for row in payload.get("vehicles", []):
                if row.get("lat") is None or row.get("lon") is None:
                    continue
                vehicles.append(Vehicle(
                    id=str(row.get("vehicleDoorCode", "unknown")),
                    line=line_code.strip().upper(),
                    door_number=row.get("vehicleDoorCode"),
                    latitude=float(row["lat"]), longitude=float(row["lon"]),
                    bearing=None, recorded_at=datetime.now(UTC),
                ))
            return LiveSnapshot(fetched_at=datetime.now(UTC), source=f"{settings.iett_next_api_url}/line-vehicles", vehicles=vehicles)
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return None

    async def _fetch_uncached(self) -> LiveSnapshot:
        if settings.iett_wsdl_url:
            rows = await asyncio.to_thread(self._fetch_soap_rows)
            return self._snapshot(rows, settings.iett_wsdl_url)
        if not settings.iett_live_url:
            return LiveSnapshot(fetched_at=datetime.now(UTC), source="not-configured", vehicles=[])

        async with httpx.AsyncClient(timeout=settings.iett_request_timeout_seconds) as client:
            response = await client.get(settings.iett_live_url)
            response.raise_for_status()
            payload = response.json()

        # Endpoint formatı doğrulanınca bu normalize edici alan eşleştirmesi genişletilecek.
        rows = payload.get("features", payload if isinstance(payload, list) else [])
        return self._snapshot(rows, settings.iett_live_url)

    def _fetch_soap_rows(self) -> list[dict]:
        try:
            client = Client(wsdl=settings.iett_wsdl_url)
            payload = client.service.GetFiloAracKonum_json()
            return json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            # WSDL'deki bozuk AuthHeader tanımını atlayıp ASMX metodunu doğrudan çağır.
            endpoint = settings.iett_wsdl_url.split("?", 1)[0]
            envelope = '''<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="http://tempuri.org/">
  <SOAP-ENV:Body><ns1:GetFiloAracKonum_json /></SOAP-ENV:Body>
</SOAP-ENV:Envelope>'''
            response = httpx.post(endpoint, content=envelope, headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '"http://tempuri.org/GetFiloAracKonum_json"',
            }, timeout=settings.iett_request_timeout_seconds)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            result = next((node.text for node in root.iter() if node.tag.endswith("Result") and node.text), None)
            if not result:
                raise ValueError("İETT SOAP yanıtında araç sonucu bulunamadı")
            return json.loads(result)

    def _snapshot(self, rows: list[dict], source: str) -> LiveSnapshot:
        vehicles: list[Vehicle] = []
        now = datetime.now(UTC)
        self._last_raw_count = len(rows)
        self._last_stale_count = 0
        for row in rows:
            props = row.get("properties", row)
            geometry = row.get("geometry", {})
            coords = geometry.get("coordinates", [props.get("longitude"), props.get("latitude")])
            if props.get("Enlem") is not None and props.get("Boylam") is not None:
                coords = [props.get("Boylam"), props.get("Enlem")]
            if len(coords) < 2 or coords[0] is None or coords[1] is None:
                continue
            recorded_at = self._parse_time(props.get("Saat"))
            if recorded_at and (now - recorded_at).total_seconds() > settings.max_vehicle_age_seconds:
                self._last_stale_count += 1
                continue
            vehicles.append(Vehicle(
                id=str(props.get("id", props.get("vehicle_id", props.get("KapiNo", props.get("plate", "unknown"))))),
                line=props.get("line", props.get("route")),
                plate=props.get("plate", props.get("Plaka")),
                door_number=props.get("door_number", props.get("KapiNo")),
                garage=props.get("garage", props.get("Garaj")),
                speed_kmh=props.get("speed_kmh", props.get("Hiz")),
                longitude=float(coords[0]), latitude=float(coords[1]),
                bearing=props.get("bearing"),
                recorded_at=recorded_at,
            ))
        return LiveSnapshot(fetched_at=datetime.now(UTC), source=source, vehicles=vehicles)

    def status(self) -> dict:
        snapshot = self._cached_snapshot
        return {
            "source": snapshot.source if snapshot else ("not-fetched"),
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "raw_vehicle_count": self._last_raw_count,
            "fresh_vehicle_count": len(snapshot.vehicles) if snapshot else 0,
            "stale_vehicle_count": self._last_stale_count,
            "line_assignment_available": any(v.line for v in snapshot.vehicles) if snapshot else False,
            "last_error": self._last_error,
        }

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.strptime(str(value), "%H:%M:%S").replace(tzinfo=timezone(timedelta(hours=3)))
            return parsed.astimezone(UTC).replace(year=datetime.now(UTC).year, month=datetime.now(UTC).month, day=datetime.now(UTC).day)
        except ValueError:
            return None
