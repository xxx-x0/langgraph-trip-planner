from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


@pytest.fixture
def mock_fetch():
    """避免真实命中缓存/网络"""
    fake_items = [
        {"name": "新景点A", "category": "公园", "description": "x",
         "address": "", "rating": "4.5", "ticket_price": 0,
         "image_url": "", "location": {"longitude": 116.5, "latitude": 39.9},
         "poi_id": "a"},
        {"name": "新景点B", "category": "古迹", "description": "y",
         "address": "", "rating": "4.6", "ticket_price": 0,
         "image_url": "", "location": {"longitude": 116.6, "latitude": 39.8},
         "poi_id": "b"},
    ]
    with patch(
        "app.api.routes.trip_lg._fetch_attractions_batch",
        new=AsyncMock(return_value=fake_items),
    ) as m:
        yield m


def test_load_more_returns_filtered_batch(mock_fetch):
    resp = client.post("/api/discover/load_more", json={
        "city": "北京",
        "exclude_names": ["故宫", "天坛"],
        "batch_size": 20,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "attractions" in body
    assert len(body["attractions"]) == 2

    # 确认 helper 调用时把 exclude_names 转成 set
    args, kwargs = mock_fetch.call_args
    assert set(kwargs.get("exclude_names") or args[1]) == {"故宫", "天坛"}


def test_load_more_default_batch_size(mock_fetch):
    resp = client.post("/api/discover/load_more", json={
        "city": "北京",
        "exclude_names": [],
    })
    assert resp.status_code == 200
    # 默认 batch_size 应为 20
    args, kwargs = mock_fetch.call_args
    assert kwargs.get("batch_size", args[2] if len(args) > 2 else None) == 20


def test_load_more_rejects_empty_city():
    resp = client.post("/api/discover/load_more", json={
        "city": "",
        "exclude_names": [],
    })
    assert resp.status_code == 422
