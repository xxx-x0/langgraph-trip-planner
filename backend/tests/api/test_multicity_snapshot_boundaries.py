"""Whole-trip snapshot/accounting boundaries using temporary SQLite and doubles."""
import copy,json
from unittest.mock import AsyncMock
import pytest
from app.models.multicity import MultiTrip
from app.models.schemas import DayDetail,Hotel,HotelQuote,HotelOccupancy
from app.services import multicity as svc,trip_draft_service,transport_adjustment as adj
from app.database import async_session
from app.models.db_models import TripDraft
from tests.api.test_multicity import client,example,city_draft
from tests.api.test_transport_adjustment import sample
from app.agents.langgraph_agent.assemble.schedule import schedule_day

@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['date','index','dietary','transportation'])
async def test_import_checks_each_saved_day_and_planning_request(client,corruption):
    d=(await client.post('/api/multi-trips',json=example())).json();child,basis=await city_draft(d,'s');before=await svc.load(d['id'])
    async with async_session() as session:
        row=await session.get(TripDraft,child)
        if corruption in {'date','index'}:
            days=json.loads(row.days_detail_json);days[0]['date' if corruption=='date' else 'day_index']='2026-10-25' if corruption=='date' else 2
            row.days_detail_json=json.dumps(days)
        else:
            req=json.loads(row.request_json);req['dietary_requirements' if corruption=='dietary' else 'transportation']='过敏要求已变' if corruption=='dietary' else '自驾'
            row.request_json=json.dumps(req)
        await session.commit()
    response=await client.post('/api/multi-trips/'+d['id']+'/cities/s/import',json={'revision':1,'basis':basis,'draft_id':child})
    assert response.status_code==409,response.text
    assert await svc.load(d['id'])==before


def test_manual_lodging_override_removes_daily_hotel_timeline_charge():
    raw=example();plan=MultiTrip.model_validate(raw);req=svc.city_request(plan,plan.stops[0])
    quote=HotelQuote(source='AIGoHotel',cost_kind='query_quote',status='detail_returned',amount=100,currency='CNY',unit='average_per_room_night',check_in=req.start_date,check_out=req.end_date,nights=3,occupancy=HotelOccupancy(adults_per_room=2),occupancy_confirmed=True,queried_at='2026-10-19T10:00:00Z',unsupported_conditions=[],availability='returned')
    day=DayDetail(day_index=0,date=req.start_date,hotel=Hotel(name='苏州住处',quote=quote),timeline_order=[{'kind':'hotel','ref_name':'苏州住处','phase':'end'}]);schedule_day(day)
    snap={'s':dict(request=req.model_dump(mode='json'),days_detail=[day.model_dump(mode='json'),None,None,None],editor_data={},draft_id='source')}
    before=copy.deepcopy(snap);summary=svc.projection(plan,snap)
    projected=summary['cities'][0]['days'][0]
    assert summary['budget']['hotels']==1800 and projected['day_budget']['total_hotels']==0
    assert all(x.get('cost') is None for x in projected['timeline_schedule'] if x['kind']=='hotel')
    assert snap==before

@pytest.mark.asyncio
async def test_late_lunch_that_fits_is_not_cancelled_by_active_adjustment(monkeypatch):
    old,snapshots,plan=sample()
    # Arrival 13:30 + 30 minutes of buffers leaves a valid 14:00-15:00 lunch.
    old.stops[0].rest_periods=[];plan.stops[0].rest_periods=[]
    leg=plan.transfers[0].leg
    leg.departure_time='2026-10-29T12:30';leg.arrival_time='2026-10-29T13:30';leg.baggage_minutes=0;leg.transfer_after_minutes=0;leg.lodging_buffer_minutes=30
    raw=snapshots['h']['days_detail'][0];day=DayDetail.model_validate(raw);day.attractions=[];day.timeline_order=[{'kind':'meal','ref_name':m.name} for m in day.meals];schedule_day(day);snapshots['h']['days_detail'][0]=day.model_dump(mode='json')
    monkeypatch.setattr(adj,'compute_day_route',AsyncMock(side_effect=lambda d,*a:[dict(from_name=x['ref_name'],to_name=y['ref_name'],duration='20分钟',detail='模拟路线') for x,y in zip(d.timeline_order,d.timeline_order[1:])]))
    document=dict(id='mc_test',plan=old.model_dump(mode='json'),snapshots=snapshots,revision=1)
    before=copy.deepcopy(document)
    proposed,new_snapshots,changes,summary=await adj.propose(document,plan)
    meals=new_snapshots['h']['days_detail'][0]['meals']
    assert any(m['name']=='杭州午餐' and m['type']=='lunch' for m in meals)
    assert not any('取消本城无法容纳的用餐 杭州午餐' in c for c in changes)
    assert document==before and not summary['conflicts']


@pytest.mark.asyncio
async def test_imported_snapshot_and_cloned_editor_ignore_later_source_edits(client):
    d=(await client.post('/api/multi-trips',json=example())).json();child,basis=await city_draft(d,'s');base='/api/multi-trips/'+d['id']
    imported=await client.post(base+'/cities/s/import',json={'revision':1,'basis':basis,'draft_id':child});assert imported.status_code==200
    before=await svc.load(d['id']);source=await trip_draft_service.get_draft(child)
    changed=DayDetail.model_validate(json.loads(source.days_detail_json)[0]);changed.day_start_time='18:00';changed.locked_attraction_names=[]
    await trip_draft_service.patch_day_detail(child,0,changed)
    assert await svc.load(d['id'])==before
    cloned=await client.post(base+'/cities/s/edit',json={'revision':2});assert cloned.status_code==200,cloned.text
    record=await trip_draft_service.get_draft(cloned.json()['draft_id']);saved=json.loads(record.days_detail_json)[0]
    assert saved['day_start_time']=='12:00' and saved['locked_attraction_names']==['保留景点']
    assert await svc.load(d['id'])==before

@pytest.mark.asyncio
async def test_active_proposal_generation_rejects_concurrent_whole_trip_edit(client,monkeypatch):
    import asyncio
    old,snapshots,plan=sample();d=await svc.create(old,snapshots=snapshots);before=copy.deepcopy(d);entered,resume=asyncio.Event(),asyncio.Event()
    async def route(day,*args):
        entered.set();await resume.wait()
        return [dict(from_name=a['ref_name'],to_name=b['ref_name'],duration='20分钟',detail='模拟路线') for a,b in zip(day.timeline_order,day.timeline_order[1:])]
    monkeypatch.setattr(adj,'compute_day_route',route)
    pending=asyncio.create_task(client.post('/api/multi-trips/'+d['id']+'/preview',json={'plan':plan.model_dump(mode='json'),'revision':1,'adjust_days':True}))
    await asyncio.wait_for(entered.wait(),2)
    async def edit(doc,session): doc['plan']['title']='先完成的修改';return doc
    current=await svc.write(d['id'],1,edit);resume.set();response=await pending
    assert response.status_code==409,response.text
    assert await svc.load(d['id'])==current and current['snapshots']==before['snapshots']
