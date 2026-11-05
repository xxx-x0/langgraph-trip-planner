import asyncio
import copy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.models.journey import Journey, JourneyPlanning
from app.models.schemas import TripRequest
from app.services import journey_options as svc
from app.services.external_calls import ExternalServiceError, FailureKind
from app.services.journey_service import travel_window


def request():
    return dict(city='北京', start_date='2026-11-10', end_date='2026-11-12', travel_days=3,
                transportation='公共交通', accommodation='酒店', companions={'count': 1},
                journey=dict(origin_city='上海', return_city='上海', planning={}))


def candidate(ident, direction='outbound', *, mode='train', dep='08:00', arr='12:00', fare=300, **extra):
    day = '2026-11-10' if direction == 'outbound' else '2026-11-12'
    return dict(id=ident, service=ident, mode=mode, source='12306' if mode == 'train' else 'ctrip',
                departure=day+'T'+dep, arrival=day+'T'+arr,
                from_station='上海虹桥' if direction == 'outbound' else '北京南',
                to_station='北京南' if direction == 'outbound' else '上海虹桥',
                fare_per_person=fare, seat='二等座' if mode == 'train' else '经济舱', availability='available', **extra)


def body(out=None, back=None, **extra):
    batches = []
    for direction, values in [('outbound', out if out is not None else [candidate('G1')]), ('inbound', back if back is not None else [candidate('G2', 'inbound', dep='19:00', arr='23:00')])]:
        for mode in ('train', 'flight'):
            tickets = [c for c in values if c['mode'] == mode]
            if tickets:
                batches.append(dict(query=dict(mode=mode, direction=direction,
                    from_place='上海' if direction == 'outbound' else '北京', to_place='北京' if direction == 'outbound' else '上海',
                    date='2026-11-10' if direction == 'outbound' else '2026-11-12', passengers=1), candidates=tickets))
    return svc.JourneyOptionsRequest.model_validate(dict(request=request(), batches=batches, **extra))


@pytest.fixture(autouse=True)
def models(monkeypatch):
    # Pure rules are selected in most cases; no external service is implied.
    monkeypatch.setattr(svc, 'get_llm', lambda: object())
    monkeypatch.setattr(svc, 'invoke_structured_or_json', AsyncMock(side_effect=RuntimeError('simulated outage')))
    monkeypatch.setattr(svc, 'choose_option', AsyncMock(side_effect=ExternalServiceError('windhub', 'ticket_choice', FailureKind.TIMEOUT)))


def test_unknown_transit_keeps_two_day_and_one_day_trips_open():
    req = TripRequest.model_validate(request())
    assert JourneyPlanning().arrival_policy == 'unreserved'
    assert [travel_window(req, d)['usable_minutes'] for d in [req.start_date, req.end_date]] == [840, 840]
    req.end_date = req.start_date; req.travel_days = 1
    assert not travel_window(req, req.start_date)['unavailable']


@pytest.mark.asyncio
async def test_actual_times_leave_partial_first_and_last_days_and_no_invented_fare():
    payload = body(priority='time'); before = payload.model_dump()
    result = await svc.recommend_journeys(payload)
    proposal = result['options'][0]
    assert proposal['days'][0]['window']['start_minutes'] == 13*60+30
    assert proposal['days'][-1]['window']['end_minutes'] == 16*60+45
    assert all(not d['window']['unavailable'] for d in proposal['days'])
    assert proposal['reference_fare_per_person'] == 600
    assert proposal['journey']['outbound']['ticket_total'] is None
    assert proposal['journey']['outbound']['booking_status'] == 'planned'
    assert payload.model_dump() == before


@pytest.mark.asyncio
async def test_price_and_time_use_all_candidates_without_models():
    outs = [candidate('expensive-fast', arr='10:00', fare=800), candidate('cheap-slow', arr='18:00', fare=200), candidate('unknown', arr='09:00', fare=None)]
    cheap = await svc.recommend_journeys(body(outs, priority='price', engine='jev'))
    fast = await svc.recommend_journeys(body(outs, priority='time', engine='jev'))
    assert cheap['options'][0]['journey']['outbound']['service_number'] == 'cheap-slow'
    assert fast['options'][0]['journey']['outbound']['service_number'] == 'unknown'
    assert svc.choose_option.await_count == svc.invoke_structured_or_json.await_count == 0


@pytest.mark.asyncio
async def test_models_receive_cross_mode_city_time_after_hard_filters(monkeypatch):
    outs = [candidate('train'), candidate('flight', mode='flight', arr='10:00', fare=500), candidate('overprice', fare=2000), candidate('unknown', fare=None)]
    async def choose(state, criteria, instructions):
        assert state['已选景点游览分钟'] == 300
        assert all(c['去程']['service_number'] not in {'overprice', 'unknown'} for c in criteria.values())
        assert {c['去程']['mode'] for c in criteria.values()} == {'flight', 'train'}
        assert all(c['逐日目的地可用分钟']['2026-11-10'] > 0 for c in criteria.values())
        return next(i for i, c in criteria.items() if c['去程']['mode'] == 'flight')
    monkeypatch.setattr(svc, 'choose_option', choose)
    result = await svc.recommend_journeys(body(outs, engine='jev', selected_visit_minutes=300, preferences={'max_reference_fare_per_person': 600}))
    assert result['ranked_by'] == 'jev'
    assert result['options'][0]['journey']['outbound']['mode'] == 'flight'
    assert len(result['rejected']) == 2
    assert svc.invoke_structured_or_json.await_count == 0


@pytest.mark.asyncio
async def test_missing_flight_does_not_block_rail_or_reserve_a_whole_missing_day():
    result = await svc.recommend_journeys(body(back=[], priority='time'))
    proposal = result['options'][0]
    assert not proposal['complete']
    assert proposal['journey']['inbound'] is None
    assert proposal['days'][-1]['window']['usable_minutes'] == 840
    assert proposal['reference_fare_per_person'] is None


@pytest.mark.asyncio
async def test_booked_leg_and_custom_buffers_are_kept():
    payload = body(replace_planned=True, priority='time')
    booked = payload.batches[0].candidates[0].leg(1)
    booked.booking_status = 'booked'; booked.service_number = 'already-booked'; booked.transfer_after_minutes = 105
    payload.request.journey.outbound = booked
    result = await svc.recommend_journeys(payload)
    assert result['options'][0]['journey']['outbound'] == booked.model_dump(mode='json')


@pytest.mark.asyncio
async def test_no_viable_pair_never_creates_a_service_or_empty_day_rule():
    result = await svc.recommend_journeys(body([], [], priority='time'))
    assert not result['options']
    assert '可调整' in result['message']


@pytest.mark.asyncio
async def test_invalid_choice_falls_back_without_modifying_candidates(monkeypatch):
    payload = body(); before = payload.model_dump()
    monkeypatch.setattr(svc, 'invoke_structured_or_json', AsyncMock(return_value=svc.Ranking(ids=['invented'])))
    result = await svc.recommend_journeys(payload)
    assert result['ranked_by'] == 'rules'
    assert payload.model_dump() == before
    assert result['options'][0]['journey']['outbound']['service_number'] == 'G1'


@pytest.mark.asyncio
async def test_jev_failure_uses_default_ai_and_cancellation_propagates(monkeypatch):
    monkeypatch.setattr(svc, 'invoke_structured_or_json', AsyncMock(return_value=svc.Ranking(ids=['journey_0'])))
    result = await svc.recommend_journeys(body(engine='jev'))
    assert result['ranked_by'] == 'ai' and 'Jev 本次未完成' in result['message']
    monkeypatch.setattr(svc, 'choose_option', AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await svc.recommend_journeys(body(engine='jev'))


@pytest.mark.parametrize('field,value', [('date', '2026-11-11'), ('passengers', 2), ('from_place', '杭州')])
def test_old_route_date_or_party_is_rejected(field, value):
    raw = body().model_dump(mode='json')
    raw['batches'][0]['query'][field] = value
    with pytest.raises(ValidationError):
        svc.JourneyOptionsRequest.model_validate(raw)
