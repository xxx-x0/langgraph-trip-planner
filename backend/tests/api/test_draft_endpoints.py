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


@pytest.mark.asyncio
async def test_recompute_accepts_day_start_override(client):
    draft_id = await _seed_draft()

    with patch(
        "app.api.routes.trip_draft.compute_day_route",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/recompute",
            json={"day_start_time": "09:45"},
        )

    assert resp.status_code == 200
    assert resp.json()["day_detail"]["day_start_time"] == "09:45"


@pytest.mark.asyncio
async def test_narrative_endpoint_rewrites_description_only(client):
    from app.models.schemas import DayDetail, Attraction
    draft_id = await _seed_draft()
    existing = DayDetail(
        day_index=0, date="2026-06-01",
        attractions=[Attraction(name="A", address="", visit_duration=120,
                                description="")],
        description="V1", is_assembled=True,
    )
    await trip_draft_service.patch_day_detail(draft_id, 0, existing)

    with patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="V2 新文案")):
        resp = await client.post(f"/api/trip/draft/{draft_id}/day/0/narrative", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["day_detail"]["description"] == "V2 新文案"
    # 景点未动
    assert [a["name"] for a in body["day_detail"]["attractions"]] == ["A"]


@pytest.mark.asyncio
async def test_ai_rearrange_replaces_day_detail(client):
    draft_id = await _seed_draft()
    # 先 assemble
    with patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])), \
         patch("app.api.routes.trip_draft.write_day_narrative_llm",
               new=AsyncMock(return_value="原文案")):
        await client.post(f"/api/trip/draft/{draft_id}/day/0/assemble", json={})

    # mock LLM 返回一组餐厅 + 景点顺序
    fake_llm_resp = type("R", (), {"content": json.dumps({
        "attractions_order": ["A"],
        "meals": [{"category": "main", "name": "AI 推荐", "insert_after": "A",
                   "estimated_cost": 100}],
    })})
    with patch("app.api.routes.trip_draft._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_llm_resp)), \
         patch("app.api.routes.trip_draft.get_llm", return_value=object()), \
         patch("app.api.routes.trip_draft.compute_day_route",
               new=AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/trip/draft/{draft_id}/day/0/ai-rearrange",
            json={"hint": "我想吃辣的"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "AI 推荐" in [m["name"] for m in body["day_detail"]["meals"]]


@pytest.mark.asyncio
async def test_finalize_sse_returns_trip_id(client):
    draft_id = await _seed_draft()

    fake_trip_record = type("Rec", (), {"id": 555})()
    from app.models.schemas import TripPlan, Budget
    fake_trip_plan = TripPlan(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        days=[], weather_info=[], overall_suggestions="",
        budget=Budget(),
    )

    with patch(
        "app.api.routes.trip_draft.finalize_draft",
        new=AsyncMock(return_value=(fake_trip_plan, 555)),
    ):
        async with client.stream(
            "POST", f"/api/trip/draft/{draft_id}/finalize"
        ) as resp:
            chunks = [c async for c in resp.aiter_text()]
            body = "".join(chunks)

    assert "data: " in body
    events = [
        json.loads(line.removeprefix("data: ").strip())
        for line in body.splitlines() if line.startswith("data: ")
    ]
    types = [e["type"] for e in events]
    assert "complete" in types
    complete_evt = next(e for e in events if e["type"] == "complete")
    assert complete_evt["trip_id"] == 555


@pytest.mark.asyncio
async def test_finalize_already_finalized_returns_409(client):
    draft_id = await _seed_draft()
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)
    async with client.stream(
        "POST", f"/api/trip/draft/{draft_id}/finalize"
    ) as resp:
        body = "".join([c async for c in resp.aiter_text()])
    events = [
        json.loads(line.removeprefix("data: ").strip())
        for line in body.splitlines() if line.startswith("data: ")
    ]
    assert any(e["type"] == "error" for e in events)
