"""Synthetic itinerary/map facts; no real ticket, model or supplier requests."""
import asyncio
import json
from datetime import date,timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient,ASGITransport
from app.api.main import app
from app.api.routes.trip_draft import _load_payload
from app.database import init_db,async_session
from app.models.db_models import TripDraft
from app.models.schemas import TripRequest,MacroPlan,DayDetail,Attraction
from app.models.journey import Journey
from app.services import trip_draft_service as drafts,single_journey_adjustment as adjustment
from app.services.journey_service import travel_window
from app.services.journey_planning import reserve_clusters
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def request(planning=False,days=5):
    return TripRequest(city='北京',start_date='2026-11-10',end_date=(date(2026,11,10)+timedelta(days=days-1)).isoformat(),
        travel_days=days,transportation='步行',accommodation='酒店',
        journey=Journey(origin_city='上海',return_city='上海',planning={'arrival_policy':'travel_day','departure_policy':'travel_day'}) if planning else None)


def cluster(name):
    return dict(name=name,address='测试地点',description='模拟事实',longitude=116.4,latitude=39.9,
                visit_minutes=90,ticket_price=None,open_hours='08:00-22:00')


def late_journey():
    return dict(origin_city='上海',return_city='上海',outbound=dict(mode='train',service_number='G1',
        departure_station='上海虹桥',arrival_station='北京南',departure_time='2026-11-10T08:00',arrival_time='2026-11-10T23:00',
        transfer_before_minutes=0,station_buffer_minutes=0,baggage_minutes=0,transfer_after_minutes=0,lodging_buffer_minutes=0,
        price_source='user_estimate',ticket_total=100,extras_total=0))


async def seed(req=None,assemble=True):
    req=req or request()
    clusters=[[cluster('首日园林')],[cluster('次日公园')]]+[[] for _ in range(req.travel_days-2)]
    macro=MacroPlan(city=req.city,total_days=req.travel_days,days=[dict(day_index=i,date=(date.fromisoformat(req.start_date)+timedelta(days=i)).isoformat(),attraction_names=[a['name'] for a in group]) for i,group in enumerate(clusters)])
    ident=await drafts.create_draft(user_id='isolated',request=req,selected_attractions=[a for group in clusters for a in group],
        macro_plan=macro,clusters_data=clusters,hotels_by_day=[],dining_pool=[],weather_info=[])
    if assemble:
        for i,group in enumerate(clusters):
            day=DayDetail(day_index=i,date=macro.days[i].date,day_start_time='08:00',time_constraints={},
                attractions=[Attraction(name=a['name'],address='测试',description='模拟',visit_duration=90,open_hours='08:00-22:00') for a in group],
                timeline_order=[dict(kind='attraction',ref_name=a['name']) for a in group],removed_attraction_names=['早已删除'],is_assembled=True)
            schedule_day(day);await drafts.patch_day_detail(ident,i,day)
    return ident


@pytest_asyncio.fixture
async def client(monkeypatch):
    await init_db();adjustment._proposals.clear()
    async def routes(day,*args):
        return [dict(from_name=a['ref_name'],to_name=b['ref_name'],duration='20分钟',detail='模拟地图路线') for a,b in zip(day.timeline_order,day.timeline_order[1:]) if a['ref_name']!=b['ref_name']]
    monkeypatch.setattr(adjustment,'compute_day_route',routes)
    monkeypatch.setattr('app.services.meal_recovery.search_dining_for_day',AsyncMock(return_value={'main':[]}))
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as c: yield c


def test_reservation_leaves_travel_days_empty_and_actual_leg_overrides_it():
    req=request(True)
    assert travel_window(req,req.start_date)['unavailable']
    assert travel_window(req,req.end_date)['unavailable']
    assert travel_window(req,'2026-11-11')['usable_minutes']==840
    req.journey.planning.arrival_policy='time_window';req.journey.planning.ready_at='2026-11-10T15:00'
    assert travel_window(req,req.start_date)['start_minutes']==900
    req.journey=Journey.model_validate(late_journey()|{'planning':{'arrival_policy':'time_window','ready_at':'2026-11-10T15:00'}})
    assert travel_window(req,req.start_date)['start_minutes']==1380
    assert travel_window(request(),request().start_date)=={'provisional':True,'notes':['抵离交通尚未填写；首末日可用时间暂定']}


def test_reservation_validation_and_explicit_assignment_are_not_silently_relaxed():
    raw=request(True).model_dump(mode='json');raw['journey']['planning'].update(arrival_policy='time_window',ready_at=None)
    with pytest.raises(ValueError):TripRequest.model_validate(raw)
    raw['journey']['planning']['ready_at']='2026-11-09T15:00'
    with pytest.raises(ValueError):TripRequest.model_validate(raw)
    with pytest.raises(HTTPException):reserve_clusters(request(True),[[cluster('A')]],explicit=True)


@pytest.mark.asyncio
async def test_new_skeleton_preserves_pending_instead_of_losing_selected_facts(client):
    ident=await seed(request(True,2),assemble=False)
    record=await drafts.get_draft(ident);before=adjustment.snapshot(record)
    payload=(await client.get('/api/trip/draft/'+ident)).json()
    assert all(not c for c in json.loads(record.clusters_data_json))
    assert all(not d['attraction_names'] for d in payload['macro_plan']['days'])
    assert {a['name'] for a in payload['unassigned_attractions']}=={'首日园林','次日公园'}
    assert adjustment.snapshot(await drafts.get_draft(ident))==before
    final=await client.post(f'/api/trip/draft/{ident}/finalize')
    assert '还有待安排景点' in final.text and '"type": "complete"' not in final.text
    body=dict(journey=payload['request']['journey'],discard_ids=[a['id'] for a in payload['unassigned_attractions']])
    preview=(await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=body)).json()
    assert not preview['unassigned_attractions']
    saved=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True))
    assert saved.status_code==200,saved.text
    assert len(json.loads((await drafts.get_draft(ident)).request_json)['_transport_discarded'])==2


@pytest.mark.asyncio
async def test_transport_preview_moves_across_dates_and_cas_saves_all_sources(client):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment';body=dict(journey=late_journey())
    before=adjustment.snapshot(await drafts.get_draft(ident))
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    p=response.json();assert adjustment.snapshot(await drafts.get_draft(ident))==before
    assert not p['days_detail'][0]['attractions'] and not p['days_detail'][0]['timeline_schedule']
    assert any('移至' in x for x in p['changes']) and not p['unassigned_attractions']
    confirm=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'])
    assert (await client.post(url,json=confirm)).status_code==409
    response=await client.post(url,json=confirm|{'acknowledge_adjustments':True});assert response.status_code==200,response.text
    saved=await drafts.get_draft(ident);loaded=_load_payload(saved)
    assert not loaded.days[0].attractions
    target=next(d for d in loaded.days_detail if d and any(a.name=='首日园林' for a in d.attractions))
    assert target.day_index!=0 and any(a.name=='首日园林' for a in loaded.days[target.day_index].attractions)
    assert all(d.removed_attraction_names==['早已删除'] for d in loaded.days_detail)
    assert target.attractions[-1].visit_duration==90
    assert (await client.post(url,json=confirm|{'acknowledge_adjustments':True})).status_code==409
    # Recompute/force assembly reads the updated catalog, not the original date.
    result=await client.post(f'/api/trip/draft/{ident}/day/0/recompute',json={})
    assert result.status_code==200 and not result.json()['day_detail']['attractions']


@pytest.mark.asyncio
@pytest.mark.parametrize('protection',['lock','appointment','manual_meal'])
async def test_fixed_user_choices_are_not_silently_removed(client,protection):
    ident=await seed();record=await drafts.get_draft(ident);days=json.loads(record.days_detail_json)
    if protection=='lock':days[0]['locked_attraction_names']=['首日园林']
    elif protection=='appointment':days[0]['time_constraints']={'appointments':[dict(kind='attraction',ref_name='首日园林',start_time='08:00')]}
    else:days[0]['meals']=[dict(name='手动午餐',type='lunch',schedule_mode='manual')]
    async with async_session() as s:
        r=await s.get(TripDraft,ident);r.days_detail_json=json.dumps(days,ensure_ascii=False);await s.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident))
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json={'journey':late_journey()})
    assert response.status_code==422,response.text
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_map_failure_and_stale_projection_never_write_partial_results(client,monkeypatch):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment';before=adjustment.snapshot(await drafts.get_draft(ident))
    monkeypatch.setattr(adjustment,'compute_day_route',AsyncMock(side_effect=HTTPException(503,'模拟地图故障')))
    assert (await client.post(url,json={'journey':late_journey()})).status_code==503
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_joint_preview_assembles_skeletons_and_moves_only_displaced_visits_before_atomic_save(client):
    ident=await seed(request(days=3),assemble=False)
    url=f'/api/trip/draft/{ident}/journey-adjustment'
    before=adjustment.snapshot(await drafts.get_draft(ident))
    body={'journey':late_journey(),'assemble_pending':True}
    response=await client.post(url,json=body)
    assert response.status_code==200,response.text
    preview=response.json()
    assert adjustment.snapshot(await drafts.get_draft(ident))==before
    assert all(day is not None for day in preview['days_detail'])
    assert not preview['days_detail'][0]['attractions']
    assert not preview['unassigned_attractions']
    names=[a['name'] for day in preview['days_detail'] for a in day['attractions']]
    assert sorted(names)==['次日公园','首日园林']
    saved=await client.post(url,json=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True))
    assert saved.status_code==200,saved.text
    value=(await client.get('/api/trip/draft/'+ident)).json()
    assert [[a['name'] for a in d['attractions']] for d in value['days_detail']]==[[a['name'] for a in d['attractions']] for d in preview['days_detail']]


@pytest.mark.asyncio
async def test_impossible_auto_lunch_does_not_remove_unrelated_attractions(client):
    ident=await seed(request(days=3))
    async with async_session() as session:
        record=await session.get(TripDraft,ident)
        days=json.loads(record.days_detail_json)
        days[0]['meals']=[dict(name='下午才开门的餐厅',type='lunch',preferred_slot='lunch',schedule_mode='auto',open_hours='16:30-22:00')]
        days[0]['timeline_order'].append(dict(kind='meal',ref_name='下午才开门的餐厅'))
        record.days_detail_json=json.dumps(days,ensure_ascii=False)
        await session.commit()
    journey=late_journey();journey['outbound']['arrival_time']='2026-11-10T12:00'
    before=adjustment.snapshot(await drafts.get_draft(ident))
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json={'journey':journey})
    assert response.status_code==200,response.text
    preview=response.json()
    assert [a['name'] for a in preview['days_detail'][0]['attractions']]==['首日园林']
    assert not preview['days_detail'][0]['meals']
    assert not preview['unassigned_attractions']
    assert preview['meal_recovery'][0]['old_restaurant']=='下午才开门的餐厅'
    assert preview['meal_recovery'][0]['status']=='unavailable'
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


def test_joint_preview_uses_same_last_admission_check_as_day_save():
    day=DayDetail(day_index=0,date='2026-11-10',day_start_time='15:00',
        attractions=[Attraction(name='限时入场公园',address='测试',description='模拟',visit_duration=60,open_hours='08:00-18:00；最晚入场14:00')],
        timeline_order=[dict(kind='attraction',ref_name='限时入场公园')])
    schedule_day(day)
    assert '限时入场公园超过已知最晚入场时间' in adjustment.violations(day,day)


@pytest.mark.asyncio
async def test_confirm_rejects_weather_or_catalog_change_even_when_days_unchanged(client):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment';body={'journey':late_journey()}
    p=(await client.post(url,json=body)).json()
    async with async_session() as s:
        r=await s.get(TripDraft,ident);r.weather_info_json='[ ]';await s.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident))
    response=await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))
    assert response.status_code==409 and adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_expired_proposal_and_tampered_journey_are_rejected(client):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment';body={'journey':late_journey()}
    p=(await client.post(url,json=body)).json();adjustment._proposals[p['adjustment_id']]['expires']=0
    response=await client.post(url,json=body|dict(adjustment_id=p['adjustment_id'],preview_token=p['preview_token'],acknowledge_adjustments=True))
    assert response.status_code==409

@pytest.mark.asyncio
async def test_inflight_route_change_and_cancellation_leave_no_partial_state(client,monkeypatch):
    ident=await seed();url=f'/api/trip/draft/{ident}/journey-adjustment'
    entered,resume=asyncio.Event(),asyncio.Event()
    route=adjustment.compute_day_route
    async def paused(*args):
        entered.set();await resume.wait();return await route(*args)
    monkeypatch.setattr(adjustment,'compute_day_route',paused)
    task=asyncio.create_task(client.post(url,json={'journey':late_journey()}))
    await asyncio.wait_for(entered.wait(),2)
    async with async_session() as s:
        r=await s.get(TripDraft,ident);r.weather_info_json='[ ]';await s.commit()
    before=adjustment.snapshot(await drafts.get_draft(ident));resume.set();response=await task
    assert response.status_code==409 and adjustment.snapshot(await drafts.get_draft(ident))==before
    entered.clear();resume.clear()
    task=asyncio.create_task(client.post(url,json={'journey':late_journey()}))
    await asyncio.wait_for(entered.wait(),2);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


@pytest.mark.asyncio
async def test_pending_manual_placement_updates_the_target_catalog_and_rejects_travel_day(client):
    ident=await seed(request(True),assemble=False)
    async with async_session() as s:
        r=await s.get(TripDraft,ident);raw=json.loads(r.request_json)
        from app.services.journey_planning import pending_item
        item=pending_item(cluster('待安排新景点'));raw['_transport_unassigned']=[item];r.request_json=json.dumps(raw,ensure_ascii=False);await s.commit()
    url=f'/api/trip/draft/{ident}/journey-adjustment';record=await drafts.get_draft(ident);journey=_load_payload(record).request.journey.model_dump(mode='json')
    response=await client.post(url,json=dict(journey=journey,placements=[dict(id=item['id'],day_index=0)]))
    assert response.status_code==422
    body=dict(journey=journey,placements=[dict(id=item['id'],day_index=2)])
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    preview=response.json();assert not preview['unassigned_attractions']
    response=await client.post(url,json=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True))
    assert response.status_code==200,response.text
    record=await drafts.get_draft(ident)
    assert any(a['name']=='待安排新景点' for a in json.loads(record.clusters_data_json)[2])
    assert json.loads(record.days_detail_json)[2] is None


@pytest.mark.asyncio
async def test_estimated_or_missing_routes_do_not_become_verified_adjustments(client,monkeypatch):
    ident=await seed();before=adjustment.snapshot(await drafts.get_draft(ident))
    monkeypatch.setattr(adjustment,'compute_day_route',AsyncMock(return_value=[]))
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json={'journey':late_journey()})
    assert response.status_code==422 and '路线尚未核实' in response.text
    assert adjustment.snapshot(await drafts.get_draft(ident))==before


def test_reserved_travel_day_does_not_crowd_out_the_next_group():
    groups=reserve_clusters(request(True),[[cluster('A')],[cluster('B')],[],[],[]])
    assert not groups[0] and not groups[-1]
    assert [x['name'] for x in groups[1]]==['B']
    assert [x['name'] for x in groups[2]]==['A']


@pytest.mark.asyncio
async def test_pending_placement_in_an_empty_saved_day_uses_the_new_city_window(client):
    req=request(True);req.journey.planning.arrival_policy='time_window';req.journey.planning.ready_at='2026-11-10T15:00'
    ident=await seed(req,assemble=False)
    from app.services.journey_planning import pending_item
    item=pending_item(cluster('下午景点'))
    async with async_session() as s:
        r=await s.get(TripDraft,ident);raw=json.loads(r.request_json);raw['_transport_unassigned']=[item]
        r.request_json=json.dumps(raw,ensure_ascii=False)
        details=json.loads(r.days_detail_json);details[0]=DayDetail(day_index=0,date=req.start_date,day_start_time='08:00',time_constraints={},is_assembled=True).model_dump(mode='json')
        r.days_detail_json=json.dumps(details,ensure_ascii=False);await s.commit()
    response=await client.post(f'/api/trip/draft/{ident}/journey-adjustment',json=dict(journey=req.journey.model_dump(mode='json'),placements=[dict(id=item['id'],day_index=0)]))
    assert response.status_code==200,response.text
    preview=response.json();assert preview['days_detail'][0]['day_start_time']=='15:00'
    assert preview['days_detail'][0]['timeline_schedule'][0]['start_time']=='15:00'


@pytest.mark.asyncio
@pytest.mark.parametrize('no_city_day',[False,True])
async def test_transport_change_preserves_unassembled_skeleton_selections(client,no_city_day):
    ident=await seed(request(days=2),assemble=False)
    journey=dict(origin_city='上海',return_city='上海',planning={'arrival_policy':'travel_day','departure_policy':'travel_day'}) if no_city_day else late_journey()
    url=f'/api/trip/draft/{ident}/journey-adjustment';body={'journey':journey}
    before=adjustment.snapshot(await drafts.get_draft(ident))
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    preview=response.json()
    assert adjustment.snapshot(await drafts.get_draft(ident))==before
    assert preview['days_detail']==[None,None]
    if no_city_day:
        assert {a['name'] for a in preview['unassigned_attractions']}=={'首日园林','次日公园'}
    else:
        assert not preview['unassigned_attractions']
    response=await client.post(url,json=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True))
    assert response.status_code==200,response.text
    record=await drafts.get_draft(ident);groups=json.loads(record.clusters_data_json)
    assert not groups[0]
    assert {a['name'] for a in groups[1]}==(set() if no_city_day else {'首日园林','次日公园'})
    all_facts=[a for group in groups for a in group]+[a['cluster'] for a in preview['unassigned_attractions']]
    assert len(all_facts)==2 and all(a['visit_minutes']==90 for a in all_facts)


@pytest.mark.asyncio
async def test_preview_includes_hotel_time_changes_before_finalize(client,monkeypatch):
    from app.models.schemas import Hotel
    from app.agents.langgraph_agent.finalize import pipeline
    monkeypatch.setattr(pipeline,'_run_extract_preferences',AsyncMock(return_value=None))
    ident=await seed();record=await drafts.get_draft(ident)
    day=_load_payload(record).days_detail[-1]
    day.hotel=Hotel(name='末日酒店')
    day.timeline_order=[dict(kind='hotel',ref_name='末日酒店',phase='start'),dict(kind='hotel',ref_name='末日酒店',phase='end')]
    schedule_day(day);assert day.timeline_schedule[-1]['duration']==30
    await drafts.patch_day_detail(ident,day.day_index,day)
    url=f'/api/trip/draft/{ident}/journey-adjustment';body={'journey':late_journey()}
    response=await client.post(url,json=body);assert response.status_code==200,response.text
    preview=response.json()
    assert preview['days_detail'][-1]['timeline_schedule'][-1]['duration']==0
    assert any('末日酒店' in change and '→' in change for change in preview['changes'])
    response=await client.post(url,json=body|dict(adjustment_id=preview['adjustment_id'],preview_token=preview['preview_token'],acknowledge_adjustments=True))
    assert response.status_code==200,response.text
    saved=(await client.get(f'/api/trip/draft/{ident}')).json()
    response=await client.post(f'/api/trip/draft/{ident}/finalize')
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type']=='complete',events[-1]
    assert [d['timeline_schedule'] for d in events[-1]['trip_plan']['days']]==[d['timeline_schedule'] for d in saved['days_detail']]
