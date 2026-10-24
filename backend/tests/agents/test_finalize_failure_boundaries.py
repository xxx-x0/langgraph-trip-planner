"""Exercise failures inside real projection, not a mocked finalizer wrapper."""
import asyncio
import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, func

from app.agents.langgraph_agent.finalize import pipeline
from app.agents.langgraph_agent.assemble import narrative
from app.database import async_session
from app.models.db_models import TripRecord, UserPreferenceRecord
from app.services import trip_draft_service
from app.services.external_calls import ExternalServiceError, FailureKind
from tests.api.test_legacy_read_boundaries import client, legacy_draft


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


async def saved_state(draft, user):
    record = await trip_draft_service.get_draft(draft)
    async with async_session() as session:
        histories = (await session.execute(select(func.count()).select_from(TripRecord))).scalar()
        preference = (await session.execute(select(UserPreferenceRecord).where(
            UserPreferenceRecord.user_id == user))).scalar_one_or_none()
    return (record.days_detail_json, record.request_json, record.status, record.finalized_trip_id,
            record.updated_at, histories, preference.preference_data if preference else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["runtime", "value", "external"])
async def test_inner_projection_failure_does_not_save_or_extract_and_retry_is_idempotent(client, fault):
    draft, user, _ = await legacy_draft()
    original_preference = json.dumps({"source": "explicit", "total_trips": 17, "marker": "keep"})
    async with async_session() as session:
        session.add(UserPreferenceRecord(user_id=user, preference_data=original_preference, source="explicit"))
        await session.commit()
    before = await saved_state(draft, user)
    error = {"runtime": RuntimeError("projection bug"), "value": ValueError("projection bug"),
        "external": ExternalServiceError("amap", "maps_search_detail", FailureKind.TIMEOUT)}[fault]
    original_refresh = narrative.refresh_day_description
    injected = False
    def fail_once(*args, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            raise error
        return original_refresh(*args, **kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(pipeline, "compute_day_route", new=AsyncMock(return_value=[])))
        extract = stack.enter_context(patch.object(pipeline, "_run_extract_preferences", new=AsyncMock(return_value={})))
        stack.enter_context(patch("app.agents.langgraph_agent.assemble.narrative.refresh_day_description", side_effect=fail_once))
        failed = events(await client.post(f"/api/trip/draft/{draft}/finalize"))
    assert not any(event["type"] == "complete" for event in failed)
    failures = [event for event in failed if event["type"] == "error"]
    assert len(failures) == 1 and failures[0]["retryable"] is (fault == "external")
    extract.assert_not_awaited()
    assert await saved_state(draft, user) == before
    with patch.object(pipeline, "compute_day_route", new=AsyncMock(return_value=[])), \
         patch.object(pipeline, "_run_extract_preferences", new=AsyncMock(return_value={"preferred_attractions_per_day": 2})):
        first = events(await client.post(f"/api/trip/draft/{draft}/finalize"))
        second = events(await client.post(f"/api/trip/draft/{draft}/finalize"))
    complete = next(event for event in first if event["type"] == "complete")
    assert next(event for event in second if event["type"] == "complete") == complete
    plan = complete["trip_plan"]
    assert plan["budget"]["total_attractions"] == 60
    assert plan["budget"]["total_meals"] == 120
    assert plan["budget"]["total_transportation"] == 300
    assert plan["budget"]["total"] == 480
    assert plan["budget"]["is_complete"] is False
    assert plan["narrative_source"] == "itinerary_facts_v1"
    after = await saved_state(draft, user)
    assert after[2] == "finalized" and after[3] == complete["trip_id"]
    assert after[5] == before[5] + 1 and after[6] == original_preference
    async with async_session() as session:
        history = await session.get(TripRecord, complete["trip_id"])
        assert json.loads(history.plan_data) == plan


@pytest.mark.asyncio
async def test_cancellation_inside_projection_cannot_commit_partial_finalization(client):
    draft, user, _ = await legacy_draft()
    before = await saved_state(draft, user)
    with patch.object(pipeline, "compute_day_route", new=AsyncMock(return_value=[])), \
         patch("app.agents.langgraph_agent.assemble.narrative.refresh_day_description", side_effect=asyncio.CancelledError), \
         patch.object(pipeline, "_run_extract_preferences", new=AsyncMock()) as extract:
        with pytest.raises(asyncio.CancelledError):
            await pipeline.finalize_draft(draft, user_id=user)
    extract.assert_not_awaited()
    assert await saved_state(draft, user) == before
