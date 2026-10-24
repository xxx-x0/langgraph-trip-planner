import copy
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.database import init_db
from app.models.multicity import MultiTrip, CityTransfer
from app.models.schemas import DayDetail, Attraction, Meal
from app.services import multicity, transport_adjustment as adj
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def sample():
    city=lambda n:dict(id=n,name=n)
    plan=MultiTrip.model_validate(dict(title='隔离调整样本',start_date='2026-10-27',end_date='2026-10-31',origin=city('上海'),destination=city('上海'),companions={'type':'solo','count':1},stops=[dict(id='s',city=city('苏州'),start_date='2026-10-27',end_date='2026-10-29',rest_periods=[dict(id='r',date='2026-10-29',start_time='14:00',end_time='17:00',label='休息')]),dict(id='h',city=city('杭州'),start_date='2026-10-29',end_date='2026-10-31')]))
    snapshots={}
    for stop in plan.stops:
        req=multicity.city_request(plan,stop);days=[]
        for date in multicity.dates(stop.start_date,stop.end_date):
            day=DayDetail(day_index=len(days),date=date,attractions=[Attraction(name=stop.city.name+'景点',address='测试',description='隔离',visit_duration=60,open_hours='08:00-17:00')],meals=[Meal(name=stop.city.name+'午餐',type='lunch',preferred_slot='lunch',open_hours='10:00-21:00'),Meal(name=stop.city.name+'晚餐',type='dinner',preferred_slot='dinner',open_hours='10:00-21:00')],timeline_order=[dict(kind='attraction',ref_name=stop.city.name+'景点'),dict(kind='meal',ref_name=stop.city.name+'午餐'),dict(kind='meal',ref_name=stop.city.name+'晚餐')],removed_attraction_names=['早已删除'])
            schedule_day(day);days.append(day.model_dump(mode='json'))
        snapshots[stop.id]=dict(draft_id='test',request=req.model_dump(mode='json'),days_detail=days,editor_data={},basis=multicity.stop_basis(plan,stop))
    proposed=plan.model_copy(deep=True)
    proposed.transfers=[CityTransfer.model_validate(dict(from_stop='s',to_stop='h',leg=dict(service_number='G1',departure_station='苏州',arrival_station='杭州',departure_time='2026-10-29T15:00',arrival_time='2026-10-29T16:00',transfer_before_minutes=60,station_buffer_minutes=45,baggage_minutes=0,transfer_after_minutes=60,lodging_buffer_minutes=30)))]
    return plan,snapshots,proposed

@pytest_asyncio.fixture
async def client(monkeypatch):
    await init_db();monkeypatch.setattr(adj,'compute_day_route',AsyncMock(side_effect=lambda d,*args:[dict(from_name=a['ref_name'],to_name=b['ref_name'],duration='20分钟',detail='模拟路线') for a,b in zip(d.timeline_order,d.timeline_order[1:])]));adj._proposals.clear()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c: yield c

@pytest.mark.asyncio
async def test_preview_adjusts_both_days_and_atomic_confirmation(client):
    old,snapshots,plan=sample();d=await multicity.create(old,snapshots=snapshots);url='/api/multi-trips/'+d['id'];before=copy.deepcopy(d)
    r=await client.post(url+'/preview',json=dict(plan=plan.model_dump(mode='json'),revision=1,adjust_days=True));assert r.status_code==200,r.text
    p=r.json();assert await multicity.load(d['id'])==before and not p['summary']['conflicts']
    assert any('取消无法容纳的休息' in x for x in p['adjustments']) and any('杭州景点' in x for x in p['adjustments'])
    body=dict(plan=p['proposed_plan'],revision=1,adjustment_id=p['adjustment_id'],preview_token=p['preview_token'])
    assert (await client.put(url,json=body)).status_code==409 and await multicity.load(d['id'])==before
    r=await client.put(url,json={**body,'acknowledge_adjustments':True});assert r.status_code==200,r.text
    after=r.json();assert after['revision']==2 and len(after['plan']['transfers'])==1 and not after['summary']['conflicts']
    for sid,unchanged in [('s',[0,1]),('h',[1,2])]:
        for i in unchanged: assert after['snapshots'][sid]['days_detail'][i]==snapshots[sid]['days_detail'][i]
    hz=after['snapshots']['h']['days_detail'][0]
    assert set(hz['removed_attraction_names'])=={'早已删除','杭州景点'}
    assert [m['preferred_slot'] for m in hz['meals']]==['dinner'] and after['summary']['budget']['complete'] is False
    assert (await client.put(url,json={**body,'acknowledge_adjustments':True})).status_code==409
    saved=await client.post(url+'/save',json={'revision':2});assert saved.status_code==200,saved.text
    assert saved.json()['saved_summary']==saved.json()['summary']

@pytest.mark.asyncio
async def test_locked_attraction_cannot_be_cancelled(client):
    old,snapshots,plan=sample();snapshots['h']['days_detail'][0]['locked_attraction_names']=['杭州景点'];d=await multicity.create(old,snapshots=snapshots)
    r=await client.post('/api/multi-trips/'+d['id']+'/preview',json=dict(plan=plan.model_dump(mode='json'),revision=1,adjust_days=True))
    assert r.status_code==422 and '锁定' in r.text and await multicity.load(d['id'])==d

@pytest.mark.asyncio
async def test_map_failure_leaves_both_city_snapshots_untouched(client,monkeypatch):
    old,snapshots,plan=sample();d=await multicity.create(old,snapshots=snapshots)
    monkeypatch.setattr(adj,'compute_day_route',AsyncMock(side_effect=HTTPException(503,'地图测试故障')))
    r=await client.post('/api/multi-trips/'+d['id']+'/preview',json=dict(plan=plan.model_dump(mode='json'),revision=1,adjust_days=True))
    assert r.status_code==503 and await multicity.load(d['id'])==d

@pytest.mark.asyncio
async def test_preview_cannot_commit_after_snapshot_change(client):
    old,snapshots,plan=sample();d=await multicity.create(old,snapshots=snapshots);url='/api/multi-trips/'+d['id']
    p=(await client.post(url+'/preview',json=dict(plan=plan.model_dump(mode='json'),revision=1,adjust_days=True))).json()
    async def change(d,s): d['snapshots']['h']['days_detail'][0]['day_start_time']='09:00';return d
    await multicity.write(d['id'],1,change)
    r=await client.put(url,json=dict(plan=p['proposed_plan'],revision=2,preview_token=p['preview_token'],adjustment_id=p['adjustment_id'],acknowledge_adjustments=True));assert r.status_code==409

@pytest.mark.parametrize('mutation',['plan','basis','expiry','missing'])
def test_server_proposal_rejects_tampering_and_expiry(mutation):
    old,snapshots,plan=sample();d=dict(id='mc_x',plan=old.model_dump(mode='json'),snapshots=snapshots,revision=1);key=adj.remember(d,plan,snapshots,[])
    if mutation=='plan': plan.title='changed'
    if mutation=='basis': d['revision']=2
    if mutation=='expiry': adj._proposals[key]['expires']=0
    if mutation=='missing': key='unknown'
    with pytest.raises(HTTPException) as e: adj.resolve(key,d,plan)
    assert e.value.status_code==409

@pytest.mark.asyncio
async def test_missing_route_is_not_presented_as_a_verified_adjustment(client,monkeypatch):
    old,snapshots,plan=sample();d=await multicity.create(old,snapshots=snapshots)
    monkeypatch.setattr(adj,'compute_day_route',AsyncMock(return_value=[]))
    r=await client.post('/api/multi-trips/'+d['id']+'/preview',json=dict(plan=plan.model_dump(mode='json'),revision=1,adjust_days=True))
    assert r.status_code==422 and '路线尚未核实' in r.text and await multicity.load(d['id'])==d
