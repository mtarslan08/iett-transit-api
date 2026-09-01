from datetime import datetime
from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    id: str
    line: str | None = None
    plate: str | None = None
    door_number: str | None = None
    garage: str | None = None
    speed_kmh: float | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    bearing: float | None = None
    direction: str | None = None
    route_code: str | None = None
    nearest_stop_id: str | None = None
    recorded_at: datetime | None = None


class LiveSnapshot(BaseModel):
    fetched_at: datetime
    source: str
    vehicles: list[Vehicle]
