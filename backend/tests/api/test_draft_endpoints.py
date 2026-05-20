import json
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import init_db
from app.services import trip_draft_service
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, DiningPoolDay,
)


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro():
    return MacroPlan(
        city="北京", total_days=2,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["A"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["B"]),
        ],
    )


async def _seed_draft(user_id="u1") -> str:
    return await trip_draft_service.create_draft(
        user_id=user_id, request=_sample_request(),
        selected_attractions=[], macro_plan=_sample_macro(),
        clusters_data=[
            [{"name": "A", "longitude": 116.4, "latitude": 39.9}],
            [{"name": "B", "longitude": 116.5, "latitude": 39.95}],
        ],
        hotels_by_day=[[], []],
        dining_pool=[DiningPoolDay().model_dump(mode="json")] * 2,
        weather_info=[],
    )


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_draft_returns_payload(client):
    draft_id = await _seed_draft()
    resp = await client.get(f"/api/trip/draft/{draft_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft_id"] == draft_id
    assert body["status"] == "skeleton"
    assert body["city"] == "北京"
    assert len(body["days"]) == 2
    assert len(body["days_detail"]) == 2
    assert all(d is None for d in body["days_detail"])


@pytest.mark.asyncio
async def test_get_draft_404(client):
    resp = await client.get("/api/trip/draft/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_draft_removes_it(client):
    draft_id = await _seed_draft()
    resp = await client.delete(f"/api/trip/draft/{draft_id}")
    assert resp.status_code == 200
    resp2 = await client.get(f"/api/trip/draft/{draft_id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_draft_404(client):
    resp = await client.delete("/api/trip/draft/does-not-exist")
    assert resp.status_code == 404
