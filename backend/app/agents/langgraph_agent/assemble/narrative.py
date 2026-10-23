"""Descriptions are projections of saved itinerary facts, never free-form claims."""
from collections import Counter
from typing import Optional

from ....models.schemas import DayDetail, DayPlan, WeatherInfo, TripPlan

DESCRIPTION_SOURCE = "itinerary_facts_v1"


def refresh_day_description(day: DayDetail | DayPlan, weather: Optional[WeatherInfo] = None) -> str:
    """Brief guidance and separate confirmations, projected afresh after every edit."""
    intent = day.trip_intent
    names = [a.name for a in day.attractions]
    lines = []
    if names:
        focus = '、'.join(names[:2])
        lines.append(f"今天先把时间留给{focus}。" if len(names) <= 2 else
                     f"今天从{names[0]}开始，接着去{names[1]}，后面还有{len(names)-2}处安排。")
    else:
        lines.append('今天还没有安排景点，可以先把用餐和休息时间定下来。')
    expected = Counter([('attraction',a.name) for a in day.attractions]+[('meal',m.name) for m in day.meals])
    order = [(i.get('kind'),i.get('ref_name')) for i in day.timeline_order if i.get('kind') in {'attraction','meal'}]
    entries = [(i.get('kind'),i.get('ref_name')) for i in day.timeline_schedule if i.get('kind') in {'attraction','meal'}]
    valid = Counter(order) == expected and order == entries and bool(day.timeline_schedule) and day.timeline_schedule[0].get('start_time') == (day.day_start_time or '08:00')
    schedule = day.timeline_schedule if valid else []
    travel = sum(i.get('duration',0) for i in schedule if i.get('kind') == 'travel')
    visits = sum(a.visit_duration or 120 for a in day.attractions)
    if schedule and names:
        lines.append(f'目前游览约{visits//60}小时{visits%60:02d}分，路上约{travel}分钟；这还没有算排队和额外休息。')
    elif names:
        lines.append('活动之间的时间还没有核对，先不要据此预约固定时段。')
    foodie = intent.get('dining_style') == 'dedicated' or '美食' in intent.get('preferences', [])
    if day.meals and foodie:
        meal = next((m for m in day.meals if m.type in {'lunch','dinner'}),day.meals[0])
        lines.append(f'这次想把美食作为重点，可以先核实{meal.name}的营业时间，再为用餐留出更充裕的时间。')
    unlocked = [n for n in names if n not in getattr(day,'locked_attraction_names',[])]
    if len(names)>1 and unlocked:
        lines.append(f'如果当天时间不够，可以先缩短{unlocked[-1]}的停留，再看是否保留。')
    elif names:
        lines.append('如果当天时间不够，可以先减少购物或拍照停留；需要删减景点时再调整安排。')
    rest_items=[x for x in schedule if x.get('kind')=='rest']
    if rest_items:
        lines.append('今天把'+ '、'.join(x['start_time']+'—'+x['end_time'] for x in rest_items)+'留给休息，这段时间不再安排景点。可以在当时所在区域歇一歇；如想回酒店，需要重新核对路线。')
    elif day.rest_periods:
        lines.append('你想留出的休息时段还没放进当前安排，先处理下方冲突，再决定减少哪些活动。')
    gaps = sorted((x for x in schedule if x.get('kind') == 'free_time' and x.get('duration',0)>60), key=lambda x:x['duration'], reverse=True)
    if gaps:
        lines.append(f"{gaps[0]['start_time']}至{gaps[0]['end_time']}尚未安排，可以留在附近自由活动。如想去别处，先核对后续路程。")
    from ....services.journey_service import conflicts
    travel_notes = day.travel_window.get("notes",[])
    if travel_notes: lines.append("；".join(travel_notes)+"。")
    pending = [("与交通或休息安排冲突：" if day.rest_periods else "与抵离交通冲突：")+"；".join(conflicts(day))] if conflicts(day) else []
    pending.extend(n for n in travel_notes if "超出所填旅行日期" in n)
    pending += [w for w in day.meal_warnings if '分钟未安排' in w]
    if not day.hotel and day.overnight_stay:
        pending.append('今晚住宿尚未确定，请先确认住宿再核对晚间回程。')
    unknown = [a.name for a in day.attractions if a.ticket_price is None]
    if unknown: pending.append('票价待确认：'+'、'.join(unknown)+'；未知不代表免费。')
    if names: pending.append('请核对景点开放日期和预约要求。')
    if weather and weather.date == day.date and _weather_fact(weather):
        pending.append('本次天气预报：'+_weather_fact(weather)+'；出发前再看一次最新预报。')
    else: pending.append('当日天气尚未获取，出发前请查看预报。')
    if day.hotel and day.overnight_stay:
        from ....services.hotel_quotes import hotel_cost_for_date
        _, missing = hotel_cost_for_date(day.hotel, day.date)
        pending.extend(missing)
    pending.extend(day.meal_adjustments)
    pending.extend(day.meal_warnings)
    if intent.get('dietary_requirements'):
        pending.append('饮食要求「'+intent['dietary_requirements']+'」尚未由店家确认。')
    day.pending_confirmations = list(dict.fromkeys(pending))
    day.description = '\n\n'.join(lines)
    day.description_source = DESCRIPTION_SOURCE
    return day.description


async def write_day_narrative_llm(day_detail: DayDetail, weather: Optional[WeatherInfo] = None,
                                  free_text_input: Optional[str] = None, city: str = "") -> str:
    """Compatibility callable; refreshes facts without an LLM or extra service request."""
    return refresh_day_description(day_detail, weather)


def _weather_fact(weather: Optional[WeatherInfo]) -> str:
    if not weather:
        return ""
    parts = []
    for prefix, label in [("day", "白天"), ("night", "夜间")]:
        condition = getattr(weather, prefix + "_weather")
        if condition:
            temperature = getattr(weather, prefix + "_temp")
            has_temp = prefix + "_temp" in weather.model_fields_set and str(temperature).strip()
            parts.append(label + condition + (f" {temperature}°C" if has_temp else ""))
    return "，".join(parts)


def _confirmed_overall_suggestions(plan) -> str:
    """Keep cost, nights, meal coverage and weather tied to saved facts."""
    nights = sum(bool(day.overnight_stay) for day in plan.days)
    lines = [f"这次在{plan.city}安排了{len(plan.days)}天，需要{nights}晚住宿。先确认最想去的景点能否预约，再把住宿和往返交通定下来；每天的取舍建议在‘每日行程’里。"]
    budget = plan.budget
    if budget:
        lines.append(f"目前已知费用预估小计{budget.total:g}元，其中已核对的住宿参考报价为{budget.total_hotels:g}元。餐饮按候选人均价估算，市内交通暂按每人每天50元计；{f"其中往返大交通已录入小计{budget.total_intercity:g}元（按全体同行人数合计）" if plan.journey else "往返大交通尚未纳入"}，这还不是整趟旅行的最终花费。")
        if not budget.is_complete:
            lines.append('仍需核对：'+'；'.join(budget.unknown_cost_items)+'。未知价格不代表免费。')
        if '旧记录费用完整性未核对' in budget.unknown_cost_items:
            lines.append('这是一份旧记录，旧记录费用口径待核对。')
        if budget.budget_limit is not None:
            status = ('已知费用已超出上限，建议先调整大项开销' if budget.is_within_budget is False else
                      '按当前预估在上限内，预订前还要再核价' if budget.is_within_budget is True else
                      '费用有缺项，暂不能判断是否在上限内')
            lines.append(f'你设定的预算上限为{budget.budget_limit}元；{status}。')
    meal_notes = list(dict.fromkeys(note for day in plan.days for note in day.meal_adjustments+day.meal_warnings))
    if meal_notes:
        lines.append('用餐方面，'+'；'.join(meal_notes)+'。')
    forecasts = [f'{w.date}：{_weather_fact(w)}' for w in plan.weather_info if _weather_fact(w)]
    lines.append('本次查询的天气预报：'+'；'.join(forecasts)+'。出发前再看一次最新预报。' if forecasts else
                 '天气数据未获取，请在出发前查询，再决定衣物和雨具。')
    return '\n\n'.join(lines)


def _generate_weather_summary_fallback(trip_plan) -> str:
    from collections import Counter
    if not trip_plan.weather_info:
        return ""
    weathers = [w.day_weather for w in trip_plan.weather_info if w.day_weather]
    if not weathers:
        return ""
    counter = Counter(weathers)
    most_common = counter.most_common(1)[0][0]
    if len(counter) == 1:
        return f"{most_common}为主"
    second = counter.most_common(2)[1][0] if len(counter) > 1 else ""
    return f"{most_common}间{second}为主" if second else f"{most_common}为主"



def refresh_trip_descriptions(plan: TripPlan) -> TripPlan:
    weather_by_date = {w.date: w for w in plan.weather_info}
    for index, day in enumerate(plan.days):
        if plan.journey:
            from types import SimpleNamespace
            from ....services.journey_service import apply_context
            apply_context(day,SimpleNamespace(journey=plan.journey,start_date=plan.start_date,end_date=plan.end_date))
        if not plan.journey and "overnight_stay" not in day.model_fields_set:
            day.overnight_stay = index < len(plan.days) - 1
        refresh_day_description(day, weather_by_date.get(day.date))
    # Legacy monetary completeness was not recorded; it cannot become confirmed by parsing defaults.
    if plan.budget and not {"is_complete", "unknown_cost_items"} <= plan.budget.model_fields_set:
        plan.budget.is_complete = False
        plan.budget.is_within_budget = None
        if "旧记录费用完整性未核对" not in plan.budget.unknown_cost_items:
            plan.budget.unknown_cost_items.append("旧记录费用完整性未核对")
    if plan.budget:
        from .budget import compute_day_budget, combine_budgets
        old_unknown = [item for item in plan.budget.unknown_cost_items if "分钟未安排" not in item]
        day_budgets = []
        for day in plan.days:
            detail = DayDetail.model_validate(day.model_dump())
            detail.companion_count = plan.companions.count if plan.companions else 1
            day_budgets.append(compute_day_budget(detail))
            # Read projection only: avoid displaying a stale hotel charge in old schedules.
            for entry in day.timeline_schedule:
                if entry.get('kind') == 'hotel':
                    from ....services.hotel_quotes import hotel_cost_for_date
                    amount, missing = hotel_cost_for_date(day.hotel, day.date) if day.hotel and day.overnight_stay else (0, [])
                    entry['cost'] = (amount if amount or not missing else None) if day.overnight_stay else None
        plan.budget = combine_budgets(day_budgets, plan.budget.budget_limit)
        plan.budget.unknown_cost_items = list(dict.fromkeys(plan.budget.unknown_cost_items + old_unknown))
        if plan.budget.unknown_cost_items:
            plan.budget.is_complete = False
            if plan.budget.is_within_budget is True:
                plan.budget.is_within_budget = None
    plan.trip_tagline = f"{plan.city} · {len(plan.days)}日行程"
    plan.overall_suggestions = _confirmed_overall_suggestions(plan)
    plan.weather_summary = _generate_weather_summary_fallback(plan)
    plan.narrative_source = DESCRIPTION_SOURCE
    return plan
