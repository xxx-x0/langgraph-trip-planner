import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.api.main import app
from app.api.routes import trip_draft
from app.database import init_db, async_session
from app.models.db_models import TripDraft
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton, DayDetail, Attraction, Location
from app.services import trip_draft_service
from app.services.external_calls import ExternalServiceError, FailureKind


def request():
    return TripRequest(city='苏州',start_date='2026-10-20',end_date='2026-10-20',
                       travel_days=1,transportation='公共交通',accommodation='经济型酒店')


async def create(user='default'):
    req=request()
    return await trip_draft_service.create_draft(user_id=user,request=req,selected_attractions=[],
        macro_plan=MacroPlan(city=req.city,total_days=1,days=[DaySkeleton(day_index=0,date=req.start_date,attraction_names=['A','B'])]),
        clusters_data=[[{'name':n,'longitude':120+i*.02,'latitude':31} for i,n in enumerate(['A','B'])]],
        hotels_by_day=[[]],dining_pool=[{}],weather_info=[])


@pytest.mark.asyncio
async def test_dropped_creation_complete_and_concurrent_retry_return_one_draft():
    await init_db();user='creation-'+uuid.uuid4().hex;calls=[]
    async def generate(**kwargs):
        calls.append(kwargs)
        draft=await create(user)
        # This simulates connection loss after durable save but before complete.
        yield {'type':'node_complete','node':'save_draft'}
        yield {'type':'complete','draft_id':draft}
    payload={'request':request().model_dump(mode='json'),'selected_attractions':[],
             'user_id':user,'request_id':uuid.uuid4().hex}
    with patch.object(trip_draft,'get_trip_planner_agent',return_value=SimpleNamespace(plan_from_selections_stream=generate)):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            first=await client.post('/api/trip/draft/from-selections/stream',json=payload)
            first_id=json.loads(first.text.split('data: ')[-1])['draft_id']
            repeats=await asyncio.gather(*(client.post('/api/trip/draft/from-selections/stream',json=payload) for _ in range(3)))
            assert all(json.loads(r.text.split('data: ')[-1])['draft_id']==first_id for r in repeats)
            changed={**payload,'weather_info':'changed input'}
            conflict=await client.post('/api/trip/draft/from-selections/stream',json=changed)
            assert '输入已改变' in conflict.text
    assert len(calls)==1
    async with async_session() as session:
        count=(await session.execute(select(func.count()).select_from(TripDraft).where(TripDraft.user_id==user))).scalar()
        assert count==1


@pytest.mark.asyncio
async def test_creation_failure_can_retry_same_request_without_partial_save():
    await init_db();user='creation-failure-'+uuid.uuid4().hex;attempt=0
    async def generate(**kwargs):
        nonlocal attempt
        attempt+=1
        if attempt==1:raise ExternalServiceError('llm','macro_planner',FailureKind.TIMEOUT)
        draft=await create(user)
        yield {'type':'complete','draft_id':draft}
    payload={'request':request().model_dump(mode='json'),'selected_attractions':[],
             'user_id':user,'request_id':uuid.uuid4().hex}
    with patch.object(trip_draft,'get_trip_planner_agent',return_value=SimpleNamespace(plan_from_selections_stream=generate)):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            failed=await client.post('/api/trip/draft/from-selections/stream',json=payload)
            assert 'macro_planner' in failed.text and 'error' in failed.text
            recovered=await client.post('/api/trip/draft/from-selections/stream',json=payload)
            assert json.loads(recovered.text.split('data: ')[-1])['type']=='complete'
