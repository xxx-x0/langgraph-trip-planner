"""Isolated schedule adoption and save boundaries, mocked routes, no live services."""
import json
from unittest.mock import AsyncMock, patch
import pytest
from tests.api.test_narrative_consistency import case
from app.api.routes import trip_draft
from app.database import async_session
from app.models.db_models import TripDraft
from app.models.schemas import DayDetail, RouteSegment, TripRequest
from app.services import trip_draft_service
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from app.services.journey_service import conflicts

async def seed(draft, *, rest=None, window=None):
    async with async_session() as session:
        record=await session.get(TripDraft,draft)
        request=json.loads(record.request_json)
        request['rest_periods']=rest or []
        if window: request['journey']=window
        record.request_json=json.dumps(request,ensure_ascii=False)
        await session.commit()

async def sparse(client,url):
    response=await client.post(url+'/recompute',json={'day_start_time':'08:00','locked_attraction_names':['乙园'],'removed_attraction_names':['丙园'],
        'meals':[{'name':'午饭馆','type':'lunch','category':'main','preferred_slot':'lunch','insert_after':'乙园','schedule_mode':'manual'},
                 {'name':'晚饭馆','type':'dinner','category':'main','preferred_slot':'dinner','insert_after':'乙园','schedule_mode':'manual','open_hours':'10:00-22:00'}]})
    assert response.status_code==200,response.text
    return response.json()['day_detail']

@pytest.mark.asyncio
async def test_opt_in_api_recompute_preserves_saved_intent_and_final_readback(case):
    client,draft,url=case
    before=await sparse(client,url)
    assert before['day_start_time']=='08:00' and before['schedule_suggestion']['saved_minutes']>0
    oldrecord=await trip_draft_service.get_draft(draft)
    read=await client.get(f'/api/trip/draft/{draft}')
    assert read.status_code==200
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==oldrecord.days_detail_json
    start=before['schedule_suggestion']['day_start_time']
    response=await client.post(url+'/recompute',json={'day_start_time':start})
    assert response.status_code==200,response.text
    after=response.json()['day_detail']
    assert after['day_start_time']==start
    for key in ['attractions','meals','locked_attraction_names','removed_attraction_names','timeline_order']:
        assert after[key]==before[key],key
    assert sum(x['duration'] for x in after['timeline_schedule'] if x['kind'] in {'free_time','wait'}) < sum(x['duration'] for x in before['timeline_schedule'] if x['kind'] in {'free_time','wait'})
    with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        done=await client.post(f'/api/trip/draft/{draft}/finalize')
    event=next(json.loads(l[6:]) for l in done.text.splitlines() if l.startswith('data: ') and json.loads(l[6:]).get('type')=='complete')
    saved=(await client.get(f"/api/trips/{event['trip_id']}")).json()['data']['plan']['days'][0]
    assert saved['day_start_time']==start and saved['timeline_schedule']==after['timeline_schedule']
    assert saved['locked_attraction_names']==before['locked_attraction_names']

@pytest.mark.asyncio
async def test_rest_blocks_suggestion_and_failed_shift_keeps_saved_day(case):
    client,draft,url=case
    await sparse(client,url)
    rest=[{'id':'r','date':'2026-10-15','start_time':'14:00','end_time':'16:00','label':'固定午休'}]
    await seed(draft,rest=rest)
    response=await client.post(url+'/recompute',json={})
    assert response.status_code==200,response.text
    detail=response.json()['day_detail'];assert detail['schedule_suggestion']=={}
    assert any(x['kind']=='rest' and x['start_time']=='14:00' and x['end_time']=='16:00' for x in detail['timeline_schedule'])
    snapshot=await trip_draft_service.get_draft(draft)
    failed=await client.post(url+'/recompute',json={'day_start_time':'15:00'})
    assert failed.status_code==409 and '早于' in failed.text
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot.days_detail_json

@pytest.mark.asyncio
async def test_new_route_cannot_save_past_return_window(case):
    client,draft,url=case
    before=await sparse(client,url)
    journey={'origin_city':'上海','return_city':'上海','inbound':{'departure_station':'苏州','arrival_station':'上海','departure_time':'2026-10-15T21:00','arrival_time':'2026-10-16T00:10','booking_status':'booked','passengers':1}}
    await seed(draft,window=journey)
    snapshot=await trip_draft_service.get_draft(draft)
    with patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[RouteSegment(from_name='乙园',to_name='午饭馆',mode='步行',duration='8小时',distance='1公里')])):
        response=await client.post(url+'/recompute',json={'day_start_time':before['schedule_suggestion']['day_start_time']})
    assert response.status_code==409,response.text
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot.days_detail_json


def shape():
    from app.models.schemas import DraftDayContext,Attraction
    from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
    ctx=DraftDayContext(day_index=0,date='2026-10-15',day_start_time='08:00',attractions=[Attraction(name=n,address='',description='',visit_duration=90) for n in ['甲','乙']])
    return rule_assemble_day_timeline(ctx,{'meals':[{'name':'午','type':'lunch','preferred_slot':'lunch','insert_after':'乙','open_hours':'11:00-22:00'}, {'name':'晚','type':'dinner','preferred_slot':'dinner','insert_after':'乙','open_hours':'11:00-22:00'}]})


def test_return_window_and_known_closing_remove_otherwise_valid_suggestion():
    free=shape();schedule_day(free);assert free.schedule_suggestion
    # The same candidate must be rejected when the return is too early.
    blocked=shape();blocked.travel_window={'start_minutes':0,'end_minutes':1000};schedule_day(blocked)
    assert blocked.schedule_suggestion=={}
    # Every 30-minute delay crosses the known closing time of the first attraction.
    closing=shape();closing.attractions[0].open_hours='08:00-09:30';schedule_day(closing)
    assert closing.schedule_suggestion=={}


@pytest.mark.asyncio
async def test_opt_in_rechecks_known_hours_after_actual_route_changes(case):
    client,draft,url=case
    before=await sparse(client,url)
    async with async_session() as session:
        record=await session.get(TripDraft,draft)
        clusters=json.loads(record.clusters_data_json)
        for attraction in clusters[0]: attraction['open_hours']='08:00-13:00'
        record.clusters_data_json=json.dumps(clusters)
        await session.commit()
    snapshot=await trip_draft_service.get_draft(draft)
    with patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[RouteSegment(from_name='住处',to_name='甲园',mode='步行',duration='3小时',distance='1公里')])):
        response=await client.post(url+'/recompute',json={'day_start_time':before['schedule_suggestion']['day_start_time']})
    assert response.status_code==409,response.text
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot.days_detail_json


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['assemble?force=true','ai-rearrange','finalize'])
async def test_infeasible_fixed_rest_cannot_write_partial_day_or_history(case,operation):
    from types import SimpleNamespace
    client,draft,url=case
    await sparse(client,url)
    await seed(draft,rest=[{'id':'r','date':'2026-10-15','start_time':'11:00','end_time':'23:30','label':'固定休息'}])
    before=await trip_draft_service.get_draft(draft)
    llm=SimpleNamespace(content=json.dumps({'attractions_order':['甲园','乙园'],'meals':[]}))
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=llm)),patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        response=await client.post(f'/api/trip/draft/{draft}/finalize' if operation=='finalize' else url+'/'+operation,json={})
    if operation=='finalize':
        events=[json.loads(l[6:]) for l in response.text.splitlines() if l.startswith('data: ')]
        assert any(x['type']=='error' for x in events) and not any(x['type']=='complete' for x in events)
    else: assert response.status_code in {409,422},response.text
    after=await trip_draft_service.get_draft(draft)
    assert after.request_json==before.request_json and after.days_detail_json==before.days_detail_json
    assert after.status!='finalized' and after.finalized_trip_id is None

@pytest.mark.asyncio
async def test_finalized_history_keeps_exact_rest_and_reads_do_not_rewrite_draft(case):
    client,draft,url=case
    await sparse(client,url)
    await seed(draft,rest=[{'id':'r','date':'2026-10-15','start_time':'14:00','end_time':'16:00','label':'固定午休'}])
    saved=await client.post(url+'/recompute',json={});assert saved.status_code==200,saved.text
    rest=[x for x in saved.json()['day_detail']['timeline_schedule'] if x['kind']=='rest']
    before=await trip_draft_service.get_draft(draft)
    with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        response=await client.post(f'/api/trip/draft/{draft}/finalize')
    assert any(json.loads(l[6:]).get('type')=='complete' for l in response.text.splitlines() if l.startswith('data: ')),response.text
    event=next(json.loads(l[6:]) for l in response.text.splitlines() if l.startswith('data: ') and json.loads(l[6:]).get('type')=='complete')
    history=(await client.get(f"/api/trips/{event['trip_id']}")).json()['data']['plan']
    assert [x for x in history['days'][0]['timeline_schedule'] if x['kind']=='rest']==rest
    assert history['days'][0]['rest_periods'][0]['id']=='r'
    assert history['days'][0]['locked_attraction_names']==['乙园']
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before.days_detail_json
