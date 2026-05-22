from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _payload(attractions, days=2):
    return {
        "selected_attractions": attractions,
        "travel_days": days,
    }


@pytest.fixture
def mock_estimate():
    """避免真实调 LLM"""
    with patch(
        "app.api.routes.trip_lg.estimate_durations_batch",
        new=AsyncMock(return_value={"故宫": 120, "天坛": 90, "颐和园": 150}),
    ) as m:
        yield m


def test_returns_per_day_assignment_and_durations(mock_estimate):
    payload = _payload([
        {"name": "故宫", "category": "博物馆", "location": {"longitude": 116.397, "latitude": 39.916}},
        {"name": "天坛", "category": "古迹", "location": {"longitude": 116.412, "latitude": 39.882}},
        {"name": "颐和园", "category": "公园", "location": {"longitude": 116.273, "latitude": 39.999}},
    ], days=2)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["day_assignments"]) == 2
    assert len(body["day_durations"]) == 2
    # 每个 attraction 都带 visit_minutes
    for day in body["day_assignments"]:
        for attr in day:
            assert attr["visit_minutes"] is not None and attr["visit_minutes"] > 0


def test_warning_set_when_day_over_8h(mock_estimate):
    # 故意构造一组紧密聚集（强制聚在同一天）且时长很长的景点
    mock_estimate.return_value = {"A": 240, "B": 240, "C": 240}
    payload = _payload([
        {"name": "A", "category": "x", "location": {"longitude": 116.40, "latitude": 39.90}},
        {"name": "B", "category": "x", "location": {"longitude": 116.401, "latitude": 39.901}},
        {"name": "C", "category": "x", "location": {"longitude": 116.402, "latitude": 39.902}},
    ], days=1)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    body = resp.json()
    assert body["day_durations"][0]["total_minutes"] == 720
    assert body["day_durations"][0]["warning"] is not None


def test_handles_missing_coords(mock_estimate):
    mock_estimate.return_value = {"A": 90, "B": 90}
    payload = _payload([
        {"name": "A", "category": "x"},
        {"name": "B", "category": "x"},
    ], days=2)
    resp = client.post("/api/trip/plan/preview-day-assignment", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # 没坐标也应该正常返回，不崩
    all_names = sorted(a["name"] for d in body["day_assignments"] for a in d)
    assert all_names == ["A", "B"]


def test_rejects_empty_attractions(mock_estimate):
    resp = client.post("/api/trip/plan/preview-day-assignment",
                       json={"selected_attractions": [], "travel_days": 2})
    # 空列表应该返回 200 + 空分配，或 400 — 由实现决定，这里测期望行为
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        body = resp.json()
        assert all(len(d) == 0 for d in body["day_assignments"])
