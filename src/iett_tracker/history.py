import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Vehicle


class VehicleHistory:
    """Canlı araç gözlemlerini hat atamasından bağımsız saklar."""

    def __init__(self, path: str = "data/vehicles.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT NOT NULL,
                    plate TEXT,
                    door_number TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    speed_kmh REAL,
                    recorded_at TEXT,
                    fetched_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ix_vehicle_time ON vehicle_observations(vehicle_id, fetched_at)")

    def save(self, vehicles: list[Vehicle], fetched_at: datetime) -> None:
        rows = [(v.id, v.plate, v.door_number, v.latitude, v.longitude, v.speed_kmh,
                 v.recorded_at.isoformat() if v.recorded_at else None, fetched_at.isoformat()) for v in vehicles]
        with sqlite3.connect(self.path) as db:
            db.executemany("""
                INSERT INTO vehicle_observations
                (vehicle_id, plate, door_number, latitude, longitude, speed_kmh, recorded_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

    def recent(self, vehicle_id: str, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT vehicle_id, plate, door_number, latitude, longitude, speed_kmh, recorded_at, fetched_at
                FROM vehicle_observations WHERE vehicle_id = ?
                ORDER BY id DESC LIMIT ?
            """, (vehicle_id, limit)).fetchall()
        return [dict(row) for row in rows]
