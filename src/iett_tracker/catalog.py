import asyncio
import json
import time

from zeep import Client

from .config import settings
from .eta import Stop


class StopCatalog:
    def __init__(self) -> None:
        self._stops: list[Stop] | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def fetch(self) -> list[Stop]:
        if self._stops is not None and time.monotonic() < self._expires_at:
            return self._stops
        async with self._lock:
            if self._stops is not None and time.monotonic() < self._expires_at:
                return self._stops
            self._stops = await asyncio.to_thread(self._fetch_soap)
            self._expires_at = time.monotonic() + 86400
            return self._stops

    def _fetch_soap(self) -> list[Stop]:
        if not settings.iett_stops_wsdl_url:
            return []
        client = Client(wsdl=settings.iett_stops_wsdl_url)
        payload = client.service.GetDurak_json(DurakKodu="")
        rows = json.loads(payload) if isinstance(payload, str) else payload
        stops: list[Stop] = []
        for row in rows:
            lat = row.get("Enlem", row.get("latitude"))
            lon = row.get("Boylam", row.get("longitude"))
            stop_id = row.get("DurakKodu", row.get("id"))
            if lat is None or lon is None or stop_id is None:
                continue
            stops.append(Stop(
                id=str(stop_id),
                name=str(row.get("DurakAdi", row.get("name", stop_id))),
                latitude=float(lat), longitude=float(lon),
                line=row.get("HatKodu", row.get("line")),
            ))
        return stops
