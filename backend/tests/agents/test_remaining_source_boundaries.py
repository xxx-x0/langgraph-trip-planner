"""Synthetic boundary checks; no real model, map, hotel or business database."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.models.schemas import TripRequest, DayPlan, DayDetail, TripPlan, Attraction, Meal, Budget, CompanionInfo
from app.models.journey import Journey, JourneyLeg
from app.agents.langgraph_agent.assemble.narrative import refresh_day_description
from tests.api.test_draft_endpoints import client, _seed_draft


def request():
    return TripRequest(city='北京',start_date='2026-06-01',end_date='2026-06-02',travel_days=2,
                       transportation='公共交通',accommodation='酒店',companions=CompanionInfo(type='friends',count=3))


def plan():
    return TripPlan(city='北京',start_date='2026-06-01',end_date='2026-06-01',overall_suggestions='',
        days=[DayPlan(date='2026-06-01',day_index=0,description='旧文',transportation='步行',accommodation='酒店')])


@pytest.mark.parametrize('endpoint',['recompute','assemble?force=true'])
@pytest.mark.asyncio
async def test_unknown_manual_meal_cannot_impersonate_provider_recommendation(client,endpoint):
    from app.services import trip_draft_service
    draft=await _seed_draft()
    body={'meals':[{'name':'用户自选店','type':'lunch','category':'main','insert_after':'A',
                   'source':'nearby','recommendation':{'reasons':['provider verified']},'estimated_cost':20}]}
    with patch('app.api.routes.trip_draft.compute_day_route',new=AsyncMock(return_value=[])):
        response=await client.post(f'/api/trip/draft/{draft}/day/0/'+endpoint,json=body)
    assert response.status_code==200,response.text
    meal=response.json()['day_detail']['meals'][0]
    assert meal['source']=='user_custom' and meal['recommendation']=={}
    stored=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    assert stored['meals'][0]['source']=='user_custom'


@pytest.mark.asyncio
async def test_known_candidate_retains_server_source_price_and_location(client):
    from app.models.schemas import DiningPoolDay
    pool=DiningPoolDay(main=[dict(name='候选店',category='main',source='nearby',avg_cost=68,
        location={'longitude':116.4,'latitude':39.9},open_hours='10:00-23:00')]).model_dump(mode='json')
    draft=await _seed_draft(dining_pool=[pool,pool])
    body={'meals':[dict(name='候选店',type='lunch',category='main',insert_after='A',source='user_custom',
        estimated_cost=999,location={'longitude':1,'latitude':1},recommendation={'reasons':['spoof']})]}
    with patch('app.api.routes.trip_draft.compute_day_route',new=AsyncMock(return_value=[])):
        response=await client.post(f'/api/trip/draft/{draft}/day/0/recompute',json=body)
    assert response.status_code==200,response.text
    meal=response.json()['day_detail']['meals'][0]
    assert meal['source']=='nearby' and meal['estimated_cost']==68
    assert meal['location']==pool['main'][0]['location']
    assert 'spoof' not in str(meal['recommendation'])


@pytest.mark.parametrize('text,expected',[('想慢游',True),('不想轻松，只想赶路',False),('不要慢慢逛',False),('不需要轻松，但想慢游',True)])
def test_current_intent_guidance_respects_negation_and_does_not_edit_arrangements(text,expected):
    d=DayDetail(day_index=0,date='2026-06-01',attractions=[Attraction(name='A',address='',description='',visit_duration=60)],
        trip_intent={'free_text_input':text},locked_attraction_names=['A'],removed_attraction_names=['B'])
    before=d.model_dump(exclude={'description','description_source','pending_confirmations'})
    with patch('app.services.llm_service.get_llm',side_effect=AssertionError('no model')):
        result=refresh_day_description(d)
    assert ('慢慢逛' in result)==expected
    assert d.model_dump(exclude={'description','description_source','pending_confirmations'})==before


@pytest.mark.parametrize('intent,phrase',[({'companion_type':'elderly'},'长辈同行'),({'children':True},'带孩子'),({'companion_count':1},'一个人出行')])
def test_only_explicit_companion_facts_appear(intent,phrase):
    d=DayDetail(day_index=0,date='2026-06-01',trip_intent=intent)
    assert phrase in refresh_day_description(d)
    d.trip_intent={};assert phrase not in refresh_day_description(d)


@pytest.mark.asyncio
async def test_compatibility_reducer_keeps_journey_costs_and_does_not_open_legacy_api(client):
    from app.agents.langgraph_agent.nodes.generate import reduce_assemble_node
    req=request();req.journey=Journey(origin_city='上海',return_city='上海',outbound=JourneyLeg(mode='train',
        departure_station='上海',arrival_station='北京',departure_time='2026-06-01T07:00',arrival_time='2026-06-01T09:00',
        passengers=3,ticket_total=200,price_source='user_quote',extras_total=0,price_note='隔离模拟报价',quoted_at='2026-05-31T10:00'))
    days=[DayPlan(date=date,day_index=i,description='',transportation='公共交通',accommodation='酒店')
          for i,date in enumerate([req.start_date,req.end_date])]
    with patch('app.agents.langgraph_agent.nodes.generate._build_weather_list',new=AsyncMock(return_value=[])):
        result=await reduce_assemble_node({'request':req,'day_plans':days})
    saved=result['trip_plan'];assert saved.journey==req.journey
    assert saved.days[0].travel_window['intercity_cost']==200
    assert saved.budget.total_intercity==200
    assert saved.days[0].overnight_stay and not saved.days[1].overnight_stay
    response=await client.post('/api/trip/plan',json=req.model_dump(mode='json'))
    assert response.status_code==422 and '草稿' in response.json()['detail']


@pytest.mark.asyncio
async def test_legacy_hotel_fallback_does_not_send_unsupported_amenity_switches():
    from app.agents.langgraph_agent.nodes.search import search_hotel_node
    tool=object();service=SimpleNamespace(get_tools=AsyncMock(return_value=[]),get_tool=AsyncMock(return_value=tool))
    fake_llm=SimpleNamespace(bind_tools=lambda tools:object())
    with patch('app.services.aigohotel_mcp_service.get_aigohotel_service',return_value=service), \
         patch('app.agents.langgraph_agent.nodes.search.get_llm',return_value=fake_llm), \
         patch('app.agents.langgraph_agent.nodes.search._invoke_llm_with_retry',new=AsyncMock(return_value=SimpleNamespace(tool_calls=[]))), \
         patch('app.agents.langgraph_agent.nodes.search._invoke_tool_with_retry',new=AsyncMock(return_value='synthetic result')) as invoke, \
         patch('app.agents.langgraph_agent.nodes.search.analyze_free_text',new=AsyncMock(return_value={'attractions':['A']})):
        result=await search_hotel_node({'request':request()})
    assert result['hotels_info'] and invoke.await_count==2
    for call in invoke.await_args_list:
        assert 'withHotelAmenities' not in call.args[1] and 'withRoomAmenities' not in call.args[1]


# These baseline-preservation probes must fail on unsafe leftover hunks.
@pytest.mark.asyncio
async def test_read_projection_uses_current_party_size_without_writing_saved_json(client):
    from app.api.routes.trip_draft import _load_payload
    from app.services import trip_draft_service
    draft=await _seed_draft();record=await trip_draft_service.get_draft(draft)
    record.request_json=request().model_dump_json()
    detail=DayDetail(day_index=0,date='2026-06-01',attractions=[Attraction(name='A',address='',description='',visit_duration=60,ticket_price=10)],
                     meals=[Meal(name='自选店',type='lunch',estimated_cost=20)])
    raw=detail.model_dump(mode='json');raw.pop('companion_count');record.days_detail_json=json.dumps([raw,None])
    before=(record.request_json,record.days_detail_json)
    projected=_load_payload(record).days_detail[0]
    assert projected.companion_count==3
    assert projected.day_budget.total_attractions==30 and projected.day_budget.total_meals==60
    assert (record.request_json,record.days_detail_json)==before


def test_legacy_source_labels_remain_readable_and_are_reprojected_as_facts():
    from app.services.trip_history_service import project_saved_narratives
    DayDetail(day_index=0,date='2026-06-01',description_source='legacy_v0')
    raw=plan().model_dump(mode='json');raw['narrative_source']='legacy_v0';raw['days'][0]['description_source']='legacy_v0'
    raw['extra_saved_field']='preserve'
    projected=project_saved_narratives(copy.deepcopy(raw))
    assert projected['narrative_source']=='itinerary_facts_v1'
    assert projected['extra_saved_field']=='preserve'


def test_history_projection_refreshes_hotel_timeline_cost_alongside_budget():
    from app.services.trip_history_service import project_saved_narratives
    raw=plan().model_dump(mode='json');raw['days'][0].update(hotel={'name':'旧酒店','estimated_cost':999},overnight_stay=False,
        timeline_schedule=[dict(kind='hotel',ref_name='旧酒店',start_time='08:00',end_time='08:00',start_minutes=480,end_minutes=480,duration=0,cost=999)])
    raw['budget']=Budget(total_hotels=999,total=999,is_complete=False).model_dump(mode='json')
    projected=project_saved_narratives(copy.deepcopy(raw))
    assert projected['budget']['total_hotels']==0
    assert projected['days'][0]['timeline_schedule'][0]['cost'] is None
    assert raw['days'][0]['timeline_schedule'][0]['cost']==999


@pytest.mark.asyncio
async def test_finalize_projection_does_not_swallow_internal_errors():
    from app.agents.langgraph_agent.finalize.pipeline import _run_global_synthesizer
    with patch('app.agents.langgraph_agent.assemble.narrative.refresh_day_description',side_effect=RuntimeError('projection bug')):
        with pytest.raises(RuntimeError,match='projection bug'):
            await _run_global_synthesizer(plan(),'')


@pytest.mark.asyncio
async def test_day_save_keeps_authoritative_request_intent():
    from app.api.routes.trip_draft import _save_day_detail
    d=DayDetail(day_index=0,date='2026-06-01',trip_intent={'companion_type':'elderly'})
    req=request();req.free_text_input='想慢游'
    with patch('app.services.trip_draft_service.patch_day_detail',new=AsyncMock()) as save:
        await _save_day_detail('fixture',0,d,expected_day=None,expected_request=req.model_dump_json(),weather=None)
    assert d.trip_intent['companion_type']=='friends' and d.trip_intent['companion_count']==3
    assert d.trip_intent['free_text_input']=='想慢游'
    save.assert_awaited_once()
