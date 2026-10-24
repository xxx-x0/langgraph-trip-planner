"""Isolated contract tests; examples are not actual tickets or live fares."""
import json
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
import pytest
from tests.api.test_narrative_consistency import case
from app.api.routes.trip_draft import _load_payload
from app.services import trip_draft_service
from app.services.journey_comparison import JourneyCandidate, compare_candidates
from app.models.journey import JourneyLeg


def candidate(name='高铁示例',price=100,start='2026-10-15',end='2026-10-16'):
    common=dict(departure_station='上海虹桥',arrival_station='苏州',price_source='user_estimate',
                ticket_total=price,extras_total=20,connections=0,transfer_before_minutes=10,
                station_buffer_minutes=20,baggage_minutes=0,transfer_after_minutes=10,lodging_buffer_minutes=0,
                price_note='测试示例，不是真实车次或报价')
    return dict(name=name,start_date=start,end_date=end,journey=dict(origin_city='上海',return_city='上海',
                outbound=dict(**common,departure_time=start+'T06:00',arrival_time=start+'T07:00'),
                inbound=dict(**{**common,'departure_station':'苏州','arrival_station':'上海虹桥'},departure_time=end+'T22:00',arrival_time=end+'T23:00')))


@pytest.mark.asyncio
async def test_compare_readonly_unknown_subtotal_never_wins(case):
    client,draft,_=case;before=await trip_draft_service.get_draft(draft)
    a=candidate();b=candidate('缺项',10);b['journey']['outbound']['extras_total']=None
    c=candidate('完整',150);c['journey']['outbound']['transfer_after_minutes']=100
    response=await client.post(f'/api/trip/draft/{draft}/journey-comparison',json={'candidates':[a,b,c]})
    assert response.status_code==200,response.text
    options=response.json()['options']
    assert options[0]['known_total']==240 and '已填交通费用较低' in options[0]['badges']
    assert not options[1]['cost_complete'] and '已填交通费用较低' not in options[1]['badges']
    assert options[0]['door_minutes']==200 and options[0]['budget']['total']>=240
    after=await trip_draft_service.get_draft(draft)
    assert (after.request_json,after.days_detail_json)==(before.request_json,before.days_detail_json)


@pytest.mark.asyncio
async def test_expired_quotes_unknown_connections_not_promoted(case):
    _,draft,_=case;payload=_load_payload(await trip_draft_service.get_draft(draft))
    a=candidate('过期便宜',10);a['journey']['outbound'].update(quoted_at='2026-10-01T08:00',quote_expires_at='2026-10-01T08:15',connections=None)
    options=compare_candidates(payload,[JourneyCandidate.model_validate(a),JourneyCandidate.model_validate(candidate())],now=datetime(2026,10,10,tzinfo=timezone.utc))
    assert not options[0]['cost_complete'] and not options[0]['comfort_known']
    assert '去程：报价已过期' in options[0]['freshness'] and options[0]['badges']==[]


@pytest.mark.asyncio
async def test_adjacent_dates_comparison_only_no_old_hotel_repricing(case):
    client,draft,_=case;c=candidate(start='2026-10-16',end='2026-10-17')
    response=await client.post(f'/api/trip/draft/{draft}/journey-comparison',json={'candidates':[c]})
    option=response.json()['options'][0]
    assert not option['same_dates'] and option['budget'] is None and option['stay_nights']==1
    save=await client.post(f'/api/trip/draft/{draft}/journey',json={'journey':c['journey'],'synchronize':True})
    assert save.status_code==422


@pytest.mark.asyncio
async def test_sync_preserves_order_locks_deletions_atomic_budget(case):
    client,draft,_=case;url=f'/api/trip/draft/{draft}/journey'
    before=await trip_draft_service.get_draft(draft);old=json.loads(before.days_detail_json)
    c=candidate();c['journey']['outbound']['arrival_time']='2026-10-15T09:00'
    body={'journey':c['journey'],'synchronize':True}
    preview=await client.post(url,json=body);assert preview.status_code==200,preview.text
    data=preview.json();assert (await trip_draft_service.get_draft(draft)).days_detail_json==before.days_detail_json
    saved=await client.post(url,json={**body,'preview_token':data['preview_token']});assert saved.status_code==200
    new=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)
    for a,b in zip(old,new):
        if a:
            for key in ['locked_attraction_names','removed_attraction_names','timeline_order']: assert a[key]==b[key]
    assert new[0]['day_budget']['total_intercity']==120 and new[0]['travel_window']['start_minutes']==550
    assert new[0]['day_start_time']=='09:10'
    stale=await client.post(url,json={**body,'preview_token':data['preview_token']});assert stale.status_code==409


@pytest.mark.asyncio
async def test_late_arrival_keeps_meals_marks_conflicts(case):
    client,draft,_=case;before=await trip_draft_service.get_draft(draft);old=json.loads(before.days_detail_json)[0]
    c=candidate();c['journey']['outbound']['arrival_time']='2026-10-15T23:00'
    body={'journey':c['journey'],'synchronize':True};url=f'/api/trip/draft/{draft}/journey'
    preview=(await client.post(url,json=body)).json();assert preview['impacts'][0]['conflicts']
    assert (await client.post(url,json={**body,'preview_token':preview['preview_token']})).status_code==200
    new=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    assert new['meals']==old['meals'] and new['timeline_order']==old['timeline_order']
    assert any('抵离交通冲突' in x for x in new['pending_confirmations'])




def test_itemized_costs_override_aggregate_unknown_not_free():
    data=candidate()['journey']['outbound'];data.update(extras_total=999,extra_costs={'taxes':0,'baggage':None,'transfers':20,'overnight':100})
    leg=JourneyLeg.model_validate(data)
    assert leg.extras_total==120 and leg.extra_costs.baggage is None


@pytest.mark.asyncio
async def test_cross_midnight_reduces_stay_and_counts_extra_lodging_once(case):
    _,draft,_=case;payload=_load_payload(await trip_draft_service.get_draft(draft));payload.request.budget=300
    c=candidate();c['journey']['outbound'].update(departure_time='2026-10-15T23:00',arrival_time='2026-10-16T06:00',
       extra_costs={'taxes':0,'baggage':0,'transfers':20,'overnight':100})
    option=compare_candidates(payload,[JourneyCandidate.model_validate(c)])[0]
    assert option['stay_nights']==0 and option['known_total']==340
    assert option['impacts'][0]['window']['unavailable'] and option['impacts'][0]['conflicts']
    assert option['budget']['total_intercity']==340 and option['budget']['total_hotels']==0
    assert option['budget']['is_within_budget'] is False


@pytest.mark.asyncio
async def test_early_return_preserves_dinner_with_actionable_conflict(case):
    client,draft,_=case;c=candidate();c['journey']['inbound'].update(departure_time='2026-10-16T06:00',arrival_time='2026-10-16T07:00')
    result=await client.post(f'/api/trip/draft/{draft}/journey-comparison',json={'candidates':[c]})
    option=result.json()['options'][0]
    assert option['impacts'][1]['conflicts'] and option['impacts'][1]['window']['end_minutes']==330
    assert option['available_minutes']<=840


@pytest.mark.asyncio
async def test_foreign_currency_and_missing_breakdown_never_rank_as_cheaper(case):
    _,draft,_=case;payload=_load_payload(await trip_draft_service.get_draft(draft))
    foreign=candidate('美元',1);foreign['journey']['outbound']['currency']='USD'
    missing=candidate('少填住宿',1);missing['journey']['outbound']['extra_costs']={'taxes':0,'baggage':0,'transfers':20,'overnight':None}
    items=compare_candidates(payload,[JourneyCandidate.model_validate(c) for c in [foreign,missing,candidate()]])
    assert not items[0]['cost_complete'] and not items[1]['cost_complete']
    assert all('已填交通费用较低' not in i['badges'] for i in items)
    assert any('途中额外住宿费用未知' in m for m in items[1]['missing'])


@pytest.mark.asyncio
async def test_sync_stale_preview_after_day_edit_does_not_write(case):
    client,draft,day=case;body={'journey':candidate()['journey'],'synchronize':True};url=f'/api/trip/draft/{draft}/journey'
    preview=(await client.post(url,json=body)).json()
    assert (await client.post(day+'/recompute',json={'locked_attraction_names':['甲园'],'removed_attraction_names':['丙园']})).status_code==200
    before=await trip_draft_service.get_draft(draft)
    assert (await client.post(url,json={**body,'preview_token':preview['preview_token']})).status_code==409
    after=await trip_draft_service.get_draft(draft)
    assert (after.request_json,after.days_detail_json)==(before.request_json,before.days_detail_json)
    fresh=(await client.post(url,json=body)).json()
    assert (await client.post(url,json={**body,'preview_token':fresh['preview_token']})).status_code==200
    saved=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    assert saved['locked_attraction_names']==['甲园'] and saved['removed_attraction_names']==['丙园']
    assert [a['name'] for a in saved['attractions']]==['甲园','乙园']


@pytest.mark.asyncio
async def test_sync_finalize_and_history_keep_transport_budget_once(case):
    client,draft,_=case;body={'journey':candidate()['journey'],'synchronize':True};base=f'/api/trip/draft/{draft}'
    data=(await client.post(base+'/journey',json=body)).json()
    assert (await client.post(base+'/journey',json={**body,'preview_token':data['preview_token']})).status_code==200
    with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        final=await client.post(base+'/finalize')
    events=[json.loads(line[6:]) for line in final.text.splitlines() if line.startswith('data: ')]
    complete=next(e for e in events if e['type']=='complete')
    assert complete['trip_plan']['budget']['total_intercity']==240
    history=(await client.get('/api/trips/'+str(complete['trip_id']))).json()['data']['plan']
    assert history['journey']['outbound']['ticket_total']==100 and history['budget']['total_intercity']==240
    again=await client.post(base+'/finalize')
    assert next(json.loads(line[6:]) for line in again.text.splitlines() if line.startswith('data: ') and json.loads(line[6:])['type']=='complete')['trip_id']==complete['trip_id']
