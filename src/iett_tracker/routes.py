from datetime import UTC, datetime

import httpx

from .config import settings

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


async def google_transit_duration_minutes(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> int | None:
    """Google'ın toplu taşıma rota süresini döndürür; anahtar yoksa devre dışıdır."""
    if not settings.google_maps_api_key:
        return None

    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lon}}},
        "destination": {"location": {"latLng": {"latitude": destination_lat, "longitude": destination_lon}}},
        "travelMode": "TRANSIT",
        "departureTime": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "transitPreferences": {"allowedTravelModes": ["BUS"], "routingPreference": "FEWER_TRANSFERS"},
    }
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "routes.duration,routes.legs.steps.transitDetails",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(ROUTES_URL, json=body, headers=headers)
        response.raise_for_status()
        routes = response.json().get("routes", [])
    if not routes:
        return None
    duration = routes[0].get("duration", "0s").removesuffix("s")
    return max(1, round(float(duration) / 60))
