"""Legacy JSON and read projections through real APIs and isolated SQLite."""
import copy
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import async_session, init_db
from app.models.db_models import TripDraft, TripRecord
from app.models.schemas import (
    Attraction, CompanionInfo, DayDetail, DaySkeleton, MacroPlan, Meal, TripRequest,
)
from app.services import trip_draft_service, trip_history_service


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def legacy_draft(count=3, stored_count="missing", source="missing"):
    user = "legacy-" + uuid.uuid4().hex
    req = TripRequest(city="北京", start_date="2026-06-01", end_date="2026-06-02",
                      travel_days=2, transportation="公共交通", accommodation="酒店",
                      companions=CompanionInfo(type="friends", count=count) if count else None,
                      free_text_input="想慢游")
    draft = await trip_draft_service.create_draft(
        user_id=user, request=req, selected_attractions=[],
        macro_plan=MacroPlan(city=req.city, total_days=2, days=[
            DaySkeleton(day_index=i, date=date, attraction_names=[name])
            for i, (date, name) in enumerate([(req.start_date, "A"), (req.end_date, "B")])]),
        clusters_data=[[{"name": name, "ticket_price": "10", "visit_minutes": 60}]
                       for name in ["A", "B"]],
        hotels_by_day=[[], []], dining_pool=[{}, {}], weather_info=[])
    days = []
    for i, name in enumerate(["A", "B"]):
        day = DayDetail(day_index=i, date=[req.start_date, req.end_date][i],
            day_start_time="09:00", is_assembled=True, description="旧版未核对说明",
            trip_intent={"companion_type": "elderly", "companion_count": 9},
            attractions=[Attraction(name=name, address="", description="", visit_duration=60, ticket_price=10)],
            meals=[Meal(name="自选店", type="lunch", estimated_cost=20)],
            timeline_order=[{"kind": "attraction", "ref_name": name}, {"kind": "meal", "ref_name": "自选店"}]
        ).model_dump(mode="json")
        day["extra_legacy_day"] = {"preserve": True}
        day.pop("overnight_stay")
        if stored_count == "missing": day.pop("companion_count")
        else: day["companion_count"] = stored_count
        if source == "missing": day.pop("description_source")
        else: day["description_source"] = source
        days.append(day)
    async with async_session() as session:
        record = await session.get(TripDraft, draft)
        record.days_detail_json = json.dumps(days, ensure_ascii=False)
        await session.commit()
    return draft, user, req


async def draft_bytes(draft):
    record = await trip_draft_service.get_draft(draft)
    return record.request_json, record.days_detail_json, record.status, record.updated_at


def old_plan(source="missing", amount=None):
    hotel = {"name": "旧酒店", "estimated_cost": 999}
    if amount is not None:
        hotel["quote"] = dict(source="synthetic", cost_kind="query_quote", status="detail_returned",
            amount=amount, currency="CNY", unit="total_stay", check_in="2026-06-01",
            check_out="2026-06-02", nights=1, occupancy={"room_count": 1, "adults_per_room": 3, "children_ages": []},
            occupancy_confirmed=True, queried_at="2026-05-31T09:00", unsupported_conditions=[],
            availability="returned", taxes_included=True, meal_plan="不含早餐", cancellation_policy="不可退")
    days = []
    for i, date in enumerate(["2026-06-01", "2026-06-02"]):
        day = dict(day_index=i, date=date, description="已预约，全部免费", transportation="步行", accommodation="酒店",
            hotel=copy.deepcopy(hotel), extra_legacy_day={"id": "keep"},
            timeline_schedule=[dict(kind="hotel", ref_name="旧酒店", start_time="08:00", end_time="08:00",
                start_minutes=480, end_minutes=480, duration=0, cost=999, extra_saved_marker="keep")])
        if source != "missing": day["description_source"] = source
        days.append(day)
    raw = dict(city="北京", start_date="2026-06-01", end_date="2026-06-02", days=days,
        overall_suggestions="已预约，全部免费", companions={"type": "friends", "count": 3},
        budget={"total_hotels": 1998, "total": 1998, "budget_limit": 10000, "is_within_budget": True,
                "extra_budget_marker": "keep"}, extra_legacy_plan={"id": "keep"})
    if source != "missing": raw["narrative_source"] = source
    return raw


async def seed_history(raw):
    async with async_session() as session:
        record = TripRecord(title="Legacy fixture", city="北京", start_date="2026-06-01", end_date="2026-06-02",
            travel_days=2, plan_data=json.dumps(raw, ensure_ascii=False), request_data=None, total_cost=1998)
        session.add(record)
        await session.commit()
        return record.id, record.plan_data, record.updated_at


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["missing", None, "", "legacy_v0", "llm_v0"])
async def test_legacy_sources_read_through_both_apis_without_rewriting_storage(client, source):
    draft, _, _ = await legacy_draft(source=source)
    before = await draft_bytes(draft)
    response = await client.get(f"/api/trip/draft/{draft}")
    assert response.status_code == 200, response.text
    for day in response.json()["days_detail"]:
        assert day["description_source"] == "itinerary_facts_v1"
        assert "旧版未核对说明" not in day["description"]
    assert await draft_bytes(draft) == before
    trip_id, saved, timestamp = await seed_history(old_plan(source))
    for _ in range(2):
        response = await client.get(f"/api/trips/{trip_id}")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan"]
        assert plan["narrative_source"] == "itinerary_facts_v1"
        assert plan["extra_legacy_plan"] == {"id": "keep"}
        assert all(d["description_source"] == "itinerary_facts_v1" for d in plan["days"])
        assert "已预约" not in plan["overall_suggestions"]
    record = await trip_history_service.get_trip_by_id(trip_id)
    assert (record.plan_data, record.request_data, record.updated_at) == (saved, None, timestamp)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [None, 1, 3, 5])
@pytest.mark.parametrize("stored_count", ["missing", 1, 9])
async def test_party_budget_projection_uses_request_and_never_backfills_saved_json(client, count, stored_count):
    draft, _, _ = await legacy_draft(count=count, stored_count=stored_count)
    before = await draft_bytes(draft)
    response = await client.get(f"/api/trip/draft/{draft}")
    assert response.status_code == 200, response.text
    days = response.json()["days_detail"]
    for day in days:
        assert day["companion_count"] == (count or 1)
        assert day["day_budget"]["total_attractions"] == 10 * (count or 1)
        assert day["day_budget"]["total_meals"] == 20 * (count or 1)
        assert day["day_budget"]["total_transportation"] == 50 * (count or 1)
        assert day["trip_intent"]["companion_count"] == (count or 1)
    assert [day["overnight_stay"] for day in days] == [True, False]
    assert await draft_bytes(draft) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [None, 0, 120])
async def test_history_cost_projection_keeps_schedule_budget_and_unknowns_consistent(client, amount):
    trip_id, saved, timestamp = await seed_history(old_plan(amount=amount))
    results = []
    for _ in range(2):
        response = await client.get(f"/api/trips/{trip_id}")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan"]
        assert plan["budget"]["total_hotels"] == (amount or 0)
        assert plan["days"][0]["timeline_schedule"][0]["cost"] == amount
        assert plan["days"][1]["timeline_schedule"][0]["cost"] is None
        assert [d["overnight_stay"] for d in plan["days"]] == [True, False]
        assert plan["budget"]["extra_budget_marker"] == "keep"
        assert plan["budget"]["is_complete"] is False
        assert plan["budget"]["is_within_budget"] is None
        for day in plan["days"]:
            assert day["extra_legacy_day"] == {"id": "keep"}
            assert day["timeline_schedule"][0]["extra_saved_marker"] == "keep"
        results.append(plan)
    assert results[0] == results[1]
    record = await trip_history_service.get_trip_by_id(trip_id)
    assert (record.plan_data, record.updated_at, record.total_cost) == (saved, timestamp, 1998)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [{"days": [{"description": "已预约"}], "extra": 42},
    {"city": "北京", "days": "broken", "extra": 42}])
async def test_invalid_legacy_history_falls_back_without_trusting_prose_or_writing(client, raw):
    trip_id, saved, timestamp = await seed_history(raw)
    response = await client.get(f"/api/trips/{trip_id}")
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan"]
    assert plan["extra"] == 42 and "narrative_source" not in plan
    assert "旧记录缺少可核对安排" in plan["overall_suggestions"]
    record = await trip_history_service.get_trip_by_id(trip_id)
    assert (record.plan_data, record.updated_at) == (saved, timestamp)
