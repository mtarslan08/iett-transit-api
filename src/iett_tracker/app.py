from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .provider import IettProvider
from .eta import Stop, nearest_vehicle_etas
from .catalog import StopCatalog
from .route_catalog import RouteCatalog
from .arrivals import IettArrivalProvider
from .history import VehicleHistory
from .config import settings
from math import cos, radians
import re
import time
from collections import defaultdict, deque

app = FastAPI(
    title="İETT Transit Data API",
    description="İETT canlı araç, hat, durak ve varış verilerini geliştiriciler için sade REST cevaplarına dönüştürür.",
    version="1.0.0",
    contact={"name": "otobusum_nerede_v2", "url": "https://github.com/mtarslan08/otobusum_nerede_v2"},
)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()] or ["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
provider = IettProvider()
stop_catalog = StopCatalog()
route_catalog = RouteCatalog()
arrival_provider = IettArrivalProvider()
vehicle_history = VehicleHistory()
_request_log: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_REQUESTS = 120


def api_response(data, *, source: str = "iett", fetched_at=None, stale: bool = False) -> dict:
    return {"data": data, "meta": {"source": source, "fetched_at": fetched_at, "stale": stale}}


@app.middleware("http")
async def public_api_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/v1/"):
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _request_log[client]
        while bucket and now - bucket[0] >= RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return JSONResponse({"error": {"code": "rate_limited", "message": "Dakikalık istek limiti aşıldı."}}, status_code=429, headers={"Retry-After": "60"})
        bucket.append(now)
        if len(_request_log) > 1000:
            for address in [address for address, values in _request_log.items() if not values]:
                _request_log.pop(address, None)
    return await call_next(request)


def _route_points(route_rows: list[dict]) -> list[tuple[float, float]]:
    points = []
    for row in route_rows:
        for segment in str(row.get("line", "")).split("|"):
            pairs = re.findall(r"([\d.]+)\s+([\d.]+)", segment)
            points.extend((float(lon), float(lat)) for lon, lat in pairs)
    return points


def _distance_to_route_km(lon: float, lat: float, points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 999
    scale_x = 111.32 * cos(radians(lat))
    scale_y = 111.32
    best = 999.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        ax, ay = (lon - x1) * scale_x, (lat - y1) * scale_y
        bx, by = (x2 - x1) * scale_x, (y2 - y1) * scale_y
        length_sq = bx * bx + by * by
        t = max(0.0, min(1.0, (ax * bx + ay * by) / length_sq)) if length_sq else 0
        dx, dy = ax - t * bx, ay - t * by
        best = min(best, (dx * dx + dy * dy) ** 0.5)
    return best


@app.get("/")
async def home():
    return FileResponse("static/index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "provider": provider.status().get("source", "not-fetched")}


@app.get("/health/detailed")
async def detailed_health() -> dict:
    return {"status": "ok", "live": provider.status(), "arrivals": arrival_provider.status()}


@app.get("/api/live/vehicles")
async def live_vehicles():
    snapshot = await provider.fetch()
    if snapshot.vehicles:
        vehicle_history.save(snapshot.vehicles, snapshot.fetched_at)
    return {
        "available": snapshot.source not in {"unavailable", "not-configured"},
        "fetched_at": snapshot.fetched_at,
        "source": snapshot.source,
        "vehicles": snapshot.vehicles,
    }


@app.get("/api/live/status")
async def live_status():
    """Canlı kaynağın tazelik ve hat eşleştirme kabiliyetini açıkça döndürür."""
    snapshot = await provider.fetch()
    return {
        "available": bool(snapshot.vehicles),
        "matching_note": "İETT tüm-filo SOAP kaydında hat kodu yok; GPS yakınlığı doğrulanmış hat eşleşmesi değildir.",
        **provider.status(),
    }


@app.get("/api/live/vehicles/{vehicle_id}/history")
async def vehicle_history_endpoint(vehicle_id: str, limit: int = 20):
    return {"vehicle_id": vehicle_id, "observations": vehicle_history.recent(vehicle_id, min(max(limit, 1), 100))}


@app.get("/api/stops")
async def stops():
    items = await stop_catalog.fetch()
    return {"count": len(items), "stops": items}


@app.get("/api/routes/{line_code}")
async def route(line_code: str):
    routes = await route_catalog.fetch(line_code)
    return {
        "available": bool(routes),
        "line": line_code.upper(),
        "directions": routes,
        "count": len(routes),
    }


@app.get("/api/route-search")
async def route_search(q: str = ""):
    """Hat kutusu için resmi İETT katalog önerileri."""
    query = q.strip()
    if len(query) < 2:
        return {"items": []}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://iett.istanbul/tr/RouteStation/GetSearchItems",
            params={"key": query, "langid": 1},
        )
        response.raise_for_status()
        items = response.json().get("list", [])
    return {"items": [{"code": item.get("Code"), "name": item.get("Name")} for item in items if item.get("Code")]}


@app.get("/api/routes/{line_code}/map")
async def route_map(line_code: str):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            "https://iett.istanbul/tr/RouteStation/GetRoutePinV2",
            params={"q": f"{line_code.upper()}_G_D0"},
        )
        response.raise_for_status()
        return {"line": line_code.upper(), "routes": response.json()}


@app.get("/api/live/vehicles/near-route")
async def vehicles_near_route(line_code: str):
    """Hat bilgisi yokken yalnızca güzergâha yakın canlı araçları döndürür."""
    exact_snapshot = await provider.fetch_line(line_code)
    if exact_snapshot is not None:
        return {
            "available": bool(exact_snapshot.vehicles),
            "line": line_code.upper(),
            "vehicles": exact_snapshot.vehicles,
            "fetched_at": exact_snapshot.fetched_at,
            "matching_method": "iett-official-line-soap",
            "line_verified": True,
            "note": "Resmi İETT GetHatOtoKonum_json akışından alındı.",
        }
    async with httpx.AsyncClient(timeout=15) as client:
        route_response = await client.get(
            "https://iett.istanbul/tr/RouteStation/GetRoutePinV2",
            params={"q": f"{line_code.upper()}_G_D0"},
        )
        route_response.raise_for_status()
    route_rows = route_response.json()
    places = [p for r in route_rows for p in r.get("stationPlaces", [])]
    if not places:
        return {"available": False, "vehicles": []}
    snapshot = await provider.fetch()
    points = _route_points(route_rows)
    nearby = [v for v in snapshot.vehicles if _distance_to_route_km(v.longitude, v.latitude, points) <= 0.1]
    return {
        "available": bool(nearby),
        "line": line_code.upper(),
        "vehicles": nearby,
        "fetched_at": snapshot.fetched_at,
        "matching_method": "route-proximity",
        "line_verified": False,
        "radius_meters": 100,
        "note": "Araçlar seçili hattın güzergâhına yakın; canlı kayıtta hat kodu bulunmadığı için kesin hat eşleşmesi değildir.",
    }


@app.get("/api/live/arrivals")
async def arrivals(stop_code: str, line_code: str):
    result = await arrival_provider.fetch(stop_code, line_code)
    # WMyBus ETA kaydında çoğu zaman plaka yok. Aynı hattın resmi canlı
    # akışındaki nearest_stop_id ile yalnızca güvenli, doğrudan eşleşme yap.
    exact = await provider.fetch_line(line_code)
    candidates = []
    if exact:
        candidates = [v for v in exact.vehicles if v.nearest_stop_id == str(stop_code) and (v.plate or v.door_number)]
    enriched = []
    for index, item in enumerate(result.get("arrivals", [])):
        value = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if index < len(candidates):
            vehicle = candidates[index]
            value.update({"plate": vehicle.plate, "door_number": vehicle.door_number, "direction": vehicle.direction, "match_confidence": "exact-stop"})
        else:
            value["match_confidence"] = "unmatched"
        enriched.append(value)
    return {**result, "arrivals": enriched, "vehicle_match_count": len(candidates)}


# Public, versioned developer API. Eski /api endpointleri geriye dönük uyumluluk
# için korunur; yeni entegrasyonlar /api/v1 kullanmalıdır.
@app.get("/api/v1/vehicles", tags=["vehicles"])
async def v1_vehicles():
    result = await live_vehicles()
    return api_response(result["vehicles"], source=result["source"], fetched_at=result["fetched_at"], stale=not result["available"])


@app.get("/api/v1/vehicles/{line_code}", tags=["vehicles"])
async def v1_line_vehicles(line_code: str):
    result = await vehicles_near_route(line_code)
    return api_response(result["vehicles"], source=result.get("matching_method", "iett"), fetched_at=result.get("fetched_at"), stale=not result.get("available", False)) | {"line": line_code.upper(), "line_verified": result.get("line_verified", False)}


@app.get("/api/v1/lines/{line_code}", tags=["lines"])
async def v1_line(line_code: str):
    result = await route(line_code)
    return api_response(result["directions"], source="iett-route-catalog") | {"line": result["line"], "count": result["count"]}


@app.get("/api/v1/stops", tags=["stops"])
async def v1_stops():
    result = await stops()
    return api_response(result["stops"], source="iett-stop-catalog") | {"count": result["count"]}


@app.get("/api/v1/stops/{stop_code}", tags=["stops"])
async def v1_stop(stop_code: str):
    items = await stop_catalog.fetch()
    stop_item = next((item for item in items if item.id == stop_code), None)
    if stop_item is None:
        raise HTTPException(status_code=404, detail={"code": "stop_not_found", "message": "Durak bulunamadı."})
    return api_response(stop_item, source="iett-stop-catalog")


@app.get("/api/v1/stops/{stop_code}/arrivals", tags=["arrivals"])
async def v1_stop_arrivals(stop_code: str, line_code: str):
    result = await arrivals(stop_code, line_code)
    return api_response(result["arrivals"], source=result.get("source", "iett"), fetched_at=result.get("fetched_at"), stale=not result.get("available", False)) | {"stop_code": stop_code, "line": line_code.upper(), "vehicle_match_count": result.get("vehicle_match_count", 0)}


@app.post("/api/eta")
async def eta(stop: Stop, line: str | None = None):
    snapshot = await provider.fetch()
    return {
        "experimental": True,
        "note": "Bu endpoint kuş uçuşu mesafe ve ortalama hız kullanan deneysel tahmindir.",
        "fetched_at": snapshot.fetched_at,
        "stop": stop,
        "etas": nearest_vehicle_etas(snapshot.vehicles, stop, line),
    }
