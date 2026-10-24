"""Comparison and conservative rescheduling based only on supplied transport facts."""
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from ..models.journey import Journey, local_instant
from ..models.schemas import TripRequest
from .journey_service import travel_window, apply_context, conflicts, stay_dates
from ..agents.langgraph_agent.assemble.schedule import schedule_day, clock, clock_minutes, opening_windows
from ..agents.langgraph_agent.assemble.meals import meal_plan_violations
from ..agents.langgraph_agent.assemble.budget import compute_day_budget, combine_budgets
from ..agents.langgraph_agent.assemble.narrative import refresh_day_description


class JourneyCandidate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    journey: Journey
    start_date: str | None = None
    end_date: str | None = None


class JourneyComparison(BaseModel):
    candidates: list[JourneyCandidate] = Field(min_length=1, max_length=6)


def synchronize_days(payload, request):
    """Reuse saved routes only; never delete/reorder stops or change a main meal slot."""
    details, impacts, budgets = [], [], []
    for ctx, old in zip(payload.days, payload.days_detail):
        window = travel_window(request, ctx.date)
        problems, changes = [], []
        detail = old.model_copy(deep=True) if old else None
        if detail:
            # A removed journey must restore ordinary date-based lodging nights.
            detail.overnight_stay = ctx.date < request.end_date
            apply_context(detail, request)
            proposed = detail.model_copy(deep=True)
            proposed.day_start_time = clock(max(clock_minutes(detail.day_start_time), window.get('start_minutes', 0)))
            schedule_day(proposed)
            problems = conflicts(proposed) + meal_plan_violations(proposed, detail)
            attractions = {a.name:a for a in proposed.attractions}
            for item in proposed.timeline_schedule:
                if item['kind'] == 'attraction':
                    hours = opening_windows(attractions[item['ref_name']].open_hours)
                    if hours and not any(lo <= item['start_minutes'] and item['end_minutes'] <= hi for lo,hi in hours):
                        problems.append(f"{item['ref_name']}超出已知开放时间")
            if not problems:
                if detail.day_start_time != proposed.day_start_time:
                    changes.append(f'市内出发从{detail.day_start_time}调整到{proposed.day_start_time}')
                if detail.rest_periods and detail.timeline_schedule != proposed.timeline_schedule:
                    changes.append('休息已纳入时间轴，后续活动时间随之核对；景点、时长和正餐保留')
                detail = proposed
            else:
                # Retain saved facts instead of silently losing lunch or cutting attractions.
                problems = list(dict.fromkeys(conflicts(detail) + problems))
                changes.append('当前活动无法完整放入抵离及休息时段，保留原排序、餐次和时间；需手动删减后重算')
            # Keeping the old activity times must not retain an invalid lodging charge.
            from .hotel_quotes import hotel_cost_for_date
            for entry in detail.timeline_schedule:
                if entry.get('kind') == 'hotel':
                    amount, missing = hotel_cost_for_date(detail.hotel, detail.date) if detail.hotel and detail.overnight_stay else (0, [])
                    entry['cost'] = (amount if amount or not missing else None) if detail.overnight_stay else None
            detail.day_budget = compute_day_budget(detail)
            refresh_day_description(detail, ctx.weather)
            budgets.append(detail.day_budget)
        else:
            # The skeleton still contributes transport and unknown remaining activities.
            from ..models.schemas import Budget
            budgets.append(Budget(total=window.get('intercity_cost',0), total_transportation=window.get('intercity_cost',0),
                                  total_intercity=window.get('intercity_cost',0), is_complete=False,
                                  unknown_cost_items=[ctx.date+'市内行程尚未装配']+window.get('unknown_cost_items',[])))
        details.append(detail)
        impacts.append(dict(date=ctx.date, window=window, conflicts=problems, changes=changes,
                            activities=[a.name for a in (detail.attractions if detail else ctx.attractions)]))
    return details, impacts, combine_budgets(budgets,request.budget)


def compare_candidates(payload, candidates, now=None):
    now = now or datetime.now(timezone.utc)
    results = []
    for index, candidate in enumerate(candidates):
        raw = payload.request.model_dump(mode='json')
        raw.update(journey=candidate.journey.model_dump(mode='json'),
                   start_date=candidate.start_date or raw['start_date'], end_date=candidate.end_date or raw['end_date'])
        request = TripRequest.model_validate(raw)
        same_dates = (request.start_date,request.end_date)==(payload.request.start_date,payload.request.end_date)
        if same_dates:
            _, impacts, budget = synchronize_days(payload,request)
        else:
            from datetime import date,timedelta
            impacts=[dict(date=(date.fromisoformat(request.start_date)+timedelta(days=i)).isoformat(), changes=[], conflicts=[],
                          window=travel_window(request,(date.fromisoformat(request.start_date)+timedelta(days=i)).isoformat())) for i in range(request.travel_days)]
            budget=None
        j=request.journey
        legs=[v for v in (j.outbound,j.inbound) if v]
        complete=len(legs)==2
        missing, freshness=[],[]
        duration=0;connections=0;night=0;transfers=0
        for label,leg in [('去程',j.outbound),('返程',j.inbound)]:
            if not leg:
                missing.append(label+'未填写');continue
            dep=local_instant(leg.departure_time,leg.departure_timezone)
            arr=local_instant(leg.arrival_time,leg.arrival_timezone)
            duration+=round((arr.astimezone(timezone.utc)-dep.astimezone(timezone.utc)).total_seconds()/60)+leg.transfer_before_minutes+leg.station_buffer_minutes+leg.baggage_minutes+leg.transfer_after_minutes+leg.lodging_buffer_minutes
            transfers+=leg.transfer_before_minutes+leg.transfer_after_minutes
            if leg.connections is None: missing.append(label+'中转次数未知')
            else: connections+=leg.connections
            from datetime import timedelta
            door_start=(dep.astimezone(timezone.utc)-timedelta(minutes=leg.transfer_before_minutes+leg.station_buffer_minutes+(leg.lodging_buffer_minutes if label=='返程' else 0))).astimezone(dep.tzinfo)
            door_end=(arr.astimezone(timezone.utc)+timedelta(minutes=leg.baggage_minutes+leg.transfer_after_minutes+(leg.lodging_buffer_minutes if label=='去程' else 0))).astimezone(arr.tzinfo)
            night+=int(door_start.hour<7 or door_start.hour>=22 or door_end.hour<7 or door_end.hour>=22 or door_start.date()!=door_end.date())
            if leg.currency!='CNY' or leg.ticket_total is None or leg.extras_total is None: complete=False
            if leg.extra_costs and any(v is None for v in leg.extra_costs.model_dump().values()): complete=False
            if not leg.baggage_policy: missing.append(label+'行李条件待确认')
            if not leg.refund_policy: missing.append(label+'退改条件待确认')
            status='已支付记录' if leg.price_source=='paid' else '需再次核价'
            if leg.price_source!='paid' and leg.quote_expires_at and local_instant(leg.quote_expires_at,leg.departure_timezone)<=now:
                status='报价已过期';complete=False
            elif leg.quoted_at and local_instant(leg.quoted_at,leg.departure_timezone)>now:
                status='记录时间在未来，请修正';complete=False
            freshness.append(label+'：'+status)
        total=round(sum(x['window'].get('intercity_cost',0) for x in impacts),2)
        start,end=stay_dates(request)
        from datetime import date
        result=dict(index=index,name=candidate.name,journey=j.model_dump(mode='json'),start_date=request.start_date,end_date=request.end_date,
                    same_dates=same_dates,known_total=total,cost_complete=complete,
                    door_minutes=duration if len(legs)==2 else None,
                    comfort_known=len(legs)==2 and all(l.connections is not None for l in legs),
                    connections=connections,night_legs=night,transfer_minutes=transfers,
                    stay_nights=(date.fromisoformat(end)-date.fromisoformat(start)).days,
                    available_minutes=sum(max(0,min(1320,x['window'].get('end_minutes',1440))-max(480,x['window'].get('start_minutes',0))) for x in impacts),
                    missing=list(dict.fromkeys(missing+[m for x in impacts for m in x['window'].get('unknown_cost_items',[])])),
                    freshness=freshness,impacts=impacts,budget=budget.model_dump(mode='json') if budget else None,badges=[])
        results.append(result)
    # Never call an incomplete subtotal 'cheapest'. Comfort is an explained proxy, not a rating.
    for badge,eligible,key in [
        ('已填交通费用较低',[r for r in results if r['cost_complete']],lambda r:r['known_total']),
        ('门到门较快',[r for r in results if r['door_minutes'] is not None],lambda r:r['door_minutes']),
        ('少些折腾',[r for r in results if r['comfort_known']],lambda r:(r['night_legs'],r['connections'],r['transfer_minutes'],r['door_minutes']))]:
        if len(eligible)>=2 and len({key(r) for r in eligible})>1:
            min(eligible,key=key)['badges'].append(badge)
    return results
