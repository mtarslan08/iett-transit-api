from datetime import UTC, datetime, timedelta

from iett_tracker.provider import IettProvider


def test_door_key_normalizes_separators():
    assert IettProvider._door_key(" O-3275 ") == "O3275"
    assert IettProvider._door_key("o3275") == "O3275"


def test_snapshot_normalizes_official_line_fields():
    snapshot = IettProvider()._snapshot([
        {
            "kapino": "O3275",
            "boylam": "29.1669975",
            "enlem": "40.9200226666667",
            "hatkodu": "KM34",
            "guzergahkodu": "KM34_D_D0",
            "yon": "KARTAL METRO",
            "son_konum_zamani": (datetime.now(UTC) + timedelta(seconds=30)).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "yakinDurakKodu": "227352",
        }
    ], "official")
    vehicle = snapshot.vehicles[0]
    assert vehicle.line == "KM34"
    assert vehicle.door_number == "O3275"
    assert vehicle.route_code == "KM34_D_D0"
    assert vehicle.nearest_stop_id == "227352"
    assert vehicle.recorded_at is not None
    assert vehicle.recorded_at.tzinfo == UTC
