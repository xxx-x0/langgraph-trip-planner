"""Replay archived structured facts, with no database, website or model calls.

Run from backend with --source pointing to the LTP-27 evidence directory.
This is an offline regression, never a new live-provider verification.
"""
import argparse
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.models.multicity import MultiTrip
from app.services import multicity
from app.services.ticket_assistant import ObservedTicket, TicketQuery
from app.services.ticket_schedule import TicketContext, ScheduleCheck, day_facts


async def replay(source):
    checks, reasons = {}, {}
    for mode, service, margin in [('train', 'G3106', 3), ('flight', 'MU5192', 10)]:
        initial = json.loads((source / f'{mode}-initial.json').read_text())
        saved = json.loads((source / f'{mode}-saved.json').read_text())
        original = json.dumps(initial, sort_keys=True)
        transfer = saved['plan']['transfers'][-1]
        fact = transfer['leg']
        candidate = ObservedTicket(id=mode+'_archived', mode=mode, service=fact['service_number'],
            from_station=fact['departure_station'], to_station=fact['arrival_station'],
            departure=fact['departure_time'], arrival=fact['arrival_time'], seat=fact['seat_class'],
            source='12306' if mode == 'train' else 'ctrip', availability='unknown')
        query = TicketQuery(mode=mode, direction='outbound', from_place='杭州',
            to_place=saved['plan']['destination']['name'], date=fact['departure_time'][:10],
            passengers=fact['passengers'])
        context = TicketContext(kind='multi', draft_id=initial['id'], revision=initial['revision'],
            from_stop=transfer['from_stop'], to_stop=transfer['to_stop'])
        with patch.object(multicity, 'load', new=AsyncMock(return_value=initial)):
            check = await ScheduleCheck().initialize(context, query)
            leg, notes, conflicts = check.evaluate(candidate)
            await check.assert_current()
        reasons[mode] = notes
        checks[mode+'_service'] = candidate.service == service
        checks[mode+'_fits'] = not conflicts
        checks[mode+'_margin'] = any(f'现有缓冲外剩余{margin}分钟' in n for n in notes)
        checks[mode+'_tight_fit_note'] = any('时间较紧' in n for n in notes)
        for key in ('mode', 'service_number', 'departure_station', 'arrival_station', 'departure_time',
                    'arrival_time', 'passengers', 'seat_class', 'transfer_before_minutes',
                    'station_buffer_minutes', 'baggage_minutes', 'transfer_after_minutes', 'lodging_buffer_minutes'):
            checks[mode+'_'+key] = getattr(leg, key) == fact[key]
        checks[mode+'_unknown_total'] = leg.ticket_total is None and leg.price_source == 'unknown'
        plan = MultiTrip.model_validate(initial['plan'])
        for edge in plan.transfers:
            if (edge.from_stop, edge.to_stop) == (context.from_stop, context.to_stop):
                edge.leg = leg
        projected = multicity.projection(plan, initial['snapshots'])
        checks[mode+'_no_projection_conflict'] = not projected['conflicts']
        for city, expected in zip(projected['cities'], saved['summary']['cities'], strict=True):
            checks[mode+'_'+city['id']+'_saved_day_facts'] = (
                [day_facts(d) for d in city['days']] == [day_facts(d) for d in expected['days']])
        # A user increasing the old departure buffer must make a formerly
        # borderline candidate conflict; no hidden shortening is allowed.
        old = check.old_leg or leg
        check.old_leg = old.model_copy(update={'transfer_before_minutes':old.transfer_before_minutes+margin+1})
        checks[mode+'_larger_buffer_rejects'] = bool(check.evaluate(candidate)[2])
        checks[mode+'_input_unchanged'] = original == json.dumps(initial, sort_keys=True)
    result = dict(source_scope='Archived live itinerary/ticket facts replayed offline; no new provider/model/database calls',
                  checks=checks, count=len(checks), passed=all(checks.values()), reasons=reasons)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output file; never overwrite prior evidence")
    result = asyncio.run(replay(args.source))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Offline checks: {sum(result['checks'].values())}/{result['count']}")
    raise SystemExit(0 if result['passed'] else 1)
