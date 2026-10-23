"""Actual route duration must drive recovery; every route/model value here is synthetic."""
from unittest.mock import AsyncMock, patch
import pytest
from .test_meal_recovery import case, fake
from app.api.routes import trip_draft
from app.services import trip_draft_service
from app.services.external_calls import ExternalServiceError, FailureKind


async def prepare(client, url):
    response = await client.post(url + '/recompute', json={
        'day_start_time':'10:00', 'meals':[
            {'name':'Lunch','type':'lunch','preferred_slot':'lunch','category':'main','insert_after':'B'},
            {'name':'Dinner','type':'dinner','preferred_slot':'dinner','category':'main','insert_after':'C'},
        ]})
    assert response.status_code == 200, response.text
    return response.json()['day_detail']


@pytest.mark.asyncio
@pytest.mark.parametrize('minutes,calls,recovery', [(1,1,False),(180,2,True)])
async def test_same_order_short_route_succeeds_long_route_needs_one_recovery(case, minutes, calls, recovery):
    client, draft, url = case
    before = await prepare(client,url)
    routes = AsyncMock(side_effect=[[{'from_name':'A','to_name':'B','duration':f'{minutes}分钟'}],[]])
    model = fake({'attractions_order':list('ABC'),'meals':[]})
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=model),patch.object(trip_draft,'compute_day_route',new=routes):
        response = await client.post(url + '/ai-rearrange',json={})
    assert response.status_code == 200, response.text
    detail = response.json()['day_detail']
    assert routes.await_count == calls and model.await_count == 1
    assert any('已保留原景点顺序和餐厅' in n for n in detail['meal_adjustments']) == recovery
    assert {m['type'] for m in detail['meals']} == {'lunch','dinner'}
    if recovery:
        assert detail['timeline_schedule'] == before['timeline_schedule']
    else:
        assert next(x for x in detail['timeline_schedule'] if x['kind']=='travel' and x['ref_name']=='A → B')['duration'] == 1


@pytest.mark.asyncio
async def test_route_failure_during_recovery_preserves_entire_saved_json(case):
    client, draft, url = case
    await prepare(client,url)
    before = (await trip_draft_service.get_draft(draft)).days_detail_json
    routes = AsyncMock(side_effect=[[{'from_name':'A','to_name':'B','duration':'180分钟'}],
        ExternalServiceError('amap','路线计算',FailureKind.CONNECTION)])
    model = fake({'attractions_order':list('ABC'),'meals':[]})
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=model),patch.object(trip_draft,'compute_day_route',new=routes):
        response = await client.post(url + '/ai-rearrange',json={})
    assert response.status_code == 503
    assert routes.await_count == 2 and model.await_count == 1
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == before
