"""Persisted editing/AI/failure recovery, with explicit synthetic maps and LLM output."""
import asyncio,json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest,pytest_asyncio
from httpx import ASGITransport,AsyncClient
from app.api.main import app
from app.api.routes import trip_draft
from app.database import init_db
from app.models.schemas import TripRequest,MacroPlan,DaySkeleton,DayDetail
from app.services import trip_draft_service
from app.services.external_calls import operation_deadline,ExternalServiceError,FailureKind


@pytest_asyncio.fixture
async def case():
    await init_db()
    req=TripRequest(city='苏州',start_date='2026-10-15',end_date='2026-10-15',travel_days=1,transportation='步行',accommodation='民宿')
    draft=await trip_draft_service.create_draft(user_id='meal-test',request=req,selected_attractions=[],
        macro_plan=MacroPlan(city=req.city,total_days=1,days=[DaySkeleton(day_index=0,date=req.start_date,attraction_names=list('ABC'))]),
        clusters_data=[[{'name':n,'visit_minutes':60,'longitude':120+i*.01,'latitude':31} for i,n in enumerate('ABC')]],
        hotels_by_day=[[]],dining_pool=[{'main':[{'name':n,'category':'main','avg_cost':cost,'open_hours':hours,'source':'nearby','location':{'longitude':120.001,'latitude':31}} for n,cost,hours in [('Lunch',20,'07:00-23:00'),('Dinner',30,'07:00-23:00'),('Closed',40,'07:00-10:00')]],'cafe':[{'name':'Coffee','category':'cafe','avg_cost':10,'open_hours':'08:00-20:00'}]}],weather_info=[])
    with patch.object(trip_draft,'write_day_narrative_llm',new=AsyncMock(return_value="隔离测试说明")), patch('app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer',new=AsyncMock(return_value=("","",""))), patch('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',new=AsyncMock(return_value=None)), patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            url=f'/api/trip/draft/{draft}/day/0'
            response=await client.post(url+'/recompute',json={'locked_attraction_names':['B'],'meals':[
                {'name':'Lunch','category':'main','type':'lunch','avg_cost':20,'open_hours':'07:00-23:00','insert_after':'A'},
                {'name':'Dinner','category':'main','type':'dinner','avg_cost':30,'open_hours':'07:00-23:00','insert_after':'C'}]})
            assert response.status_code==200,response.text
            yield client,draft,url


def fake(content):return AsyncMock(return_value=SimpleNamespace(content=json.dumps(content)))


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['recompute','assemble?force=true'])
async def test_deletion_with_frontend_full_meal_snapshot_preserves_slots_and_readback(case,operation):
    client,draft,url=case
    current=(await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]
    meals=trip_draft._saved_meals(DayDetail.model_validate(current))
    response=await client.post(url+'/'+operation,json={'removed_attraction_names':['A'],'meals':meals})
    assert response.status_code==200
    day=response.json()['day_detail']
    assert [m['type'] for m in day['meals']]==['lunch','dinner']
    assert day['timeline_order'][0]['ref_name']=='Lunch'
    assert day['locked_attraction_names']==['B'] and day['removed_attraction_names']==['A']
    assert '首个景点之前' in '\n'.join(day['meal_adjustments'])
    assert not any('午餐未安排' in x for x in day['meal_warnings'])
    assert (await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]==day


@pytest.mark.asyncio
@pytest.mark.parametrize('proposal',[{}, {'meals':[]},{'meals':[{'name':'Lunch','preferred_slot':'lunch'}]},
    {'meals':[{'name':'Coffee','category':'main','preferred_slot':'dinner'},{'name':'Unknown','preferred_slot':'lunch'}]},
    {'meals':[{'name':'Lunch','preferred_slot':'dinner'},{'name':'Lunch','preferred_slot':'lunch'}]}])
async def test_ai_omission_and_bad_candidates_keep_both_saved_main_slots(case,proposal):
    client,draft,url=case
    invocation=fake({'attractions_order':list('CBA'),**proposal})
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=invocation):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200,response.text
    day=response.json()['day_detail']
    assert {'lunch','dinner'} <= {m['type'] for m in day['meals']}
    assert len({m['name'] for m in day['meals']})==len(day['meals'])
    assert 'Unknown' not in {m['name'] for m in day['meals']}
    assert invocation.await_count==1
    prompt=invocation.call_args.args[1][1].content
    assert '当前已安排用餐' in prompt and 'Dinner' in prompt and '07:00-23:00' in prompt
    assert 'breakfast' not in {m['type'] for m in day['meals']}
    assert day['attractions'][1]['name']=='B'
    assert (await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]==day


@pytest.mark.asyncio
async def test_ai_does_not_restore_a_manually_deleted_dinner(case):
    client,_,url=case
    await client.post(url+'/recompute',json={'meals':[{'name':'Lunch','type':'lunch','category':'main','avg_cost':20,'insert_after':'A','open_hours':'07:00-23:00'}]})
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'meals':[{'name':'Dinner','preferred_slot':'dinner'}]})):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200
    assert [m['name'] for m in response.json()['day_detail']['meals']]==['Lunch']
    assert any('晚餐未安排' in w for w in response.json()['day_detail']['meal_warnings'])


@pytest.mark.asyncio
async def test_known_closed_ai_dinner_recovers_original_actual_plan(case):
    client,draft,url=case
    before=(await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'attractions_order':list('CBA'),'meals':[{'name':'Closed','preferred_slot':'dinner'}]})):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200
    day=response.json()['day_detail']
    for field in ['attractions','meals','timeline_order','day_start_time']:
        assert day[field]==before[field]
    assert any('已保留原景点顺序和餐厅' in n for n in day['meal_adjustments'])
    assert 'Closed' not in day['description']


@pytest.mark.asyncio
async def test_impossible_existing_main_slot_rejects_write(case):
    client,draft,url=case
    row=await trip_draft_service.get_draft(draft)
    detail=DayDetail.model_validate(json.loads(row.days_detail_json)[0]);detail.day_start_time='17:00'
    detail.meals[0].preferred_slot='lunch'
    await trip_draft_service.patch_day_detail(draft,0,detail)
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'meals':[]})):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==422 and '本次重排未保存' in response.json()['detail']
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
async def test_map_or_llm_failure_preserves_all_meals_and_notes(case):
    client,draft,url=case
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({})),patch.object(trip_draft,'compute_day_route',new=AsyncMock(side_effect=ExternalServiceError('amap','路线计算',FailureKind.CONNECTION))):
        assert (await client.post(url+'/ai-rearrange',json={})).status_code==503
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(side_effect=ExternalServiceError('llm','AI重排',FailureKind.TIMEOUT))):
        assert (await client.post(url+'/ai-rearrange',json={})).status_code==504
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
async def test_shared_deadline_cancels_route_and_saves_nothing(case):
    client,draft,url=case
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    cancelled=asyncio.Event()
    async def slow(*args):
        try:await asyncio.sleep(10)
        finally:cancelled.set()
    @asynccontextmanager
    async def short(_):
        async with operation_deadline(.02):yield
    with patch.object(trip_draft,'operation_deadline',new=short),patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({})),patch.object(trip_draft,'compute_day_route',side_effect=slow):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==504 and cancelled.is_set()
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
async def test_late_ai_cannot_recreate_concurrently_deleted_dinner(case):
    client,draft,url=case
    entered,resume=asyncio.Event(),asyncio.Event()
    async def delayed(*args,**kwargs):entered.set();await resume.wait();return SimpleNamespace(content='{"meals":[]}')
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',side_effect=delayed):
        task=asyncio.create_task(client.post(url+'/ai-rearrange',json={}))
        await asyncio.wait_for(entered.wait(),2)
        newer=await client.post(url+'/recompute',json={'meals':[]})
        assert newer.status_code==200
        snapshot=(await trip_draft_service.get_draft(draft)).days_detail_json
        resume.set();late=await task
    assert late.status_code==409
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot


@pytest.mark.asyncio
async def test_recovered_main_notes_and_prices_finalize_once(case):
    client,draft,url=case
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'meals':[{'name':'Lunch','preferred_slot':'lunch'}]})):
        saved=(await client.post(url+'/ai-rearrange',json={})).json()['day_detail']
    with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        response=await client.post(f'/api/trip/draft/{draft}/finalize')
        again=await client.post(f'/api/trip/draft/{draft}/finalize')
    complete=lambda r:next(json.loads(x[6:]) for x in r.text.splitlines() if x.startswith('data: ') and json.loads(x[6:])['type']=='complete')
    first=complete(response)
    assert complete(again)==first
    history=(await client.get(f"/api/trips/{first['trip_id']}")).json()['data']['plan']
    assert history==first['trip_plan']
    assert history['days'][0]['meal_adjustments']==saved['meal_adjustments']
    assert history['days'][0]['description']==saved['description']
    assert history['budget']['total_meals']==50


@pytest.mark.asyncio
async def test_actual_long_route_rejects_nominal_lunch_and_bounds_recovery(case):
    client,draft,url=case
    before=(await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]
    routes=AsyncMock(side_effect=[[{'from_name':'C','to_name':'B','duration':'400分钟'}],[]])
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'attractions_order':list('CBA'),'meals':[]})),patch.object(trip_draft,'compute_day_route',new=routes):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200
    assert routes.await_count==2
    day=response.json()['day_detail']
    assert day['attractions']==before['attractions'] and day['meals']==before['meals']
    assert any('已保留原景点顺序' in x for x in day['meal_adjustments'])


@pytest.mark.asyncio
async def test_ai_before_first_assembly_uses_current_trip_default_main_slots(case):
    from app.database import async_session
    from app.models.db_models import TripDraft
    client,draft,url=case
    async with async_session() as session:
        row=await session.get(TripDraft,draft);row.days_detail_json='[null]';await session.commit()
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=fake({'meals':[]})):
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200
    day=response.json()['day_detail']
    assert {m['type'] for m in day['meals']} == {'lunch','dinner'}
    assert day['is_assembled'] is True


@pytest.mark.asyncio
async def test_manual_replacement_rejects_closed_window_and_preserves_saved_json(case):
    client,draft,url=case
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    response=await client.post(url+'/recompute',json={'meals':[{'name':'Closed','category':'main','type':'dinner','preferred_slot':'dinner','insert_after':'C','open_hours':'24小时','avg_cost':0}]})
    assert response.status_code==409
    assert '本次修改未保存' in response.json()['detail']
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
async def test_dining_refresh_uses_current_gap_without_changing_saved_meals(case):
    client,draft,url=case
    row=await trip_draft_service.get_draft(draft); before=row.days_detail_json
    pool={'main':[{'name':'新店','category':'main','open_hours':'10:00-22:00','avg_cost':55}]}
    search=AsyncMock(return_value=pool)
    with patch('app.agents.langgraph_agent.nodes.food.search_dining_for_day',new=search):
        response=await client.post(url+'/dining-options')
    assert response.status_code==200
    assert response.json()['retained_categories']==['cafe']
    assert search.call_args.args[3]==json.loads(before)[0]['timeline_schedule']
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before
    with patch('app.agents.langgraph_agent.nodes.food.search_dining_for_day',new=AsyncMock(return_value={} )):
        response=await client.post(url+'/dining-options')
    assert response.status_code==503
    assert json.loads((await trip_draft_service.get_draft(draft)).dining_pool_json)[0]['main'][0]['name']=='新店'


@pytest.mark.asyncio
async def test_late_dining_query_cannot_publish_stale_recommendations(case):
    client,draft,url=case
    entered,resume=asyncio.Event(),asyncio.Event()
    async def query(*args):
        entered.set();await resume.wait();return {'main':[{'name':'旧位置店','category':'main'}]}
    before=(await trip_draft_service.get_draft(draft)).dining_pool_json
    with patch('app.agents.langgraph_agent.nodes.food.search_dining_for_day',side_effect=query):
        task=asyncio.create_task(client.post(url+'/dining-options'))
        await asyncio.wait_for(entered.wait(),2)
        assert (await client.post(url+'/recompute',json={'removed_attraction_names':['A']})).status_code==200
        resume.set();response=await task
    assert response.status_code==409
    assert (await trip_draft_service.get_draft(draft)).dining_pool_json==before
