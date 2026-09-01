import asyncio
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from .config import settings


class RouteStop(BaseModel):
    stop_id: str
    name: str | None = None
    sequence: int | None = None
    latitude: float | None = None
    longitude: float | None = None


class RouteDirection(BaseModel):
    line: str
    direction: int
    stops: list[RouteStop]


class RouteCatalog:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[RouteDirection]]] = {}
        self._lock = asyncio.Lock()

    async def fetch(self, line_code: str) -> list[RouteDirection]:
        key = line_code.strip().upper()
        cached = self._cache.get(key)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
            try:
                routes = await self._fetch_directions(key)
            except (httpx.HTTPError, ValueError, TypeError):
                # Internal endpoint geçici olarak kapalıysa uygulama 500 dönmesin.
                return cached[1] if cached else []
            self._cache[key] = (time.monotonic() + 86400, routes)
            return routes

    async def _fetch_directions(self, line_code: str) -> list[RouteDirection]:
        site_url = "https://iett.istanbul/tr/RouteStation/GetStationForRoute"
        search_url = "https://iett.istanbul/tr/RouteStation/GetSearchItems"
        async with httpx.AsyncClient(timeout=10) as client:
            search = await client.get(search_url, params={"key": line_code, "langid": 1})
            search.raise_for_status()
            items = search.json().get("list", [])
            name = next((item.get("Name") for item in items if item.get("Code", "").upper() == line_code), None)
            if not name or " - " not in name:
                return []
            start, end = [part.strip() for part in name.split(" - ", 1)]
            response = await client.get(site_url, params={"hatkod": line_code, "hatstart": start, "hatend": end, "langid": 1})
            response.raise_for_status()
            response.encoding = "windows-1254"
            soup = BeautifulSoup(response.text, "html.parser")
            results: list[RouteDirection] = []
            for direction, block in enumerate(soup.select(".line-pass-body"), start=1):
                stops = []
                for index, anchor in enumerate(block.select("a[href*='StationDetail']"), start=1):
                    href = anchor.get("href", "")
                    match = re.search(r"dkod=([^&]+)", href)
                    if not match:
                        continue
                    query = parse_qs(urlparse(href).query)
                    label = unquote(query.get("stationname", [anchor.get_text(" ", strip=True)])[0]).split("-", 1)[0].strip()
                    stops.append(RouteStop(stop_id=match.group(1), name=label, sequence=index))
                if stops:
                    results.append(RouteDirection(line=line_code, direction=direction, stops=stops))
            return results
