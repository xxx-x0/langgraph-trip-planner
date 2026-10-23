import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import async_session, init_db
from app.models.db_models import TripRecord, UserPreferenceRecord
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton, DayDetail, Attraction, TripPlan, DayPlan
from app.services import trip_draft_service, preferences_service
from app.agents.langgraph_agent.finalize.pipeline import finalize_draft


@pytest_asyncio.fixture
async def draft_case():
    await init_db()
    user = 'atomic-' + uuid.uuid4().hex
    request = TripRequest(city=user, start_date='2026-10-14', end_date='2026-10-14',
                          travel_days=1, transportation='公共交通', accommodation='经济型酒店')
    draft = await trip_draft_service.create_draft(user_id=user, request=request, selected_attractions=[],
        macro_plan=MacroPlan(city=user, total_days=1, days=[DaySkeleton(day_index=0,date=request.start_date,attraction_names=['A'])]),
        clusters_data=[[{'name':'A','ticket_price':'免费'}]], hotels_by_day=[[]], dining_pool=[{}], weather_info=[])
    detail = DayDetail(day_index=0,date=request.start_date,attractions=[Attraction(name='A',address='',description='',visit_duration=60,ticket_price=0)],
                       day_start_time='10:00', timeline_order=[{'kind':'attraction','ref_name':'A'}], is_assembled=True)
    await trip_draft_service.patch_day_detail(draft,0,detail)
    record = await trip_draft_service.get_draft(draft)
    plan = TripPlan(city=user,start_date=request.start_date,end_date=request.end_date,overall_suggestions='',
            days=[DayPlan(**{k:v for k,v in detail.model_dump().items() if k in DayPlan.model_fields},
                          transportation=request.transportation,accommodation=request.accommodation)])
    return draft, user, request, record.days_detail_json, plan


async def counts(user):
    async with async_session() as session:
        trips = (await session.execute(select(func.count()).select_from(TripRecord).where(TripRecord.city==user))).scalar()
        prefs = (await session.execute(select(UserPreferenceRecord).where(UserPreferenceRecord.user_id==user))).scalar_one_or_none()
        return trips, json.loads(prefs.preference_data)['total_trips'] if prefs else 0


@pytest.mark.asyncio
async def test_concurrent_and_repeated_finalize_reuse_one_result(draft_case):
    draft,user,*_ = draft_case
    with patch('app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer',new=AsyncMock(return_value=('','',''))) as summary, \
         patch('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',new=AsyncMock(return_value={'preferred_attractions_per_day':1})), \
         patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        results=await asyncio.gather(*(finalize_draft(draft,user_id=user) for _ in range(3)))
        again=await finalize_draft(draft,user_id=user)
    assert len({result[1] for result in results+[again]})==1
    assert summary.await_count==1
    assert await counts(user)==(1,1)
    assert (await trip_draft_service.get_draft(draft)).finalized_trip_id==again[1]


@pytest.mark.asyncio
async def test_database_serializes_two_independent_writers(draft_case):
    draft,user,request,snapshot,plan = draft_case
    results=await asyncio.gather(*(trip_draft_service.persist_finalized_trip(
        draft,plan,request,snapshot,{'preferred_attractions_per_day':1}) for _ in range(2)))
    assert results[0][1]==results[1][1]
    assert await counts(user)==(1,1)


@pytest.mark.asyncio
async def test_failure_after_all_flushes_rolls_back_and_retry_commits_once(draft_case):
    draft,user,request,snapshot,plan = draft_case
    real_apply=preferences_service.apply_extracted_preferences
    async def fail_after_writes(session,*args):
        await real_apply(session,*args)
        await session.flush()
        raise RuntimeError('injected failure before commit')
    with patch('app.services.preferences_service.apply_extracted_preferences',side_effect=fail_after_writes):
        with pytest.raises(RuntimeError,match='injected failure'):
            await trip_draft_service.persist_finalized_trip(draft,plan,request,snapshot,{'preferred_attractions_per_day':1})
    assert await counts(user)==(0,0)
    record=await trip_draft_service.get_draft(draft)
    assert record.status=='skeleton' and record.finalized_trip_id is None
    assert record.days_detail_json==snapshot
    result=await trip_draft_service.persist_finalized_trip(draft,plan,request,snapshot,{'preferred_attractions_per_day':1})
    assert await counts(user)==(1,1)
    assert (await trip_draft_service.get_draft(draft)).finalized_trip_id==result[1]


@pytest.mark.asyncio
async def test_edit_during_llm_prevents_saving_stale_choices(draft_case):
    draft,user,*_ = draft_case
    async def change_during_generation(*args,**kwargs):
        record=await trip_draft_service.get_draft(draft)
        detail=DayDetail.model_validate(json.loads(record.days_detail_json)[0])
        detail.day_start_time='11:30'
        await trip_draft_service.patch_day_detail(draft,0,detail)
        return '','',''
    with patch('app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer',side_effect=change_during_generation), \
         patch('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',new=AsyncMock(return_value={'preferred_attractions_per_day':1})), \
         patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        with pytest.raises(trip_draft_service.DraftChangedDuringFinalize,match='已更新'):
            await finalize_draft(draft,user_id=user)
    assert await counts(user)==(0,0)
    record=await trip_draft_service.get_draft(draft)
    assert json.loads(record.days_detail_json)[0]['day_start_time']=='11:30'
    assert record.status=='skeleton'


@pytest.mark.asyncio
async def test_repeated_sse_finalize_recovers_same_saved_result_and_late_edit_rejected(draft_case):
    draft,user,request,snapshot,plan = draft_case
    first=await trip_draft_service.persist_finalized_trip(draft,plan,request,snapshot,{'preferred_attractions_per_day':1})
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post(f'/api/trip/draft/{draft}/finalize')
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        complete=next(event for event in events if event['type']=='complete')
        assert complete['trip_id']==first[1]
        assert (await client.post(f'/api/trip/draft/{draft}/day/0/recompute',json={'day_start_time':'12:00'})).status_code==409
    assert await counts(user)==(1,1)
    record=await trip_draft_service.get_draft(draft)
    with pytest.raises(trip_draft_service.DraftChangedDuringFinalize):
        await trip_draft_service.patch_day_detail(draft,0,DayDetail(day_index=0,date=request.start_date))
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==record.days_detail_json
