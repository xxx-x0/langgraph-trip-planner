"""Synthetic model/POIs/routes for whole-trip pace, protection and atomicity."""
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import init_db, async_session
from app.models.db_models import TripDraft
from app.models.schemas import TripRequest, DayDetail, Attraction, Meal, Hotel, MacroPlan
from app.models.journey import Journey
from app.services import trip_draft_service as drafts, trip_coordination as coordination, single_journey_adjustment as adjustment
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from app.services.external_calls import ExternalServiceError, FailureKind
from app.api.routes.trip_draft import _load_payload
from app.models.rest import RestPeriod


def restaurant(name):
    return dict(name=name,poi_id=name,category='main',location={'longitude':120.01,'latitude':30},
                avg_cost=40,open_hours='08:00-22:00',source='nearby')


def journey():
    base=dict(mode='train',passengers=1,transfer_before_minutes=0,station_buffer_minutes=0,
              transfer_after_minutes=0,baggage_minutes=0,lodging_buffer_minutes=0)
    return Journey(origin_city='上海',return_city='上海',
        outbound=base|dict(departure_station='上海',arrival_station='温州',departure_time='2026-11-08T07:00',arrival_time='2026-11-08T10:00'),
        inbound=base|dict(departure_station='温州',arrival_station='上海',departure_time='2026-11-09T18:30',arrival_time='2026-11-09T21:00'))


async def seed(count=5,protected=False):
    req=TripRequest(city='温州',start_date='2026-11-08',end_date='2026-11-09',travel_days=2,
        accommodation='酒店',transportation='公共交通',journey=journey())
    attractions=[Attraction(name=f'景点{i}',poi_id=str(i),address='模拟',description='模拟',visit_duration=120,
        location={'longitude':120+i*.002,'latitude':30},open_hours='08:00-21:00') for i in range(count)]
    groups=[attractions[:-1],attractions[-1:]]
    clusters=[[adjustment.as_cluster(a) for a in g] for g in groups]
    hotel=Hotel(name='住宿',location={'longitude':120,'latitude':30})
    macro=MacroPlan(city='温州',total_days=2,days=[dict(day_index=i,date=f'2026-11-0{8+i}',attraction_names=[a.name for a in g]) for i,g in enumerate(groups)])
    ident=await drafts.create_draft(user_id='isolated-coordination',request=req,selected_attractions=[a.model_dump() for a in attractions],
        macro_plan=macro,clusters_data=clusters,hotels_by_day=[[hotel.model_dump()],[hotel.model_dump()]],
        dining_pool=[{'main':[restaurant('午餐店'),restaurant('晚餐店')]} for _ in range(2)],weather_info=[])
    for i,g in enumerate(groups):
        d=DayDetail(day_index=i,date=macro.days[i].date,attractions=g,hotel=hotel,day_start_time='10:00' if i==0 else '08:00',
            is_assembled=True,overnight_stay=i==0,removed_attraction_names=['已删除的地方'],
            timeline_order=[dict(kind='hotel',ref_name='住宿',phase='start'),*[dict(kind='attraction',ref_name=a.name) for a in g],dict(kind='hotel',ref_name='住宿',phase='end')])
        if protected and i==0:
            d.locked_attraction_names=['景点0']
            d.meals=[Meal(name='手选午餐',type='lunch',preferred_slot='lunch',schedule_mode='manual',open_hours='08:00-21:00',
                location={'longitude':120,'latitude':30},avg_cost=80,source='user_custom')]
            d.timeline_order.insert(2,dict(kind='meal',ref_name='手选午餐'))
        schedule_day(d);await drafts.patch_day_detail(ident,i,d)
    return ident


@pytest_asyncio.fixture
async def client(monkeypatch):
    await init_db();adjustment._proposals.clear()
    monkeypatch.setattr(coordination,'get_llm',lambda:object())
    monkeypatch.setattr(coordination,'invoke_structured_or_json',AsyncMock(side_effect=ValueError('synthetic fallback')))
    monkeypatch.setattr(coordination,'search_dining_for_day',AsyncMock(return_value={'main':[restaurant('午餐店'),restaurant('晚餐店')]}))
    async def routes(points,*args):
        return [dict(from_name=points[0]['name'],to_name=points[1]['name'],duration='10分钟',distance='1公里',detail='模拟地图路线')]
    monkeypatch.setattr(coordination,'compute_route_segments',routes)
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as c: yield c


@pytest.mark.asyncio
async def test_coordinates_both_days_with_real_meals_breaks_margin_and_refresh(client):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment'
    before=adjustment.snapshot(await drafts.get_draft(ident))
    body=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True)
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    p=response.json();assert not p['unassigned_attractions']
    assert adjustment.snapshot(await drafts.get_draft(ident))==before
    assert p['coordination']['selection_method']=='rules'
    assert sorted(a['name'] for d in p['days_detail'] for a in d['attractions'])==[f'景点{i}' for i in range(5)]
    assert len(p['days_detail'][0]['attractions'])<4
    for d in p['coordination']['days']:
        assert d['end_time']<='21:00' and d['visit_minutes']<=360 and d['rest_minutes']>=30 and d['meal_count']==2
    assert p['coordination']['days'][1]['return_margin_minutes']>=30
    assert p['days_detail'][1]['meals'][-1]['type']=='dinner'
    assert all(a['visit_duration']==120 for d in p['days_detail'] for a in d['attractions'])
    confirm=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True)
    assert (await client.post(url,json=confirm)).status_code==200
    saved=(await client.get('/api/trip/draft/'+ident)).json()
    assert saved['request']['coordination_policy']['generated_rests']
    assert len(saved['request']['rest_periods'])==2
    assert [d['timeline_schedule'] for d in saved['days_detail']]==[d['timeline_schedule'] for d in p['days_detail']]
    assert all(d['removed_attraction_names']==['已删除的地方'] for d in saved['days_detail'])
    assert all(m['poi_id'] in [c['poi_id'] for c in saved['days'][i]['dining_pool']['main']] for i,d in enumerate(saved['days_detail']) for m in d['meals'])


@pytest.mark.asyncio
async def test_over_capacity_keeps_pending_visits_instead_of_late_night_or_dropping_meals(client):
    ident=await seed(7,protected=True)
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert response.status_code==200,response.text
    p=response.json();assert p['unassigned_attractions']
    assigned=[a['name'] for d in p['days_detail'] for a in d['attractions']]
    pending=[a['name'] for a in p['unassigned_attractions']]
    assert sorted(assigned+pending)==[f'景点{i}' for i in range(7)] and not set(assigned)&set(pending)
    first=p['days_detail'][0];assert first['attractions'][0]['name']=='景点0'
    assert next(m for m in first['meals'] if m['name']=='手选午餐')['avg_cost']==80
    assert first['timeline_order'][2]==dict(kind='meal',ref_name='手选午餐')
    assert all(d['meal_count']==2 and d['rest_minutes']>=30 for d in p['coordination']['days'])
    assert all(a['cluster']['visit_minutes']==120 for a in p['unassigned_attractions'])


@pytest.mark.asyncio
async def test_model_unknown_ids_fall_back_and_map_failure_never_becomes_pending(client,monkeypatch):
    ident=await seed();before=adjustment.snapshot(await drafts.get_draft(ident))
    monkeypatch.setattr(coordination,'invoke_structured_or_json',AsyncMock(return_value=coordination.SuggestedTrip(days=[dict(attraction_ids=['invented'])])))
    monkeypatch.setattr(coordination,'compute_route_segments',AsyncMock(side_effect=ExternalServiceError('amap','test',FailureKind.UNAVAILABLE)))
    r=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert r.status_code>=400
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_whole_trip_preview_cas_rejects_changed_pool(client):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment'
    body=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True)
    r=await client.post(url,json=body);assert r.status_code==200,r.text
    p=r.json()
    async with async_session() as session:
        record=await session.get(TripDraft,ident);record.dining_pool_json='[{}]';await session.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident))
    saved=await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))
    assert saved.status_code==409 and adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_valid_model_priorities_never_supply_place_facts(client,monkeypatch):
    ident=await seed(7)
    # Every ID is real; the model can prioritize, but cannot change durations,
    # candidate coordinates, prices, or the code's meal/rest checks.
    monkeypatch.setattr(coordination,'invoke_structured_or_json',AsyncMock(return_value=coordination.SuggestedTrip(
        days=[dict(attraction_ids=['a0','a1','a2']),dict(attraction_ids=['a3','a4','a5','a6'])],
        priority_ids=['a6','a0','a1','a2','a3','a4','a5'])))
    r=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert r.status_code==200,r.text
    p=r.json();assert p['coordination']['selection_method']=='ai'
    assert '景点6' not in [x['name'] for x in p['unassigned_attractions']]
    assert all(a['visit_duration']==120 for d in p['days_detail'] for a in d['attractions'])
    assert all(m['avg_cost']==40 and m['location']==restaurant(m['name'])['location'] for d in p['days_detail'] for m in d['meals'])


@pytest.mark.asyncio
@pytest.mark.parametrize('arrival,expected_start',[('2026-11-08T23:00','09:00'),('2026-11-09T08:00','08:00')])
async def test_late_arrival_and_overnight_train_do_not_block_the_next_whole_day(client,arrival,expected_start):
    ident=await seed(2);j=journey();j.outbound.arrival_time=arrival
    r=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=j.model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert r.status_code==200,r.text
    p=r.json();assert not p['days_detail'][0]['timeline_schedule']
    assert len(p['days_detail'][1]['attractions'])==2 and not p['unassigned_attractions']
    assert p['days_detail'][1]['day_start_time']==expected_start
    assert p['coordination']['days'][1]['meal_count']==2


@pytest.mark.asyncio
async def test_user_rest_and_fixed_appointment_survive_whole_trip_coordination(client):
    ident=await seed(2)
    rest=RestPeriod(id='user-lunch-break',date='2026-11-08',start_time='14:00',end_time='14:40',label='固定休息')
    async with async_session() as session:
        record=await session.get(TripDraft,ident);raw=json.loads(record.request_json);raw['rest_periods']=[rest.model_dump(mode='json')]
        # A previous generated break was edited by the user; it is now protected.
        raw['coordination_policy']={'generated_rests':[rest.model_copy(update={'end_time':'14:30'}).model_dump(mode='json')]}
        record.request_json=json.dumps(raw)
        days=json.loads(record.days_detail_json);days[0]['time_constraints']={'appointments':[dict(kind='attraction',ref_name='景点0',start_time='10:30')]}
        record.days_detail_json=json.dumps(days);await session.commit()
    r=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert r.status_code==200,r.text
    first=r.json()['days_detail'][0]
    assert next(x for x in first['timeline_schedule'] if x.get('rest_id')==rest.id)['duration']==40
    assert next(x for x in first['timeline_schedule'] if x['ref_name']=='景点0')['start_time']=='10:30'


@pytest.mark.asyncio
async def test_fixed_impossible_plan_is_rejected_without_partial_write(client):
    ident=await seed(7,protected=True)
    async with async_session() as session:
        record=await session.get(TripDraft,ident);days=json.loads(record.days_detail_json)
        days[0]['locked_attraction_names']=[a['name'] for a in days[0]['attractions']]
        record.days_detail_json=json.dumps(days);await session.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident))
    r=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True))
    assert r.status_code==422 and adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_recompute_retains_coordinated_meals_breaks_and_rejects_lost_margin(client,monkeypatch):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment'
    body=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True)
    r=await client.post(url,json=body);assert r.status_code==200,r.text
    p=r.json();assert (await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))).status_code==200
    saved=_load_payload(await drafts.get_draft(ident));second=saved.days_detail[1]
    # Same verified facts should preserve the early dinner's chosen insertion gap.
    monkeypatch.setattr('app.api.routes.trip_draft.compute_day_route',AsyncMock(return_value=second.route_segments))
    r=await client.post(f'/api/trip/draft/{ident}/day/1/recompute',json={})
    assert r.status_code==200,r.text
    d=r.json()['day_detail'];assert d['timeline_schedule']==second.model_dump(mode='json')['timeline_schedule']
    before=adjustment.snapshot(await drafts.get_draft(ident))
    r=await client.post(f'/api/trip/draft/{ident}/day/1/recompute',json={'day_start_time':'18:00'})
    assert r.status_code==409 and adjustment.snapshot(await drafts.get_draft(ident))==before
    monkeypatch.setattr('app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences',AsyncMock(return_value=None))
    result=await client.post(f'/api/trip/draft/{ident}/finalize')
    events=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    complete=next((e for e in events if e.get('type')=='complete'),None)
    assert complete is not None,result.text
    # Read-only projection must retain early-dinner policy and the same timeline.
    from app.agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
    from app.models.schemas import TripPlan
    plan=TripPlan.model_validate(complete['trip_plan'])
    refresh_trip_descriptions(plan)
    assert plan.days[1].coordination_policy and plan.days[1].timeline_schedule==second.timeline_schedule
    assert '预计18:00结束市内安排' in plan.days[1].description
    assert '可以先缩短' not in plan.days[1].description


@pytest.mark.asyncio
async def test_route_delay_moves_auto_break_after_the_meal_and_saves_rest_atomically(client,monkeypatch):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment'
    body=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True)
    r=await client.post(url,json=body);p=r.json();assert r.status_code==200,r.text
    await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))
    saved=_load_payload(await drafts.get_draft(ident));day=saved.days_detail[0]
    changed=[r.model_copy(deep=True) for r in day.route_segments]
    changed[0].duration=f'{coordination.route_minutes(changed[0].duration)+5}分钟'
    monkeypatch.setattr('app.api.routes.trip_draft.compute_day_route',AsyncMock(return_value=changed))
    result=await client.post(f'/api/trip/draft/{ident}/day/0/recompute',json={})
    assert result.status_code==200,result.text
    reread=(await client.get('/api/trip/draft/'+ident)).json();d=reread['days_detail'][0]
    assert d['timeline_schedule']==result.json()['day_detail']['timeline_schedule']
    assert sum(x['duration'] for x in d['timeline_schedule'] if x['kind']=='rest')==30
    assert len([x for x in d['timeline_schedule'] if x['kind']=='meal' and x['duration']==60])==2
    assert all(r in reread['request']['rest_periods'] and r in reread['request']['coordination_policy']['generated_rests'] for r in d['rest_periods'])
    assert d['rest_periods']!=day.model_dump(mode='json')['rest_periods']


@pytest.mark.asyncio
async def test_pending_placement_cannot_bypass_coordinated_pace(client,monkeypatch):
    ident=await seed(7);url=f'/api/trip/draft/{ident}/journey-adjustment'
    body=dict(journey=journey().model_dump(mode='json'),coordinate_trip=True,refill_meals=True)
    p=(await client.post(url,json=body)).json();assert p['unassigned_attractions']
    await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))
    async def routes(day,*args):
        return [dict(from_name=a['ref_name'],to_name=b['ref_name'],duration='10分钟') for a,b in zip(day.timeline_order,day.timeline_order[1:]) if a['ref_name']!=b['ref_name']]
    monkeypatch.setattr(adjustment,'compute_day_route',routes)
    before=adjustment.snapshot(await drafts.get_draft(ident))
    full=max(range(2),key=lambda i:len(p['days_detail'][i]['attractions']))
    result=await client.post(url,json={'journey':body['journey'],'placements':[dict(id=p['unassigned_attractions'][0]['id'],day_index=full)]})
    assert result.status_code==422 and adjustment.snapshot(await drafts.get_draft(ident))==before
