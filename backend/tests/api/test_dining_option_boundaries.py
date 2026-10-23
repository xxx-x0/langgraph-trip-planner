"""Isolated CAS/failure checks; provider responses here are synthetic."""
import asyncio,json
from unittest.mock import patch,AsyncMock
import pytest
from app.database import async_session
from app.models.db_models import TripDraft
from app.services import trip_draft_service
from .test_meal_recovery import case


@pytest.mark.asyncio
@pytest.mark.parametrize('competitor',['pool','request','finalize'])
async def test_late_refresh_checks_pool_request_and_finalized_state(case,competitor):
    client,draft,url=case
    old=await trip_draft_service.get_draft(draft);day=json.loads(old.days_detail_json)[0];pool=json.loads(old.dining_pool_json)[0]
    entered,resume=asyncio.Event(),asyncio.Event()
    async def query(*a):
        entered.set();await resume.wait();return {'main':[{'name':'迟到店','category':'main'}]}
    with patch('app.agents.langgraph_agent.nodes.food.search_dining_for_day',side_effect=query):
        task=asyncio.create_task(client.post(url+'/dining-options'));await asyncio.wait_for(entered.wait(),2)
        if competitor=='pool':
            await trip_draft_service.patch_dining_pool(draft,0,{'main':[{'name':'较新店','category':'main'}]},expected_day=day,expected_pool=pool,expected_request=old.request_json)
        elif competitor=='request':
            async with async_session() as session:
                row=await session.get(TripDraft,draft);data=json.loads(row.request_json);data['meal_budget_per_person']=60;row.request_json=json.dumps(data);await session.commit()
        else:await trip_draft_service.mark_finalized(draft,trip_id=999999)
        saved=await trip_draft_service.get_draft(draft);expected_pool=saved.dining_pool_json
        resume.set();response=await task
    assert response.status_code==409
    latest=await trip_draft_service.get_draft(draft)
    assert latest.dining_pool_json==expected_pool and latest.days_detail_json==old.days_detail_json


@pytest.mark.asyncio
async def test_query_timeout_preserves_saved_meals_and_pool(case):
    client,draft,url=case;before=await trip_draft_service.get_draft(draft)
    with patch('app.agents.langgraph_agent.nodes.food.search_dining_for_day',new=AsyncMock(side_effect=TimeoutError())):
        response=await client.post(url+'/dining-options')
    assert response.status_code==504
    after=await trip_draft_service.get_draft(draft)
    assert after.days_detail_json==before.days_detail_json and after.dining_pool_json==before.dining_pool_json
