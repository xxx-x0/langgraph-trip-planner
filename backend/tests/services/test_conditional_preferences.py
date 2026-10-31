"""Synthetic request scenarios and saved-route replay; no live providers or model."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest
from pydantic import ValidationError
from app.models.schemas import DayDetail, DayTimeConstraints, DraftDayContext, TripRequest
from app.services.ticket_assistant import TicketRankingRequest, rank_tickets
from app.services.journey_comparison import synchronize_days
from app.services.journey_service import conflicts
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from tests.services.test_ticket_assistant import body
from tests.api.test_narrative_consistency import case


@pytest.mark.asyncio
async def test_unspecified_offers_factual_tradeoffs_without_a_model_or_winner():
    b = body(); b['query'].pop('priority')
    with patch('app.services.ticket_assistant.get_llm') as model:
        result = await rank_tickets(TicketRankingRequest.model_validate(b))
    assert result['ranked_by'] == 'options' and result['preference_status'] == 'unspecified'
    assert result['recommendations'] and '未设唯一首选' in result['message']
    model.assert_not_called()
    assert all(r['leg']['ticket_total'] is None for r in result['recommendations'])


@pytest.mark.asyncio
@pytest.mark.parametrize('preferences', [
    {'accepted_seats':['商务座']}, {'max_reference_fare_per_person':400},
    {'daytime_hard':True,'departure_after':'09:00','arrival_before':'21:00'},
])
async def test_unmatched_hard_conditions_never_silently_relax(preferences):
    b = body(); b['query']['preferences'] = preferences
    with patch('app.services.ticket_assistant.get_llm') as model:
        result = await rank_tickets(TicketRankingRequest.model_validate(b))
    assert result['recommendations'] == [] and len(result['preference_excluded']) == 2
    assert '未自动放宽' in result['message']
    model.assert_not_called()


@pytest.mark.parametrize('prefs', [{'accepted_seats':['']}, {'accepted_seats':['一等座']*2},
                                   {'arrival_before':'25:00'}, {'max_reference_fare_per_person':-1}])
def test_invalid_condition_values_rejected(prefs):
    b=body();b['query']['preferences']=prefs
    with pytest.raises(ValidationError): TicketRankingRequest.model_validate(b)


def arrival_fixture(contract):
    # Frozen artificial T10 facts; never use its reference to produce expected output.
    inp=json.loads((Path(__file__).parents[2]/'evals/datasets/inputs/T10.json').read_text())
    original=DayDetail.model_validate(inp['saved_state']['days_detail'][0])
    original.time_constraints=contract
    request=TripRequest.model_validate(inp['saved_state']['request'])
    changed=request.model_copy(deep=True)
    changed.journey.outbound.arrival_time='2027-04-12T09:10'
    payload=SimpleNamespace(days=[DraftDayContext(day_index=0,date=original.date)],days_detail=[original])
    return original,changed,payload


@pytest.mark.parametrize('contract,accepted', [(None,False),
    (DayTimeConstraints(),True),
    (DayTimeConstraints(allow_start_shift=False,fixed_start_time='11:00'),False),
    (DayTimeConstraints(appointments=[dict(kind='attraction',ref_name='SYN_T10_活动',start_time='11:00')]),False)])
def test_arrival_delay_requires_movable_time_and_never_moves_an_appointment(contract,accepted):
    original,request,payload=arrival_fixture(contract)
    before=original.model_dump(mode='json')
    days,impacts,_=synchronize_days(payload,request)
    assert bool(impacts[0]['conflicts']) != accepted
    if accepted:
        assert days[0].day_start_time == '11:10'
        assert days[0].timeline_schedule[-1]['end_time'] == '12:10'
    else:
        assert days[0].day_start_time == '11:00'
        assert days[0].timeline_schedule == original.timeline_schedule
    assert original.model_dump(mode='json') == before


def test_fixed_appointment_wait_and_earliest_boundary_are_real_constraints():
    original,_,_=arrival_fixture(DayTimeConstraints(earliest_start_time='10:00',appointments=[
        dict(kind='attraction',ref_name='SYN_T10_活动',start_time='12:00')]))
    original.day_start_time='11:00';schedule_day(original)
    activity=next(r for r in original.timeline_schedule if r['kind']=='attraction')
    assert activity['start_time']=='12:00' and not conflicts(original)
    original.day_start_time='09:59';schedule_day(original)
    assert any('最早出发' in p for p in conflicts(original))


@pytest.mark.parametrize('index,fit', [(0,'requires_adjustment'),(1,'direct')])
def test_multi_city_recommendation_exposes_arrival_shift_without_changing_saved_snapshots(index,fit):
    from app.models.multicity import MultiTrip
    from app.models.journey import JourneyLeg
    from app.services.ticket_assistant import TicketQuery, ObservedTicket
    from app.services.ticket_schedule import ScheduleCheck, TicketContext
    from app.services import multicity
    data=json.loads((Path(__file__).parents[2]/'evals/datasets/inputs/T11.json').read_text())
    for snapshot in data['saved_state']['snapshots'].values():
        for day in snapshot['days_detail']:
            if day: day['time_constraints']={'allow_start_shift':True,'appointments':[]}
    before=copy.deepcopy(data['saved_state'])
    check=ScheduleCheck();check.context=TicketContext.model_validate(data['context'])
    check.query=TicketQuery.model_validate(data['query']);check.document=data['saved_state']
    check.plan=MultiTrip.model_validate(data['saved_state']['plan'])
    check.edge=next(e for e in multicity.edges(check.plan) if e[:2]==('a','b'))
    check.affected={'a','b'};check.old_leg=JourneyLeg.model_validate(data['saved_state']['plan']['transfers'][0]['leg'])
    _,_,problems,assessment=check.assess(ObservedTicket.model_validate(data['candidates'][index]))
    assert not problems and assessment['fit_status']==fit
    if index==0:
        assert assessment['adjustments']==[dict(date='2027-04-14',city='杭州',kind='attraction',
            ref_name='SYN_T11_b',before='20:00',after='21:00',shift_minutes=60)]
    else: assert assessment['adjustments']==[]
    assert data['saved_state']==before


@pytest.mark.asyncio
async def test_fixed_time_survives_recompute_force_and_failed_delete_without_writes(case):
    client,draft,url=case
    constraint={'allow_start_shift':True,'appointments':[{'kind':'attraction','ref_name':'甲园','start_time':'09:00'}]}
    response=await client.post(url+'/recompute',json={'time_constraints':constraint})
    assert response.status_code==200,response.text
    saved=(await client.get('/api/trip/draft/'+draft)).json()['days_detail'][0]
    assert saved['time_constraints']['appointments']==constraint['appointments']
    # A disappearing appointment is rejected, not silently discarded.
    response=await client.post(url+'/recompute',json={'removed_attraction_names':['甲园']})
    assert response.status_code==409
    assert (await client.get('/api/trip/draft/'+draft)).json()['days_detail'][0]==saved
    response=await client.post(url+'/assemble?force=true',json={})
    assert response.status_code==200 and response.json()['day_detail']['time_constraints']==saved['time_constraints']


@pytest.mark.asyncio
async def test_ai_receives_fixed_clock_facts_and_cannot_replace_them(case):
    from app.api.routes import trip_draft
    client,_,url=case
    contract={'allow_start_shift':True,'appointments':[dict(kind='attraction',ref_name='甲园',start_time='09:00')]}
    saved=(await client.post(url+'/recompute',json={'time_constraints':contract})).json()['day_detail']
    reply=dict(attractions_order=[a['name'] for a in saved['attractions']],
        meals=trip_draft._saved_meals(DayDetail.model_validate(saved)),
        time_constraints={'allow_start_shift':False,'fixed_start_time':'01:00'})
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',
            new=AsyncMock(return_value=SimpleNamespace(content=json.dumps(reply)))) as model:
        response=await client.post(url+'/ai-rearrange',json={})
    assert response.status_code==200,response.text
    assert '09:00' in model.call_args.args[1][1].content
    assert response.json()['day_detail']['time_constraints']==saved['time_constraints']
