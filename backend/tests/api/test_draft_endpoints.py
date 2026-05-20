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


@pytest.mark.asyncio
async def test_assemble_returns_day_detail_and_writes_back(client):
    draft_id = await _seed_draft()
    with patch(
        "app.api.routes.trip_draft.compute_day_route",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.api.routes.trip_draft.write_day_narrative_llm",
        new=AsyncMock(return_value="今天是晴天，多带水。"),
    ):
        resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["day_index"] == 0
    assert body["day_detail"]["is_assembled"] is True
    assert body["day_detail"]["description"] == "今天是晴天，多带水。"
    # 服务端已 patch 进去
    record = await trip_draft_service.get_draft(draft_id)
    days = json.loads(record.days_detail_json)
    assert days[0] is not None
    assert days[1] is None


@pytest.mark.asyncio
async def test_assemble_idempotent_returns_cached(client):
    """已 assembled 的天再调一次不重新跑 LLM；force=true 才重跑"""
    draft_id = await _seed_draft()
    narrative_mock = AsyncMock(return_value="V1 文案")
    with patch(
        "app.api.routes.trip_draft.compute_day_route",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.api.routes.trip_draft.write_day_narrative_llm",
        new=narrative_mock,
    ):
        r1 = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
        assert narrative_mock.await_count == 1
        # 再调一次（不带 force）：不该重跑 LLM
        r2 = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
        assert narrative_mock.await_count == 1
        # 带 force：重跑
        narrative_mock.return_value = "V2 文案"
        r3 = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/assemble?force=true", json={}
        )
        assert narrative_mock.await_count == 2
        assert r3.json()["day_detail"]["description"] == "V2 文案"


@pytest.mark.asyncio
async def test_assemble_day_out_of_range(client):
    draft_id = await _seed_draft()
    resp = await client.post(f"/api/trip/draft/{draft_id}/day/99/assemble", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_assemble_rejects_finalized_draft(client):
    draft_id = await _seed_draft()
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)
    resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_recompute_with_attractions_order_change(client):
    draft_id = await _seed_draft()
    # 先 assemble 一次
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])), \
         patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="V1")):
        await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})

    # recompute：把景点顺序倒过来
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["A"], "meals": []}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert [a["name"] for a in body["day_detail"]["attractions"]] == ["A"]
    assert body["day_detail"]["meals"] == []
    # 文案保留旧的（recompute 不重写）
    assert body["day_detail"]["description"] == "V1"


@pytest.mark.asyncio
async def test_recompute_field_omission_preserves_current(client):
    """不传 meals 字段应保留当前 day_detail.meals"""
    from app.models.schemas import DayDetail, Attraction, Location
    draft_id = await _seed_draft()
    # 模拟：assemble 后餐饮非空
    existing = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[Attraction(name="A", address="", visit_duration=120,
                                description="",
                                location=Location(longitude=116.4, latitude=39.9))],
        meals=[
            {"type": "main", "category": "main", "name": "保留我", "estimated_cost": 80}
        ],
        description="V1", is_assembled=True,
    )
    await trip_draft_service.patch_day_detail(draft_id, 0, existing)

    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["A"]},  # 故意不传 meals
        )
    assert resp.status_code == 200
    body = resp.json()
    meal_names = [m["name"] for m in body["day_detail"]["meals"]]
    assert "保留我" in meal_names
