import json
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from app.database import init_db, async_session
from app.models.db_models import TripDraft
from app.services import trip_draft_service as svc
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, DayDetail,
)


@pytest_asyncio.fixture
async def _db():
    await init_db()
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(TripDraft))
        await session.commit()
    yield


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-03",
        travel_days=3, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro_plan():
    return MacroPlan(
        city="北京", total_days=3,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["故宫"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["颐和园"]),
            DaySkeleton(day_index=2, date="2026-06-03", attraction_names=["天坛"]),
        ],
    )


@pytest.mark.asyncio
async def test_create_draft_returns_id_and_persists(_db):
    draft_id = await svc.create_draft(
        user_id="u1",
        request=_sample_request(),
        selected_attractions=[],
        macro_plan=_sample_macro_plan(),
        clusters_data=[],
        hotels_by_day=[],
        dining_pool=[],
        weather_info=[],
    )
    assert draft_id and isinstance(draft_id, str)
    got = await svc.get_draft(draft_id)
    assert got is not None
    assert got.status == "skeleton"
    assert got.user_id == "u1"
    assert len(json.loads(got.days_detail_json)) == 3


@pytest.mark.asyncio
async def test_get_draft_returns_none_for_unknown(_db):
    assert await svc.get_draft("not-exist") is None


@pytest.mark.asyncio
async def test_patch_day_detail_replaces_specific_index(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    new_detail = DayDetail(day_index=1, date="2026-06-02", is_assembled=True)
    await svc.patch_day_detail(draft_id, day_index=1, day_detail=new_detail)
    got = await svc.get_draft(draft_id)
    days = json.loads(got.days_detail_json)
    assert days[0] is None
    assert days[1] is not None and days[1]["is_assembled"] is True
    assert days[2] is None


@pytest.mark.asyncio
async def test_mark_finalized_sets_status_and_trip_id(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    await svc.mark_finalized(draft_id, trip_id=42)
    got = await svc.get_draft(draft_id)
    assert got.status == "finalized"
    assert got.finalized_trip_id == 42
    assert got.finalized_at is not None


@pytest.mark.asyncio
async def test_delete_draft_removes_record(_db):
    draft_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    deleted = await svc.delete_draft(draft_id)
    assert deleted is True
    assert await svc.get_draft(draft_id) is None
    assert await svc.delete_draft(draft_id) is False


@pytest.mark.asyncio
async def test_delete_expired_only_removes_old_non_finalized(_db):
    old_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    async with async_session() as session:
        record = await session.get(TripDraft, old_id)
        record.updated_at = datetime.utcnow() - timedelta(days=60)
        await session.commit()
    fresh_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    finalized_id = await svc.create_draft(
        user_id="u1", request=_sample_request(), selected_attractions=[],
        macro_plan=_sample_macro_plan(), clusters_data=[], hotels_by_day=[],
        dining_pool=[], weather_info=[],
    )
    await svc.mark_finalized(finalized_id, trip_id=99)
    async with async_session() as session:
        record = await session.get(TripDraft, finalized_id)
        record.updated_at = datetime.utcnow() - timedelta(days=60)
        await session.commit()

    deleted_count = await svc.delete_expired(days=30)
    assert deleted_count == 1
    assert await svc.get_draft(old_id) is None
    assert await svc.get_draft(fresh_id) is not None
    assert await svc.get_draft(finalized_id) is not None
