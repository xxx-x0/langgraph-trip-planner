"""Isolated mocked hotel quote -> edits -> atomic history save/read consistency."""
import json
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.database import init_db
from app.models.schemas import MacroPlan, DaySkeleton, DayDetail, Budget
from app.services import trip_draft_service
from tests.services.test_hotel_quotes import request, parsed


@pytest.mark.asyncio
@pytest.mark.parametrize('condition,expected,missing',[
    ('matched',246.9,'税费'),('mismatch',0,'儿童年龄'),('unavailable',0,'未返回可售房型')])
async def test_quote_budget_remains_consistent_through_reads_finalize_and_retry(condition,expected,missing):
    await init_db()
    req=request();hotel=parsed()
    if condition=='mismatch':hotel.quote.unsupported_conditions.append('详情未回显匹配的儿童年龄')
    if condition=='unavailable':
        hotel.quote.status='unavailable';hotel.quote.availability='unavailable';hotel.quote.amount=None
    dates=['2026-10-19','2026-10-20','2026-10-21']
    draft=await trip_draft_service.create_draft(user_id='isolated-hotel-budget',request=req,selected_attractions=[],
        macro_plan=MacroPlan(city=req.city,total_days=3,days=[DaySkeleton(day_index=i,date=d,attraction_names=['A']) for i,d in enumerate(dates)]),
        clusters_data=[[{'name':'A','ticket_price':'未知','visit_minutes':60}]]*3,
        hotels_by_day=[[hotel.model_dump(mode='json')]]*3,dining_pool=[{}]*3,weather_info=[])
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        with patch('app.api.routes.trip_draft.compute_day_route',new=AsyncMock(return_value=[])):
            for i in range(3):
                response=await client.post(f'/api/trip/draft/{draft}/day/{i}/recompute',json={'meals':[]})
                assert response.status_code==200,response.text
                day=response.json()['day_detail']
                assert day['overnight_stay']==(i<2)
                assert day['companion_count']==2
                assert day['day_budget']['total_hotels']==(expected/2 if i<2 else 0)
        # Read projection must repair a stale cached subtotal without writing the draft.
        record=await trip_draft_service.get_draft(draft)
        stale=DayDetail.model_validate(json.loads(record.days_detail_json)[0]);stale.day_budget=Budget(total=9999,total_hotels=9999)
        await trip_draft_service.patch_day_detail(draft,0,stale)
        before=(await trip_draft_service.get_draft(draft)).days_detail_json
        view=(await client.get(f'/api/trip/draft/{draft}')).json()
        assert view['days_detail'][0]['day_budget']['total_hotels']==expected/2
        assert (await trip_draft_service.get_draft(draft)).days_detail_json==before
        with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])), patch('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',new=AsyncMock(return_value=None)):
            response=await client.post(f'/api/trip/draft/{draft}/finalize')
        event=next(json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ') and json.loads(line[6:])['type']=='complete')
        plan=event['trip_plan'];budget=plan['budget']
        assert budget['total_hotels']==expected
        assert not budget['is_complete'] and budget['is_within_budget'] is None
        assert any(missing in item for item in budget['unknown_cost_items'])
        assert '需要2晚住宿' in plan['overall_suggestions']
        assert [day['overnight_stay'] for day in plan['days']]==[True,True,False]
        assert budget['total']!=9999
        assert (await client.get(f"/api/trips/{event['trip_id']}")).json()['data']['plan']==plan
        again=await client.post(f'/api/trip/draft/{draft}/finalize')
        repeated=next(json.loads(line[6:]) for line in again.text.splitlines() if line.startswith('data: ') and json.loads(line[6:])['type']=='complete')
        assert repeated==event
