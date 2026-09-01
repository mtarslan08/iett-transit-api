import re
import asyncio
import time
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel


class Arrival(BaseModel):
    line: str
    origin: str | None = None
    departure_time: str | None = None
    eta_minutes: int | None = None
    door_number: str | None = None
    direction: str | None = None
    last_location: str | None = None
    raw_text: str


class IettArrivalProvider:
    url = "https://iett.istanbul/WMyBus"

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = asyncio.Lock()
        self.last_error: str | None = None
        self.last_success_at: datetime | None = None

    async def fetch(self, stop_code: str, line_code: str) -> dict:
        key = (stop_code.strip(), line_code.strip().upper())
        cached = self._cache.get(key)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
            try:
                result = None
                for attempt in range(3):
                    try:
                        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                            response = await client.get(self.url, params={"dcode": key[0], "hcode": key[1]})
                            response.raise_for_status()
                        result = self._parse(response.text, key[1])
                        break
                    except httpx.HTTPError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.35 * (attempt + 1))
                assert result is not None
                self.last_success_at = result["fetched_at"]
                self.last_error = None
            except (httpx.HTTPError, ValueError):
                self.last_error = "İETT durak varış kaynağı alınamadı"
                if cached:
                    return cached[1]
                return {"available": False, "fetched_at": datetime.now(UTC), "source": self.url, "line": key[1], "arrivals": []}
            self._cache[key] = (time.monotonic() + 15, result)
            return result

    def status(self) -> dict:
        return {"source": self.url, "last_success_at": self.last_success_at, "last_error": self.last_error}

    def _parse(self, html: str, line_code: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        arrivals: list[Arrival] = []
        for item in soup.select("#departure .line-item, #depar .line-item"):
            text = " ".join(item.stripped_strings)
            if not text or "Kalktığı Durak" in text or line_code.upper() in text and "Varış" not in text:
                continue
            time_match = re.search(r"\b(\d{1,2}[:.]\d{2})\b", text)
            eta_match = re.search(r"\b(\d+)\s*dk\b", text, re.IGNORECASE)
            if not eta_match:
                continue
            origin = text.split("(", 1)[0].strip() or None
            arrivals.append(Arrival(
                line=line_code.upper(),
                origin=origin,
                departure_time=time_match.group(1).replace(".", ":") if time_match else None,
                eta_minutes=int(eta_match.group(1)),
                raw_text=text,
            ))
        return {
            "available": True,
            "fetched_at": datetime.now(UTC),
            "source": self.url,
            "line": line_code.upper(),
            "arrivals": arrivals,
        }
