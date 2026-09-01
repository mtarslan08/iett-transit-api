from math import asin, cos, radians, sin, sqrt
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .models import Vehicle

EARTH_RADIUS_KM = 6371.0088


class Stop(BaseModel):
    id: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    sequence: int | None = None
    line: str | None = None


class VehicleEta(BaseModel):
    vehicle_id: str
    line: str | None
    plate: str | None
    door_number: str | None
    stop_id: str
    stop_name: str
    distance_km: float
    eta_minutes: int
    confidence: str


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """İki GPS noktası arasındaki kuş uçuşu mesafe; rota mesafesi değildir."""
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    value = sin(lat_delta / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))


def estimate_vehicle_eta(vehicle: Vehicle, stop: Stop, average_speed_kmh: float = 18) -> VehicleEta:
    """Basit MVP ETA'sı. Google Routes eklendiğinde bu süre trafik süresiyle değiştirilecek."""
    distance = distance_km(vehicle.latitude, vehicle.longitude, stop.latitude, stop.longitude)
    safe_speed = max(average_speed_kmh, 1)
    minutes = max(1, round(distance / safe_speed * 60))
    return VehicleEta(
        vehicle_id=vehicle.id,
        line=vehicle.line,
        plate=vehicle.plate,
        door_number=vehicle.door_number,
        stop_id=stop.id,
        stop_name=stop.name,
        distance_km=round(distance, 3),
        eta_minutes=minutes,
        confidence="low",  # yön ve yol ağı eşleştirilince yükseltilecek
    )


def estimate_wait_minutes(headway_minutes: float | None) -> int:
    """Sefer sıklığı biliniyorsa rastgele varış varsayımıyla ortalama bekleme süresi."""
    if headway_minutes is None or headway_minutes <= 0:
        return 0
    return max(0, round(headway_minutes / 2))


def nearest_vehicle_etas(vehicles: list[Vehicle], stop: Stop, line: str | None = None) -> list[VehicleEta]:
    matching = [vehicle for vehicle in vehicles if not line or vehicle.line == line]
    return sorted(
        (estimate_vehicle_eta(vehicle, stop) for vehicle in matching),
        key=lambda eta: eta.eta_minutes,
    )
