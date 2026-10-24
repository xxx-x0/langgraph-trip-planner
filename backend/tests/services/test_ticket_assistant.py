"""Synthetic ticket facts; these tests do not query a ticketing provider."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from pydantic import ValidationError
from app.services.ticket_assistant import TicketRankingRequest, Ranking, rank_tickets


def body():
    return dict(query=dict(mode='train',from_place='上海',to_place='北京',date='2026-10-27',passengers=2,priority='balanced'),
        candidates=[dict(id='rail_1',mode='train',service='G100',from_station='上海虹桥',to_station='北京南',departure='2026-10-27T08:00',arrival='2026-10-27T12:30',seat='二等座',fare_per_person=500,availability='available',source='12306'),
                    dict(id='rail_2',mode='train',service='G102',from_station='上海虹桥',to_station='北京南',departure='2026-10-27T18:00',arrival='2026-10-27T23:00',seat='二等座',fare_per_person=None,availability='unknown',source='12306')])


@pytest.mark.asyncio
async def test_ai_only_reorders_supplied_facts_and_does_not_promote_reference_price():
    b=body()
    with patch('app.services.ticket_assistant.get_llm',return_value=object()), patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(return_value=Ranking(ids=['rail_2','rail_1']))) as model:
        result=await rank_tickets(TicketRankingRequest.model_validate(b))
    assert result['ranked_by']=='ai'
    assert result['recommendations'][0]['candidate']==b['candidates'][1]
    leg=result['recommendations'][1]['leg']
    assert leg['ticket_total'] is None and leg['price_source']=='unknown'
    assert leg['passengers']==2 and leg['booking_status']=='planned'
    assert 'CNY 500' in leg['price_note'] and leg['quoted_at']
    assert 'rail_1' in model.call_args.args[1][1][1]


@pytest.mark.asyncio
@pytest.mark.parametrize('answer',[Ranking(ids=['invented']),Ranking(ids=['rail_1','rail_1']),RuntimeError('network')])
async def test_invalid_or_failed_model_is_honestly_labelled_rule_sort(answer):
    with patch('app.services.ticket_assistant.get_llm',return_value=object()), patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(**({'side_effect':answer} if isinstance(answer,Exception) else {'return_value':answer}))):
        result=await rank_tickets(TicketRankingRequest.model_validate(body()))
    assert result['ranked_by']=='rules' and 'AI本次未完成' in result['message']
    assert result['recommendations'][0]['candidate']['id']=='rail_1'


@pytest.mark.asyncio
async def test_waitlist_and_unavailable_never_reach_model():
    b=body();b['candidates'][0]['availability']='waitlist';b['candidates'][1]['availability']='unavailable'
    with patch('app.services.ticket_assistant.get_llm') as model:
        result=await rank_tickets(TicketRankingRequest.model_validate(b))
    assert not result['recommendations'];model.assert_not_called()


@pytest.mark.parametrize('edit',[
    lambda b:b['candidates'][0].update(departure='2026-10-28T08:00'),
    lambda b:b['candidates'][0].update(arrival='2026-10-27T07:00'),
    lambda b:b['candidates'][0].update(source='ctrip'),
    lambda b:b['candidates'][0].update(mode='flight'),
    lambda b:b['candidates'][0].update(departure='2026-10-27'),
    lambda b:b['candidates'][0].update(fare_per_person=-1),
    lambda b:b['candidates'][1].update(id='rail_1'),
    lambda b:b['query'].update(passengers=0),
])
def test_inconsistent_candidate_batch_rejected(edit):
    b=body();edit(b)
    with pytest.raises(ValidationError):TicketRankingRequest.model_validate(b)


@pytest.mark.asyncio
async def test_cancellation_does_not_turn_into_successful_fallback():
    with patch('app.services.ticket_assistant.get_llm',return_value=object()), patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):await rank_tickets(TicketRankingRequest.model_validate(body()))


@pytest.mark.asyncio
async def test_price_priority_keeps_unknown_price_after_known_price():
    b=body();b['query']['priority']='price'
    with patch('app.services.ticket_assistant.get_llm',side_effect=ValueError('no key')):
        result=await rank_tickets(TicketRankingRequest.model_validate(b))
    assert [r['candidate']['id'] for r in result['recommendations']]==['rail_1','rail_2']


@pytest.mark.asyncio
async def test_api_contract_no_database_write():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.api.routes.ticket_assistant import router
    app=FastAPI();app.include_router(router,prefix='/api')
    async with AsyncClient(transport=ASGITransport(app),base_url='http://test') as client:
        with patch('app.services.ticket_assistant.get_llm',side_effect=ValueError('no key')):
            response=await client.post('/api/tickets/recommend',json=body())
        assert response.status_code==200
        assert response.json()['ranked_by']=='rules'
        invalid=body();invalid['query']['date']='invalid'
        assert (await client.post('/api/tickets/recommend',json=invalid)).status_code==422
