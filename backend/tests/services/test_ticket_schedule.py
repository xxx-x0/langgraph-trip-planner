"""Synthetic saved itineraries; no live ticket, map, hotel or model calls."""
import copy
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from app.database import init_db
from app.models.multicity import MultiTrip
from app.models.schemas import DayDetail, Attraction, Meal, Hotel
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from app.services import multicity as svc, trip_draft_service
from app.services.ticket_assistant import TicketRankingRequest, Ranking, rank_tickets
from tests.api.test_multicity import example
from tests.api.test_narrative_consistency import case


def ticket(id, dep='18:00', arr='19:00', mode='train', day='2026-10-26'):
    return dict(id=id, mode=mode, service=id.upper(), from_station='杭州东', to_station='南京南',
        departure=day+'T'+dep, arrival=day+'T'+arr, source='12306' if mode=='train' else 'ctrip',
        availability='available', fare_per_person=100)


@pytest.mark.parametrize('context',[
    dict(kind='multi',draft_id='mc_a'),
    dict(kind='draft',draft_id='a'),
    dict(kind='draft',draft_id='a',request={'city':'杭州'},days_detail=[]),
])
def test_incomplete_context_is_a_validation_error(context):
    with pytest.raises(ValidationError):
        TicketRankingRequest.model_validate(dict(query=dict(priority='balanced',mode='train',from_place='杭州',to_place='南京',date='2026-10-26',passengers=2),candidates=[ticket('a')],context=context))


@pytest_asyncio.fixture
async def multi():
    await init_db()
    plan=MultiTrip.model_validate(example());stop=plan.stops[-1];req=svc.city_request(plan, stop)
    d=DayDetail(day_index=3,date='2026-10-26',day_start_time='08:00',companion_count=2,
        hotel=Hotel(name='杭州住处',address='测试地址'),
        attractions=[Attraction(name='已锁公园',address='测试',description='',visit_duration=60,open_hours='08:00-20:00')],
        meals=[Meal(name='保留午餐',type='lunch',category='main',preferred_slot='lunch',open_hours='10:00-20:00')],
        locked_attraction_names=['已锁公园'],removed_attraction_names=['已删除'],
        timeline_order=[dict(kind='attraction',ref_name='已锁公园'),dict(kind='meal',ref_name='保留午餐')])
    schedule_day(d)
    snapshots={'h':dict(request=req.model_dump(mode='json'),days_detail=[None,None,None,d.model_dump(mode='json')],draft_id='fixture',editor_data={})}
    doc=await svc.create(plan,snapshots=snapshots)
    return doc,dict(query=dict(priority='balanced',mode='train',from_place='杭州',to_place='南京',date='2026-10-26',passengers=2),
        candidates=[ticket('early','07:00','08:00'),ticket('late')],
        context=dict(kind='multi',draft_id=doc['id'],revision=1,from_stop='h',to_stop='destination'))


@pytest.mark.asyncio
async def test_conflicts_removed_before_ai_facts_buffers_and_snapshot_unchanged(multi):
    doc,body=multi
    with patch('app.services.ticket_assistant.get_llm',return_value=object()),patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(return_value=Ranking(ids=['late']))) as model:
        result=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert result['excluded'][0]['candidate']['id']=='early'
    assert any('原安排至' in p for p in result['excluded'][0]['conflicts'])
    sent=json.loads(model.call_args.args[1][1][1])
    assert [c['id'] for c in sent['candidates']]==['late']
    chosen=result['recommendations'][0]
    assert '已锁公园' in ' '.join(chosen['reasons']) and '保留午餐' in ' '.join(chosen['reasons'])
    assert chosen['leg']['transfer_before_minutes']==20 and chosen['leg']['station_buffer_minutes']==30
    assert chosen['leg']['ticket_total'] is None
    assert await svc.load(doc['id'])==doc


@pytest.mark.asyncio
async def test_all_conflict_never_invokes_model(multi):
    _,body=multi;body['candidates']=body['candidates'][:1]
    with patch('app.services.ticket_assistant.get_llm') as model:
        r=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert not r['recommendations'] and r['excluded_count']==1 and '冲突' in r['message']
    model.assert_not_called()


@pytest.mark.asyncio
async def test_rule_fallback_can_only_choose_feasible_candidates(multi):
    _,body=multi
    with patch('app.services.ticket_assistant.get_llm',side_effect=RuntimeError('offline')):
        r=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert r['ranked_by']=='rules' and [x['candidate']['id'] for x in r['recommendations']]==['late']


@pytest.mark.asyncio
@pytest.mark.parametrize('margin', [0, 3, 30, 31])
async def test_departure_margin_is_extra_to_saved_buffers_and_tight_fit_is_explicit(multi, margin):
    doc, body = multi
    detail = doc['snapshots']['h']['days_detail'][-1]
    last = max(i['end_minutes'] for i in detail['timeline_schedule'] if i['kind'] != 'free_time')
    old_leg = doc['plan']['transfers'][-1]['leg']
    buffers = sum(old_leg[k] for k in ('transfer_before_minutes', 'station_buffer_minutes', 'lodging_buffer_minutes'))
    depart = last + buffers + margin
    clock = lambda n: f'{n // 60:02d}:{n % 60:02d}'
    body['candidates'] = [ticket('fit', clock(depart), clock(depart + 60))]
    with patch('app.services.ticket_assistant.get_llm', side_effect=RuntimeError('offline')):
        result = await rank_tickets(TicketRankingRequest.model_validate(body))
    chosen = result['recommendations'][0]
    text = ' '.join(chosen['reasons'])
    assert f'现有缓冲外剩余{margin}分钟' in text
    assert ('时间较紧' in text) == (margin <= 30)
    assert '接驳缓冲后重查' in text if margin <= 30 else '时间较紧' not in text
    assert all(chosen['leg'][k] == old_leg[k] for k in ('transfer_before_minutes', 'station_buffer_minutes', 'lodging_buffer_minutes'))
    assert await svc.load(doc['id']) == doc


@pytest.mark.asyncio
async def test_cross_day_outside_trip_is_explicitly_excluded(multi):
    _,body=multi;body['candidates']=[ticket('cross','23:00','23:59')]
    body['candidates'][0]['arrival']='2026-10-27T02:00'
    r=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert not r['recommendations'] and '跨出' in r['excluded'][0]['conflicts'][0]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[lambda b:b['context'].update(revision=2),lambda b:b['context'].update(to_stop='unknown'),lambda b:b['query'].update(passengers=1),lambda b:b['query'].update(from_place='北京')])
async def test_mismatched_scope_is_rejected_before_ai(multi,change):
    _,body=multi;change(body)
    with patch('app.services.ticket_assistant.get_llm') as model,pytest.raises(HTTPException) as error:
        await rank_tickets(TicketRankingRequest.model_validate(body))
    assert error.value.status_code in {409,422};model.assert_not_called()


@pytest.mark.asyncio
async def test_late_model_and_adoption_refuse_changed_multi_snapshot(multi):
    doc,body=multi
    async def mutate(*args,**kwargs):
        async def transform(d,session): d['plan']['budget']=9999;return d
        await svc.write(doc['id'],1,transform)
        return Ranking(ids=['late'])
    with patch('app.services.ticket_assistant.get_llm',return_value=object()),patch('app.services.ticket_assistant.invoke_structured_or_json',side_effect=mutate),pytest.raises(HTTPException) as error:
        await rank_tickets(TicketRankingRequest.model_validate(body))
    assert error.value.status_code==409
    from app.api.routes.multicity import preview,Change
    with pytest.raises(HTTPException) as error:
        await preview(doc['id'],Change(plan=MultiTrip.model_validate((await svc.load(doc['id']))['plan']),revision=2,ticket_basis=svc.token(doc)))
    assert error.value.status_code==409


@pytest.mark.asyncio
async def test_single_city_filters_saved_meals_and_refuses_changed_day(case):
    client,draft,url=case
    loaded=(await client.get('/api/trip/draft/'+draft)).json()
    body=dict(query=dict(priority='balanced',mode='train',direction='inbound',from_place='苏州',to_place='上海',date='2026-10-16',passengers=1),
        candidates=[{**ticket('early','07:00','08:00',day='2026-10-16'), 'from_station':'苏州','to_station':'上海'},
                    {**ticket('late','22:00','23:00',day='2026-10-16'), 'from_station':'苏州','to_station':'上海'}],
        context=dict(kind='draft',draft_id=draft,request=loaded['request'],days_detail=loaded['days_detail']))
    before=await trip_draft_service.get_draft(draft)
    with patch('app.services.ticket_assistant.get_llm',side_effect=RuntimeError('offline')):
        r=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert r['checked_schedule'] and r['excluded_count']==1 and r['recommendations'][0]['candidate']['id']=='late'
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before.days_detail_json
    await client.post(url+'/recompute',json={'day_start_time':'09:00'})
    with pytest.raises(HTTPException) as error:
        await rank_tickets(TicketRankingRequest.model_validate(body))
    assert error.value.status_code==409
    response=await client.post('/api/trip/draft/'+draft+'/journey',json={'journey':None,'ticket_basis':r['schedule_basis']})
    assert response.status_code==409


@pytest.mark.asyncio
async def test_single_city_arrival_margin_uses_synchronized_start_without_saving(case):
    client, draft, _ = case
    loaded = (await client.get('/api/trip/draft/'+draft)).json()
    before = await trip_draft_service.get_draft(draft)
    body = dict(query=dict(mode='train', direction='outbound', from_place='上海', to_place='苏州',
                           date='2026-10-15', passengers=1),
                candidates=[{**ticket('arrive', '07:00', '08:00', day='2026-10-15'),
                             'from_station':'上海', 'to_station':'苏州'}],
                context=dict(kind='draft', draft_id=draft, request=loaded['request'], days_detail=loaded['days_detail']))
    with patch('app.services.ticket_assistant.get_llm', side_effect=RuntimeError('offline')):
        result = await rank_tickets(TicketRankingRequest.model_validate(body))
    text = ' '.join(result['recommendations'][0]['reasons'])
    assert '含缓冲09:30后可开始，当前安排09:30开始，现有缓冲外剩余0分钟' in text
    assert '时间较紧' in text
    after = await trip_draft_service.get_draft(draft)
    assert after.request_json == before.request_json and after.days_detail_json == before.days_detail_json

@pytest.mark.asyncio
async def test_finalized_single_city_during_model_refuses_late_recommendation(case):
    client,draft,_=case
    loaded=(await client.get('/api/trip/draft/'+draft)).json()
    body=dict(query=dict(priority='balanced',mode='train',direction='inbound',from_place='苏州',to_place='上海',date='2026-10-16',passengers=1),
        candidates=[{**ticket('late','22:00','23:00',day='2026-10-16'),'from_station':'苏州','to_station':'上海'}],
        context=dict(kind='draft',draft_id=draft,request=loaded['request'],days_detail=loaded['days_detail']))
    before=await trip_draft_service.get_draft(draft)
    finalized=copy.copy(before);finalized.status='finalized'
    async def finish(*args,**kwargs):
        reader.return_value=finalized
        return Ranking(ids=['late'])
    with patch('app.services.ticket_schedule.trip_draft_service.get_draft',new=AsyncMock(return_value=before)) as reader,patch('app.services.ticket_assistant.get_llm',return_value=object()),patch('app.services.ticket_assistant.invoke_structured_or_json',side_effect=finish),pytest.raises(HTTPException) as error:
        await rank_tickets(TicketRankingRequest.model_validate(body))
    assert error.value.status_code==409
    actual=await trip_draft_service.get_draft(draft)
    assert actual.request_json==before.request_json and actual.days_detail_json==before.days_detail_json



@pytest.mark.asyncio
async def test_single_city_http_recommend_preview_confirm_preserves_facts_and_unknown_total(case):
    client,draft,_=case
    loaded=(await client.get('/api/trip/draft/'+draft)).json()
    before=await trip_draft_service.get_draft(draft)
    body=dict(query=dict(priority='balanced',mode='train',direction='inbound',from_place='苏州',to_place='上海',date='2026-10-16',passengers=1),
        candidates=[{**ticket('late','22:00','23:00',day='2026-10-16'),'from_station':'苏州','to_station':'上海'}],
        context=dict(kind='draft',draft_id=draft,request=loaded['request'],days_detail=loaded['days_detail']))
    with patch('app.services.ticket_assistant.get_llm',side_effect=RuntimeError('offline')):
        ranked=await client.post('/api/tickets/recommend',json=body)
    assert ranked.status_code==200,ranked.text
    result=ranked.json();chosen=result['recommendations'][0]['leg']
    journey=dict(origin_city='上海',return_city='上海',inbound=chosen)
    change=dict(journey=journey,synchronize=True,ticket_basis=result['schedule_basis'])
    url='/api/trip/draft/'+draft+'/journey'
    preview=await client.post(url,json=change);assert preview.status_code==200,preview.text
    assert (await trip_draft_service.get_draft(draft)).request_json==before.request_json
    saved=await client.post(url,json={**change,'preview_token':preview.json()['preview_token']})
    assert saved.status_code==200 and saved.json()['saved']
    actual=(await client.get('/api/trip/draft/'+draft)).json()
    assert actual['request']['journey']['inbound']['ticket_total'] is None
    assert actual['request']['journey']['inbound']['price_source']=='unknown'
    for old,new in zip(loaded['days_detail'],actual['days_detail']):
        for k in ('attractions','meals','locked_attraction_names','removed_attraction_names','rest_periods'):
            assert old[k]==new[k]
    assert (await client.post(url,json=change)).status_code==409


@pytest.mark.asyncio
async def test_multi_city_http_recommend_preview_confirm_preserves_city_snapshots(multi):
    from httpx import ASGITransport,AsyncClient
    from app.api.main import app
    doc,body=multi
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as client:
        with patch('app.services.ticket_assistant.get_llm',side_effect=RuntimeError('offline')):
            ranked=await client.post('/api/tickets/recommend',json=body)
        assert ranked.status_code==200,ranked.text
        result=ranked.json();chosen=result['recommendations'][0]['leg']
        proposed=copy.deepcopy(doc['plan'])
        proposed['transfers'][-1]['leg']=chosen
        url='/api/multi-trips/'+doc['id']
        change=dict(plan=proposed,revision=1,ticket_basis=result['schedule_basis'])
        preview=await client.post(url+'/preview',json=change)
        assert preview.status_code==200,preview.text
        assert await svc.load(doc['id'])==doc
        saved=await client.put(url,json={**change,'preview_token':preview.json()['preview_token']})
        assert saved.status_code==200,saved.text
        actual=await svc.load(doc['id'])
        assert actual['snapshots']==doc['snapshots']
        assert actual['revision']==2
        leg=actual['plan']['transfers'][-1]['leg']
        assert leg['ticket_total'] is None and leg['price_source']=='unknown'
        assert leg['transfer_before_minutes']==doc['plan']['transfers'][-1]['leg']['transfer_before_minutes']
        stale=await client.post(url+'/preview',json={**change,'revision':2})
        assert stale.status_code==409
