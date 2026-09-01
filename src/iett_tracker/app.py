from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx

from .provider import IettProvider
from .eta import Stop, nearest_vehicle_etas
from .routes import google_transit_duration_minutes
from .catalog import StopCatalog
from .route_catalog import RouteCatalog
from .arrivals import IettArrivalProvider
from .history import VehicleHistory
from math import cos, radians
import re

app = FastAPI(title="İETT Canlı Otobüs API", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
provider = IettProvider()
stop_catalog = StopCatalog()
route_catalog = RouteCatalog()
arrival_provider = IettArrivalProvider()
vehicle_history = VehicleHistory()


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
    return {"status": "ok"}


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
    return await arrival_provider.fetch(stop_code, line_code)


@app.post("/api/eta")
async def eta(stop: Stop, line: str | None = None):
    snapshot = await provider.fetch()
    return {
        "fetched_at": snapshot.fetched_at,
        "stop": stop,
        "etas": nearest_vehicle_etas(snapshot.vehicles, stop, line),
    }


@app.get("/api/routes/transit-duration")
async def transit_duration(origin_lat: float, origin_lon: float, destination_lat: float, destination_lon: float):
    minutes = await google_transit_duration_minutes(origin_lat, origin_lon, destination_lat, destination_lon)
    return {"available": minutes is not None, "duration_minutes": minutes, "source": "google-routes" if minutes else None}
