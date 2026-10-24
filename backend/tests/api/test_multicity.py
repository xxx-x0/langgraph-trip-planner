"""No live fares: aggregate accounting, time windows, versions and atomic edits."""
import copy
import json
from datetime import date
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.database import init_db
from app.models.multicity import MultiTrip
from app.models.schemas import MacroPlan, DaySkeleton, DayDetail, Attraction
from app.services import multicity as svc, trip_draft_service


def example():
    def city(id,name): return dict(id=id,name=name)
    def leg(day,frm,to,price=100):
        return dict(departure_station=frm,arrival_station=to,departure_time=day+'T10:00',arrival_time=day+'T11:00',passengers=2,ticket_total=price,extras_total=0,price_source='user_estimate',price_note='人工测试示例，非真实票价',transfer_before_minutes=20,station_buffer_minutes=30,baggage_minutes=0,transfer_after_minutes=20,lodging_buffer_minutes=10)
    def hotel(id,name,a,b,amount,basis): return dict(id=id,name=name,check_in=a,check_out=b,rooms=2,amount=amount,basis=basis,source='user_estimate',source_note='测试估算',taxes_included=True)
    return dict(title='上海出发苏杭六晚',start_date='2026-10-20',end_date='2026-10-26',origin=city('sh','上海'),destination=city('nj','南京'),companions={'type':'couple','count':2},budget=3000,
        stops=[dict(id='s',city=city('sz','苏州'),start_date='2026-10-20',end_date='2026-10-23',lodgings=[hotel('hs','苏州住处','2026-10-20','2026-10-23',200,'room_night')]),dict(id='h',city=city('hz','杭州'),start_date='2026-10-23',end_date='2026-10-26',lodgings=[hotel('hh','杭州住处','2026-10-23','2026-10-26',600,'stay_total')])],
        transfers=[dict(from_stop='origin',to_stop='s',leg=leg('2026-10-20','上海','苏州')),dict(from_stop='s',to_stop='h',leg=leg('2026-10-23','苏州','杭州',150)),dict(from_stop='h',to_stop='destination',leg=leg('2026-10-26','杭州','南京',200))])

@pytest_asyncio.fixture
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c: yield c


def test_accounting_and_windows_do_not_double_count():
    v=svc.projection(MultiTrip.model_validate(example()))
    assert v['budget']['hotels']==1800 and v['budget']['transport']==450 and v['budget']['total']==2250
    assert v['budget']['is_within_budget'] is None
    assert len(v['nights'])==6 and all(len(n['owners'])==1 for n in v['nights'])
    assert v['cities'][0]['windows'][-1]['end_minutes']==540
    assert v['cities'][1]['windows'][0]['start_minutes']==690
    assert v['door_minutes']==430 and not v['conflicts']


def test_overnight_and_zero_night_visit():
    raw=example();raw['stops'][0]['end_date']='2026-10-22';raw['stops'][0]['lodgings'][0]['check_out']='2026-10-22'
    raw['transfers'][1]['leg'].update(departure_time='2026-10-22T22:00',arrival_time='2026-10-23T08:00')
    v=svc.projection(MultiTrip.model_validate(raw))
    assert next(n for n in v['nights'] if n['date']=='2026-10-22')['owners']==['在途：苏州 → 杭州']
    assert v['cities'][1]['windows'][0]['start_minutes']==510
    raw['stops'][0]['end_date']=raw['stops'][0]['start_date'];raw['stops'][0]['lodgings']=[]
    assert MultiTrip.model_validate(raw).stops[0].start_date==date(2026,10,20)

@pytest.mark.parametrize('change',[lambda p:p['stops'][1].update(start_date='2026-10-22'),lambda p:p['stops'][1].update(id='s'),lambda p:p['transfers'][0]['leg'].update(passengers=1),lambda p:p['stops'][0]['lodgings'].append(copy.deepcopy(p['stops'][0]['lodgings'][0])),lambda p:p.update(end_date='2026-11-20')])
def test_invalid_structure(change):
    raw=example();change(raw)
    with pytest.raises(ValueError): MultiTrip.model_validate(raw)


def test_date_mismatch_conflicts():
    raw=example();raw['transfers'][1]['leg'].update(departure_time='2026-10-24T10:00',arrival_time='2026-10-24T11:00')
    assert any('不一致' in x for x in svc.projection(MultiTrip.model_validate(raw))['conflicts'])


def test_missing_foreign_prices_and_partial_stays():
    raw=example();raw['transfers'][0]['leg']['currency']='USD';raw['stops'][0]['lodgings'][0].update(amount=None,check_out='2026-10-21')
    v=svc.projection(MultiTrip.model_validate(raw));assert v['budget']['transport']==350 and v['budget']['hotels']==600
    assert v['budget']['is_within_budget'] is None and any('未换算' in x for x in v['missing'])
    assert any('2026-10-22 苏州住宿' in x for x in v['missing'])


def test_suggestions_protect_booked_travel():
    raw=example();raw['transfers'][1]['leg']['booking_status']='booked';options=svc.suggest(MultiTrip.model_validate(raw))
    assert len(options)>=2 and not options[0]['blocked']
    assert all(x['blocked'] or x['summary']['conflicts'] for x in options[1:])

@pytest.mark.asyncio
async def test_preview_cas_saved_copy_and_old_api_guard(client):
    r=await client.post('/api/multi-trips',json=example());assert r.status_code==200,r.text
    d=r.json();url='/api/multi-trips/'+d['id'];raw=copy.deepcopy(d['plan']);raw['budget']=2000
    body=dict(plan=raw,revision=1);preview=await client.post(url+'/preview',json=body);assert preview.status_code==200,preview.text
    assert (await client.get(url)).json()['plan']['budget']==3000
    body['preview_token']=preview.json()['preview_token'];saved=await client.put(url,json=body);assert saved.status_code==200,saved.text
    assert (await client.put(url,json=body)).status_code==409
    frozen=await client.post(url+'/save',json={'revision':2});assert frozen.status_code==200,frozen.text
    assert (await client.post(url+'/preview',json={**body,'revision':3})).status_code==409
    copied=(await client.post(url+'/copy')).json();assert copied['id']!=d['id'] and copied['source_id']==d['id'] and copied['status']=='draft'
    assert (await client.get('/api/trip/draft/'+d['id'])).status_code==404
    assert (await client.delete('/api/trip/draft/'+d['id'])).status_code==404

@pytest.mark.asyncio
async def test_booked_change_requires_ack(client):
    raw=example();raw['transfers'][0]['leg']['booking_status']='booked';d=(await client.post('/api/multi-trips',json=raw)).json();url='/api/multi-trips/'+d['id']
    raw['transfers'][0]['leg']['departure_time']='2026-10-20T09:00';body=dict(plan=raw,revision=1);pr=(await client.post(url+'/preview',json=body)).json();assert pr['booked']
    body['preview_token']=pr['preview_token'];assert (await client.put(url,json=body)).status_code==409
    body['acknowledge_booked']=True;assert (await client.put(url,json=body)).status_code==200

async def city_draft(parent,stop_id):
    plan=MultiTrip.model_validate(parent['plan']);stop=next(x for x in plan.stops if x.id==stop_id);req=svc.city_request(plan,stop)
    ds=svc.dates(date.fromisoformat(req.start_date),date.fromisoformat(req.end_date));macro=MacroPlan(city=req.city,total_days=len(ds),days=[DaySkeleton(day_index=i,date=d,attraction_names=[]) for i,d in enumerate(ds)])
    draft=await trip_draft_service.create_draft(user_id='multi-test',request=req,selected_attractions=[],macro_plan=macro,clusters_data=[[]]*len(ds),hotels_by_day=[[]]*len(ds),dining_pool=[{}]*len(ds),weather_info=[])
    detail=DayDetail(day_index=0,date=ds[0],day_start_time='12:00',companion_count=2,attractions=[Attraction(name='保留景点',address='测试',description='隔离示例',visit_duration=30,ticket_price=0)],locked_attraction_names=['保留景点'],removed_attraction_names=['已删景点'],timeline_order=[dict(kind='attraction',ref_name='保留景点')])
    await trip_draft_service.patch_day_detail(draft,0,detail)
    return draft,svc.stop_basis(plan,stop)

@pytest.mark.asyncio
async def test_sync_delay_preserves_locks_and_source(client):
    raw=example();d=(await client.post('/api/multi-trips',json=raw)).json();url='/api/multi-trips/'+d['id'];child,basis=await city_draft(d,'s');source=await trip_draft_service.get_draft(child)
    r=await client.post(url+'/cities/s/import',json=dict(revision=1,basis=basis,draft_id=child));assert r.status_code==200,r.text
    assert (await client.post(url+'/cities/s/import',json=dict(revision=1,basis=basis,draft_id=child))).status_code==409
    raw['transfers'][0]['leg']['arrival_time']='2026-10-20T15:00';body=dict(plan=raw,revision=2);p=await client.post(url+'/preview',json=body);assert p.status_code==200,p.text
    r=await client.put(url,json={**body,'preview_token':p.json()['preview_token']});assert r.status_code==200,r.text
    day=r.json()['summary']['cities'][0]['days'][0];assert day['locked_attraction_names']==['保留景点'] and day['removed_attraction_names']==['已删景点']
    assert day['day_start_time']=='15:30'
    assert (await trip_draft_service.get_draft(child)).days_detail_json==source.days_detail_json
    r=await client.post(url+'/cities/s/edit',json={'revision':3});assert r.status_code==200,r.text
    new=await trip_draft_service.get_draft(r.json()['draft_id']);assert new.id!=child and json.loads(new.days_detail_json)[0]['locked_attraction_names']==['保留景点']
    assert (await client.post(url+'/cities/s/import',json=dict(revision=3,basis=basis,draft_id=child))).status_code==409

@pytest.mark.asyncio
async def test_failed_import_keeps_whole_trip(client):
    d=(await client.post('/api/multi-trips',json=example())).json();url='/api/multi-trips/'+d['id'];child,basis=await city_draft(d,'s');before=(await client.get(url)).json()
    assert (await client.post(url+'/cities/h/import',json=dict(revision=1,basis=basis,draft_id=child))).status_code==409
    assert (await client.get(url)).json()==before

@pytest.mark.asyncio
async def test_multicity_not_deleted_by_old_ttl(client):
    d=(await client.post('/api/multi-trips',json=example())).json();await trip_draft_service.delete_expired(days=-1)
    assert (await client.get('/api/multi-trips/'+d['id'])).status_code==200


def test_three_cities_ten_days_can_reduce_optional_city():
    raw=example();raw['end_date']='2026-10-29';raw['transfers']=[]
    raw['stops'].append(dict(id='n',city=dict(id='nj',name='南京'),start_date='2026-10-26',end_date='2026-10-29',must_visit=False,lodgings=[]))
    p=MultiTrip.model_validate(raw);v=svc.projection(p)
    assert len(v['nights'])==9 and v['hotel_changes']==2
    option=next(o for o in svc.suggest(p) if o['name']=='少换一座城市')
    assert len(option['plan']['stops'])==2 and option['plan']['stops'][-1]['end_date']=='2026-10-29'
    assert not option['blocked'] and option['summary']['missing']

@pytest.mark.asyncio
async def test_imported_editor_snapshot_survives_source_deletion_and_date_change(client):
    raw=example();d=(await client.post('/api/multi-trips',json=raw)).json();url='/api/multi-trips/'+d['id'];child,basis=await city_draft(d,'s')
    r=await client.post(url+'/cities/s/import',json=dict(revision=1,basis=basis,draft_id=child));assert r.status_code==200,r.text
    await trip_draft_service.delete_draft(child)
    r=await client.post(url+'/cities/s/edit',json=dict(revision=2));assert r.status_code==200,r.text
    raw['stops'][0]['start_date']='2026-10-21';raw['stops'][0]['lodgings']=[];raw['transfers']=[]
    body=dict(plan=raw,revision=2);p=(await client.post(url+'/preview',json=body)).json()
    assert p['summary']['cities'][0]['stale']
    r=await client.put(url,json={**body,'preview_token':p['preview_token']});assert r.status_code==200,r.text
    assert r.json()['snapshots']['s']['days_detail'][0]['locked_attraction_names']==['保留景点']
    assert (await client.post(url+'/cities/s/edit',json=dict(revision=3))).status_code==409

@pytest.mark.asyncio
async def test_projection_failure_rolls_back_parent(client,monkeypatch):
    d=(await client.post('/api/multi-trips',json=example())).json();url='/api/multi-trips/'+d['id'];body=dict(plan=d['plan'],revision=1)
    p=(await client.post(url+'/preview',json=body)).json();before=await svc.load(d['id'])
    with monkeypatch.context() as m:
        def fail(*a,**kw): raise RuntimeError('injected projection failure')
        m.setattr(svc,'projection',fail)
        with pytest.raises(RuntimeError): await client.put(url,json={**body,'preview_token':p['preview_token']})
    assert await svc.load(d['id'])==before


def test_missing_meals_on_rest_days_remain_pending():
    v=svc.projection(MultiTrip.model_validate(example()))
    assert any('2026-10-22 午餐尚未' in x for x in v['missing'])
    assert not v['budget']['complete']


def test_mismatched_departure_is_reported_without_failing_projection():
    raw=example();raw['stops'][0]['start_date']='2026-10-24';raw['stops'][0]['end_date']='2026-10-24';raw['stops'][0]['lodgings']=[]
    raw['stops'][1]['start_date']='2026-10-24';raw['stops'][1]['lodgings'][0]['check_in']='2026-10-24'
    # Known transfer precedes the hand-edited stay dates; keep an actionable conflict.
    v=svc.projection(MultiTrip.model_validate(raw))
    assert any('日期不一致' in c for c in v['conflicts'])


def test_changing_booked_departure_city_requires_review_even_if_leg_unchanged():
    raw=example();raw['transfers'][0]['leg']['booking_status']='booked';old=MultiTrip.model_validate(raw)
    raw['origin']['name']='北京';new=MultiTrip.model_validate(raw)
    _,booked=svc.change_report(old,new)
    assert booked and '已订班次' in booked[0]

@pytest.mark.asyncio
async def test_rest_proposal_preview_save_and_child_context(client):
    raw=example();proposed=(await client.post('/api/multi-trips/rest-suggestions',json=raw)).json()['plan']
    assert [r['date'] for s in proposed['stops'] for r in s['rest_periods']]==['2026-10-22','2026-10-25']
    assert (await client.post('/api/multi-trips/rest-suggestions',json=proposed)).json()['plan']==proposed
    d=(await client.post('/api/multi-trips',json=raw)).json();url='/api/multi-trips/'+d['id'];body=dict(plan=proposed,revision=d['revision'])
    p=(await client.post(url+'/preview',json=body)).json()
    assert any('休息时段更新' in x for x in p['changes']) and any('休息尚未落实' in x for x in p['summary']['missing'])
    assert (await client.get(url)).json()['plan']['stops'][0]['rest_periods']==[]
    saved=(await client.put(url,json={**body,'preview_token':p['preview_token']})).json()
    assert (await client.get(url+'/cities/s/request')).json()['request']['rest_periods']==proposed['stops'][0]['rest_periods']
    assert saved['summary']['budget']==d['summary']['budget']
    assert saved['summary']['usable_minutes']==d['summary']['usable_minutes']-360

@pytest.mark.parametrize('periods',[
    [dict(id='r',date='2026-10-29',start_time='14:00',end_time='15:00')],
    [dict(id='r',date='2026-10-22',start_time='15:00',end_time='14:00')],
    [dict(id='r',date='2026-10-22',start_time='14:00',end_time='16:00'),dict(id='b',date='2026-10-22',start_time='15:00',end_time='17:00')]])
def test_invalid_rest_periods(periods):
    raw=example();raw['stops'][0]['rest_periods']=periods
    with pytest.raises(ValueError): MultiTrip.model_validate(raw)

def test_rest_outside_transfer_window():
    raw=example();raw['stops'][0]['rest_periods']=[dict(id='r',date='2026-10-23',start_time='14:00',end_time='17:00')]
    assert any('休息时段与抵离交通冲突' in x for x in svc.projection(MultiTrip.model_validate(raw))['conflicts'])


def test_shared_transfer_date_cannot_reserve_overlapping_rest_in_two_cities():
    raw=example();raw['transfers']=[]
    for i,s in enumerate(raw['stops']): s['rest_periods']=[dict(id=f'r{i}',date='2026-10-23',start_time='14:00',end_time='16:00')]
    with pytest.raises(ValueError,match='不能重叠'): MultiTrip.model_validate(raw)


def test_long_transfer_recovery_suggestion_keeps_user_rest():
    raw=example();raw['transfers'][0]['leg'].update(departure_time='2026-10-20T06:00',arrival_time='2026-10-20T11:00')
    result=svc.suggest_rest(MultiTrip.model_validate(raw))
    periods=result['plan']['stops'][0]['rest_periods']
    assert periods[0]['date']=='2026-10-20' and periods[0]['label']=='换城后歇一歇'
    assert periods[0]['start_time']=='14:00' and periods[0]['end_time']=='15:00'
    assert svc.suggest_rest(MultiTrip.model_validate(result['plan']))['plan']==result['plan']
