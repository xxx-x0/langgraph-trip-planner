from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_ai_select_returns_matched_ids():
    fake_result = {
        "recommended_ids": ["1", "3"],
        "source_strategy_title": "北京三日游精华路线",
    }
    with patch(
        "app.api.routes.trip_lg.extract_attractions_from_strategy",
        new=AsyncMock(return_value=fake_result),
    ):
        resp = client.post("/api/discover/ai_select", json={
            "destination": "北京",
            "days": 3,
            "attractions": [
                {"poi_id": "1", "name": "故宫"},
                {"poi_id": "2", "name": "天坛"},
                {"poi_id": "3", "name": "颐和园"},
            ],
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_ids"] == ["1", "3"]
    assert body["source_strategy_title"] == "北京三日游精华路线"


def test_ai_select_rejects_empty_destination():
    resp = client.post("/api/discover/ai_select", json={
        "destination": "",
        "days": 3,
        "attractions": [],
    })
    assert resp.status_code == 422


def test_ai_select_returns_500_on_extract_exception():
    with patch(
        "app.api.routes.trip_lg.extract_attractions_from_strategy",
        new=AsyncMock(side_effect=RuntimeError("internal /private/error")),
    ):
        resp = client.post("/api/discover/ai_select", json={
            "destination": "北京",
            "days": 3,
            "attractions": [],
        })
    assert resp.status_code == 500
    body = resp.json()
    assert "/private/error" not in str(body)
