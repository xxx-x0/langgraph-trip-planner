"""Descriptions are projections of saved itinerary facts, never free-form claims."""
from collections import Counter
from typing import Optional

from ....models.schemas import DayDetail, DayPlan, WeatherInfo, TripPlan

DESCRIPTION_SOURCE = "itinerary_facts_v1"


def refresh_day_description(day: DayDetail | DayPlan, weather: Optional[WeatherInfo] = None) -> str:
    """Brief guidance and separate confirmations, projected afresh after every edit."""
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
    unlocked = [n for n in names if n not in getattr(day,'locked_attraction_names',[])]
    if len(names)>1 and unlocked:
        lines.append(f'如果当天时间不够，可以先缩短{unlocked[-1]}的停留，再看是否保留。')
    elif names:
        lines.append('如果当天时间不够，可以先减少购物或拍照停留；需要删减景点时再调整安排。')
    gaps = sorted((x for x in schedule if x.get('kind') == 'free_time' and x.get('duration',0)>60), key=lambda x:x['duration'], reverse=True)
    if gaps:
        lines.append(f"{gaps[0]['start_time']}至{gaps[0]['end_time']}尚未安排，可以留在附近自由活动。如想去别处，先核对后续路程。")
    pending = []
    unknown = [a.name for a in day.attractions if a.ticket_price is None]
    if unknown: pending.append('票价待确认：'+'、'.join(unknown)+'；未知不代表免费。')
    if names: pending.append('请核对景点开放日期和预约要求。')
    if weather and weather.date == day.date and _weather_fact(weather):
        pending.append('本次天气预报：'+_weather_fact(weather)+'；出发前再看一次最新预报。')
    else: pending.append('当日天气尚未获取，出发前请查看预报。')
    pending.extend(day.meal_adjustments)
    pending.extend(day.meal_warnings)
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
    lines = [f"这次在{plan.city}安排了{len(plan.days)}天；请按每日保存的安排核对开放日期和预约要求。"]
    if plan.budget:
        lines.append(f"当前保存的费用预估为{plan.budget.total:g}元；费用口径和缺项尚未核对，不能据此判断最终花费或是否在预算上限内。")
    notes = list(dict.fromkeys(note for day in plan.days for note in day.meal_adjustments + day.meal_warnings))
    if notes: lines.append('用餐待确认：'+'；'.join(notes)+'。')
    forecasts = [f'{w.date}：{_weather_fact(w)}' for w in plan.weather_info if _weather_fact(w)]
    lines.append('本次查询的天气预报：'+'；'.join(forecasts)+'。出发前再看一次最新预报。' if forecasts else '天气数据未获取，请在出发前查询预报。')
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
    for day in plan.days:
        refresh_day_description(day, weather_by_date.get(day.date))
    plan.trip_tagline = f"{plan.city} · {len(plan.days)}日行程"
    plan.overall_suggestions = _confirmed_overall_suggestions(plan)
    plan.weather_summary = _generate_weather_summary_fallback(plan)
    plan.narrative_source = DESCRIPTION_SOURCE
    return plan
