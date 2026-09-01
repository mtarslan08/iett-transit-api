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
                snapshot = None
                for attempt in range(3):
                    try:
                        snapshot = await self._fetch_uncached()
                        break
                    except (httpx.HTTPError, ValueError, TypeError):
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.4 * (attempt + 1))
                assert snapshot is not None
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

    async def fetch_line(self, line_code: str) -> LiveSnapshot | None:
        """Resmi İETT hat bazlı SOAP akışı; HatKodu ve AuthHeader kullanır."""
        if not settings.iett_wsdl_url:
            return None
        try:
            code = line_code.strip().upper()
            rows = None
            for attempt in range(3):
                try:
                    rows = await asyncio.to_thread(self._fetch_line_soap_rows, code)
                    break
                except (httpx.HTTPError, ValueError, TypeError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.4 * (attempt + 1))
            assert rows is not None
            line_snapshot = self._snapshot(rows, f"{settings.iett_wsdl_url}#GetHatOtoKonum_json")
            fleet_snapshot = await self.fetch()
            fleet_by_door = {self._door_key(v.door_number): v for v in fleet_snapshot.vehicles if v.door_number}
            merged = []
            for vehicle in line_snapshot.vehicles:
                fleet_vehicle = fleet_by_door.get(self._door_key(vehicle.door_number))
                if fleet_vehicle:
                    vehicle = vehicle.model_copy(update={
                        "plate": fleet_vehicle.plate,
                        "garage": fleet_vehicle.garage,
                        "speed_kmh": fleet_vehicle.speed_kmh,
                    })
                merged.append(vehicle)
            return line_snapshot.model_copy(update={"vehicles": merged})
        except (httpx.HTTPError, ValueError, TypeError):
            return None

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

    def _fetch_line_soap_rows(self, line_code: str) -> list[dict]:
        endpoint = settings.iett_wsdl_url.split("?", 1)[0]
        username = settings.iett_api_username or ""
        password = settings.iett_api_password or ""
        envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="http://tempuri.org/">
  <SOAP-ENV:Header><ns1:AuthHeader><ns1:Username>{username}</ns1:Username><ns1:Password>{password}</ns1:Password></ns1:AuthHeader></SOAP-ENV:Header>
  <SOAP-ENV:Body><ns1:GetHatOtoKonum_json><ns1:HatKodu>{line_code}</ns1:HatKodu></ns1:GetHatOtoKonum_json></SOAP-ENV:Body>
</SOAP-ENV:Envelope>'''
        response = httpx.post(endpoint, content=envelope.encode(), headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '"http://tempuri.org/GetHatOtoKonum_json"',
        }, timeout=settings.iett_request_timeout_seconds)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        result = next((node.text for node in root.iter() if node.tag.endswith("Result") and node.text), None)
        if not result:
            raise ValueError("İETT hat SOAP yanıtında araç sonucu bulunamadı")
        return json.loads(result)

    def _snapshot(self, rows: list[dict], source: str) -> LiveSnapshot:
        vehicles: list[Vehicle] = []
        now = datetime.now(UTC)
        self._last_raw_count = len(rows)
        self._last_stale_count = 0
        for row in rows:
            props = row.get("properties", row)
            geometry = row.get("geometry", {})
            coords = geometry.get("coordinates", [props.get("longitude", props.get("boylam")), props.get("latitude", props.get("enlem"))])
            if props.get("Enlem") is not None and props.get("Boylam") is not None:
                coords = [props.get("Boylam"), props.get("Enlem")]
            if props.get("enlem") is not None and props.get("boylam") is not None:
                coords = [props.get("boylam"), props.get("enlem")]
            if len(coords) < 2 or coords[0] is None or coords[1] is None:
                continue
            recorded_at = self._parse_time(props.get("Saat", props.get("son_konum_zamani")))
            if recorded_at and (now - recorded_at).total_seconds() > settings.max_vehicle_age_seconds:
                self._last_stale_count += 1
                continue
            vehicles.append(Vehicle(
                id=str(props.get("id", props.get("vehicle_id", props.get("KapiNo", props.get("kapino", props.get("plate", "unknown")))))),
                line=props.get("line", props.get("route", props.get("hatkodu"))),
                plate=props.get("plate", props.get("Plaka")),
                door_number=props.get("door_number", props.get("KapiNo", props.get("kapino"))),
                garage=props.get("garage", props.get("Garaj")),
                speed_kmh=props.get("speed_kmh", props.get("Hiz")),
                longitude=float(coords[0]), latitude=float(coords[1]),
                bearing=props.get("bearing"),
                direction=props.get("direction", props.get("yon")),
                route_code=props.get("route_code", props.get("guzergahkodu")),
                nearest_stop_id=str(props.get("nearest_stop_id", props.get("yakinDurakKodu"))) if props.get("yakinDurakKodu") is not None else None,
                recorded_at=recorded_at,
            ))
        return LiveSnapshot(fetched_at=datetime.now(UTC), source=source, vehicles=vehicles)

    @staticmethod
    def _door_key(value: str | None) -> str:
        return "".join(str(value or "").upper().split()).replace("-", "")

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
            text = str(value)
            if len(text) > 8:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=3)))
            else:
                parsed = datetime.strptime(text, "%H:%M:%S").replace(tzinfo=timezone(timedelta(hours=3)))
            return parsed.astimezone(UTC).replace(year=datetime.now(UTC).year, month=datetime.now(UTC).month, day=datetime.now(UTC).day)
        except ValueError:
            return None
