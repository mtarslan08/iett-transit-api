from iett_tracker.app import app


def test_versioned_api_routes_are_documented():
    paths = app.openapi()["paths"]
    assert "/api/v1/vehicles" in paths
    assert "/api/v1/vehicles/{line_code}" in paths
    assert "/api/v1/stops/{stop_code}/arrivals" in paths
