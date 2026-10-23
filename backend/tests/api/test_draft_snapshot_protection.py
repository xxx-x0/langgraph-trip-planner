"""Isolated batch extraction regressions; all external services are test doubles."""
import asyncio
import json
import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.api.main import app
from app.api.routes import trip_draft
from app.database import init_db, async_session
from app.models.db_models import TripDraft, TripRecord, UserPreferenceRecord
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton
from app.services import trip_draft_service
from app.agents.langgraph_agent.finalize import pipeline


@pytest_asyncio.fixture
async def case():
    await init_db()
    user = "snapshot-" + uuid.uuid4().hex
    request = TripRequest(city=user, start_date="2026-10-15", end_date="2026-10-16",
                          travel_days=2, transportation="步行", accommodation="民宿")
    draft = await trip_draft_service.create_draft(
        user_id=user, request=request, selected_attractions=[],
        macro_plan=MacroPlan(city=user, total_days=2, days=[
            DaySkeleton(day_index=i, date=date, attraction_names=["甲园", "乙园"])
            for i, date in enumerate([request.start_date, request.end_date])]),
        clusters_data=[[{"name":name, "visit_minutes":60, "ticket_price":"免费"}
                        for name in ["甲园", "乙园"]]] * 2,
        hotels_by_day=[[], []], dining_pool=[{}, {}], weather_info=[])
    with ExitStack() as stack:
        stack.enter_context(patch.object(trip_draft, "compute_day_route", new=AsyncMock(return_value=[])))
        stack.enter_context(patch.object(trip_draft, "write_day_narrative_llm", new=AsyncMock(return_value="新说明")))
        stack.enter_context(patch.object(trip_draft, "get_llm"))
        stack.enter_context(patch.object(trip_draft, "_invoke_llm_with_retry", new=AsyncMock(
            return_value=SimpleNamespace(content=json.dumps({"attractions_order":["乙园", "甲园"], "meals":[]})))))
        stack.enter_context(patch.object(pipeline, "compute_day_route", new=AsyncMock(return_value=[])))
        stack.enter_context(patch.object(pipeline, "_run_global_synthesizer", new=AsyncMock(return_value=("标语", "建议", "天气"))))
        stack.enter_context(patch.object(pipeline, "_run_extract_preferences", new=AsyncMock(return_value={"preferred_attractions_per_day":2})))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for i in range(2):
                response = await client.post(f"/api/trip/draft/{draft}/day/{i}/recompute", json={})
                assert response.status_code == 200, response.text
            yield client, draft, user


async def change_request(draft):
    async with async_session() as session:
        record = await session.get(TripDraft, draft)
        request = json.loads(record.request_json)
        request["budget"] = 4321
        record.request_json = json.dumps(request, ensure_ascii=False)
        await session.commit()
        return record.request_json


async def assert_no_finalized_writes(draft, user):
    record = await trip_draft_service.get_draft(draft)
    assert record.status == "skeleton" and record.finalized_trip_id is None
    async with async_session() as session:
        assert (await session.execute(select(func.count()).select_from(TripRecord).where(TripRecord.city == user))).scalar() == 0
        assert (await session.execute(select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user))).scalar_one_or_none() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["narrative", "recompute", "ai-rearrange", "assemble?force=true"])
async def test_late_daily_response_cannot_overwrite_newer_day(case, operation):
    client, draft, user = case
    url = f"/api/trip/draft/{draft}/day/0"
    entered, resume = asyncio.Event(), asyncio.Event()
    narrative = operation in ["narrative", "assemble?force=true"]
    async def paused(*args, **kwargs):
        entered.set()
        await asyncio.wait_for(resume.wait(), 5)
        return "过期说明" if narrative else []
    target = "write_day_narrative_llm" if narrative else "compute_day_route"
    with patch.object(trip_draft, target, side_effect=paused):
        task = asyncio.create_task(client.post(url + "/" + operation, json={}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            with patch.object(trip_draft, "compute_day_route", new=AsyncMock(return_value=[])):
                newer = await client.post(url + "/recompute", json={"day_start_time":"10:15"})
            assert newer.status_code == 200
            saved = (await trip_draft_service.get_draft(draft)).days_detail_json
        finally:
            resume.set()
        late = await asyncio.wait_for(task, 5)
    assert late.status_code == 409, late.text
    assert "未保存" in late.json()["detail"]
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == saved


@pytest.mark.asyncio
@pytest.mark.parametrize("competitor", ["other_day", "request", "finalize"])
async def test_snapshot_checks_relevant_state_at_write_time(case, competitor):
    client, draft, user = case
    entered, resume = asyncio.Event(), asyncio.Event()
    async def paused(*args, **kwargs):
        entered.set()
        await asyncio.wait_for(resume.wait(), 5)
        return "当前日新说明"
    with patch.object(trip_draft, "write_day_narrative_llm", side_effect=paused):
        task = asyncio.create_task(client.post(f"/api/trip/draft/{draft}/day/0/narrative"))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if competitor == "other_day":
                newer = await client.post(f"/api/trip/draft/{draft}/day/1/recompute", json={"day_start_time":"12:00"})
                assert newer.status_code == 200
            elif competitor == "request":
                new_request = await change_request(draft)
            else:
                await pipeline.finalize_draft(draft, user_id=user)
            saved = (await trip_draft_service.get_draft(draft)).days_detail_json
        finally:
            resume.set()
        response = await asyncio.wait_for(task, 5)
    record = await trip_draft_service.get_draft(draft)
    if competitor == "other_day":
        assert response.status_code == 200, response.text
        days = json.loads(record.days_detail_json)
        assert days[1] == json.loads(saved)[1]
        assert days[0]["description_source"] == "itinerary_facts_v1"
        assert "甲园" in days[0]["description"]
    else:
        assert response.status_code == 409, response.text
        assert record.days_detail_json == saved
        if competitor == "request":
            assert record.request_json == new_request
        else:
            assert record.status == "finalized"


@pytest.mark.asyncio
async def test_request_changed_during_finalize_rejects_old_snapshot(case):
    client, draft, user = case
    before = (await trip_draft_service.get_draft(draft)).days_detail_json
    async def changed(*args, **kwargs):
        await change_request(draft)
        return "标语", "建议", "天气"
    with patch.object(pipeline, "_run_global_synthesizer", side_effect=changed):
        with pytest.raises(trip_draft_service.DraftChangedDuringFinalize):
            await pipeline.finalize_draft(draft, user_id=user)
    await assert_no_finalized_writes(draft, user)
    record = await trip_draft_service.get_draft(draft)
    assert record.days_detail_json == before
    assert json.loads(record.request_json)["budget"] == 4321


@pytest.mark.asyncio
async def test_finalize_generation_failure_writes_nothing_and_sse_retry_recovers(case):
    client, draft, user = case
    before = (await trip_draft_service.get_draft(draft)).days_detail_json
    with patch.object(pipeline, "_run_extract_preferences", side_effect=RuntimeError("injected extraction failure")):
        failed = await client.post(f"/api/trip/draft/{draft}/finalize")
    assert '"type": "error"' in failed.text and '"type": "complete"' not in failed.text
    await assert_no_finalized_writes(draft, user)
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == before
    async def complete():
        response = await client.post(f"/api/trip/draft/{draft}/finalize")
        return next(json.loads(line[6:]) for line in response.text.splitlines()
                    if line.startswith("data: ") and json.loads(line[6:])["type"] == "complete")
    first, repeated = await complete(), await complete()
    assert repeated == first
    async with async_session() as session:
        history = await session.get(TripRecord, first["trip_id"])
        assert json.loads(history.plan_data) == first["trip_plan"]
    assert first["trip_plan"]["trip_tagline"] == f"{user} · 2日行程"
    assert first["trip_plan"]["weather_summary"] == ""


@pytest.mark.asyncio
async def test_explicit_preferences_unchanged_by_atomic_finalize(case):
    client, draft, user = case
    original = json.dumps({"source":"explicit", "total_trips":17, "preferred_attractions_per_day":9})
    async with async_session() as session:
        session.add(UserPreferenceRecord(user_id=user, preference_data=original, source="explicit"))
        await session.commit()
    await pipeline.finalize_draft(draft, user_id=user)
    async with async_session() as session:
        preference = (await session.execute(select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user))).scalar_one()
        assert preference.preference_data == original
