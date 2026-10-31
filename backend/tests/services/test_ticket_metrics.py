"""Numeric objectives use the whole feasible set without an LLM or hidden tie weight."""
import copy
from pathlib import Path
import json
from unittest.mock import patch

import pytest

from app.services.ticket_assistant import TicketRankingRequest, rank_tickets
from app.services.ticket_preferences import metric_order
from tests.services.test_ticket_schedule import multi


def input_body(id):
    data=json.loads((Path(__file__).parents[2]/'evals/datasets/inputs'/f'{id}.json').read_text())
    return {k:data[k] for k in ['query','candidates','context']}


@pytest.mark.asyncio
@pytest.mark.parametrize('priority,expected', [('price',['SYN_T04_B','SYN_T04_A','SYN_T04_C']),
                                           ('time',['SYN_T04_A','SYN_T04_C','SYN_T04_B'])])
async def test_explicit_metric_never_uses_model_and_keeps_facts(priority,expected):
    body=input_body('T04');body['context']=None;body['query']['priority']=priority
    with patch('app.services.ticket_assistant.get_llm',side_effect=AssertionError('must not call')) as model:
        result=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert result['ranked_by']=='metric'
    assert [r['candidate']['id'] for r in result['recommendations']]==expected
    model.assert_not_called()
    original={c['id']:c for c in body['candidates']}
    assert all(r['candidate']==original[r['candidate']['id']] and r['leg']['ticket_total'] is None for r in result['recommendations'])


def test_same_duration_does_not_use_cheaper_fare_as_hidden_tie_breaker():
    body=input_body('T04');request=TicketRankingRequest.model_validate({**body,'context':None})
    a,b,c=request.candidates
    assert [v.id for v in metric_order([c,b,a],'time')]==[c.id,a.id,b.id]


@pytest.mark.asyncio
async def test_unknown_prices_stay_unknown_and_are_not_described_as_cheaper():
    body=input_body('T05');body['context']=None
    result=await rank_tickets(TicketRankingRequest.model_validate(body))
    ids=[r['candidate']['id'] for r in result['recommendations']]
    assert ids==['SYN_T05_A','SYN_T05_C','SYN_T05_B']
    unknown=result['recommendations'][-1]
    assert unknown['candidate']['fare_per_person'] is None
    assert '较低' not in ' '.join(unknown['reasons'])
    for c in body['candidates']:c['fare_per_person']=None
    result=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert '均未知' in result['message'] and '不代表价格高低' in result['message']


@pytest.mark.asyncio
@pytest.mark.parametrize('priority',['price','time'])
async def test_metric_still_checks_schedule_and_preserves_snapshot(multi,priority):
    doc,body=multi;body['query']['priority']=priority
    with patch('app.services.ticket_assistant.get_llm',side_effect=AssertionError('no model')):
        result=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert [r['candidate']['id'] for r in result['recommendations']]==['late']
    assert result['ranked_by']=='metric' and result['excluded_count']==1
    from app.services import multicity
    assert await multicity.load(doc['id'])==doc


@pytest.mark.asyncio
async def test_hard_conditions_are_applied_before_metric():
    body=input_body('T04');body['context']=None;body['query'].update(priority='price',preferences={'accepted_seats':['商务座']})
    with patch('app.services.ticket_assistant.get_llm') as model:
        result=await rank_tickets(TicketRankingRequest.model_validate(body))
    assert not result['recommendations'] and result['empty_reason']=='preferences'
    assert len(result['preference_excluded'])==3;model.assert_not_called()
