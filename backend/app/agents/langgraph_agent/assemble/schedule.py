"""A saved schedule shared by draft, narrative and final result."""
import re
from ....models.schemas import DayDetail, RouteSegment, DiningCategory


def clock_minutes(value: str | None) -> int:
    try:
        hour, minute = (value or '08:00').split(':')
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        return 480


def clock(value: int) -> str:
    return f'{value // 60:02d}:{value % 60:02d}'


def route_minutes(value: str) -> int:
    hours = re.search(r'(\d+(?:\.\d+)?)\s*小时', value)
    minutes = re.search(r'(\d+(?:\.\d+)?)\s*分钟', value)
    if hours or minutes:
        return round((float(hours.group(1)) * 60 if hours else 0)
                     + (float(minutes.group(1)) if minutes else 0))
    return 20


def opening_windows(text: str | None) -> list[tuple[int, int]]:
    if not text:
        return []
    # Date-dependent exceptions are not evidence that a particular travel date is open.
    simplified = text.replace('周一至周日','').replace('星期一至星期日','')
    if re.search(r'周[一二三四五六日天]|星期|节假日|暂停|歇业|关闭|休息', simplified):
        return []
    if '24小时' in text or text.strip() in {'00:00-24:00', '全天营业'}:
        return [(0, 1440)]
    result = []
    for a, b in re.findall(r'(\d{1,2}:\d{2})\s*[-–—~至]\s*(\d{1,2}:\d{2})', text):
        start, end = clock_minutes(a), clock_minutes(b)
        result.append((start, end if end > start else end + 1440))
    return result


def estimated_lunch_anchor(attractions, start: str | None) -> str:
    if not attractions:
        return 'hotel_start'
    elapsed = clock_minutes(start) + 20
    choices = []
    for attraction in attractions:
        elapsed += attraction.visit_duration or 120
        choices.append((abs(elapsed + 15 - 720), attraction.name))
        elapsed += 20
    return min(choices)[1]


def schedule_day(detail: DayDetail) -> None:
    detail.route_segments = [RouteSegment.model_validate(r) for r in detail.route_segments]
    routes = {(r.from_name, r.to_name): r for r in detail.route_segments}
    attractions = {a.name: a for a in detail.attractions}
    meals = {m.name: m for m in detail.meals}
    now = clock_minutes(detail.day_start_time)
    warnings, schedule = [], []
    previous = None
    actual_slots = set()

    def append(kind, name, duration, **extra):
        nonlocal now
        schedule.append(dict(kind=kind, ref_name=name, start_time=clock(now),
                             end_time=clock(now + duration), start_minutes=now,
                             end_minutes=now + duration, duration=duration, **extra))
        now += duration

    for entry in detail.timeline_order:
        kind, name = entry['kind'], entry['ref_name']
        if kind == 'hotel' and entry.get('phase') == 'start':
            previous = name
            continue
        if kind not in {'hotel', 'meal', 'attraction'}:
            continue
        if previous and previous != name:
            route = routes.get((previous, name))
            duration = route_minutes(route.duration) if route else 20
            append('travel', f'{previous} → {name}', duration,
                   mode=route.mode if route else '', distance=route.distance if route else '',
                   detail=route.detail if route else '路线尚未获取，暂按20分钟估算')
        if kind == 'attraction' and name in attractions:
            a = attractions[name]
            append(kind, name, a.visit_duration or 120, cost=a.ticket_price,
                   detail=a.description[:60])
        elif kind == 'meal' and name in meals:
            meal = meals[name]
            is_main = meal.category == DiningCategory.MAIN or meal.type in {'main', 'breakfast', 'lunch', 'dinner'}
            target_start = {'breakfast': 420, 'lunch': 690, 'dinner': 1050}.get(meal.preferred_slot or meal.type, now)
            if is_main and meal.type == 'main':
                target_start = 690 if now < 900 else 1050 if now < 1290 else now
            ready = max(now, target_start)
            windows = opening_windows(meal.open_hours)
            if windows:
                possible = [max(ready, start) for start, end in windows if max(ready, start) + 60 <= end]
                if possible:
                    ready = min(possible)
                else:
                    warnings.append(f'{meal.name}预计{clock(ready)}用餐不在营业时段内，请调整或更换')
            elif meal.open_hours:
                warnings.append(f'{meal.name}营业时间格式需人工确认：{meal.open_hours}')
            else:
                warnings.append(f'{meal.name}营业时间未知，请确认')
            if ready > now:
                gap = ready - now
                if gap > 60:
                    # Stay at the previous stop until departure, not at the restaurant for hours.
                    travel = schedule.pop() if schedule and schedule[-1]['kind'] == 'travel' else None
                    if travel:
                        now -= travel['duration']
                    append('free_time', '这段时间尚未安排', gap,
                           detail='可自行休息或补充活动；若离开当前区域，需重新核对后续路线。')
                    if travel:
                        append('travel', travel['ref_name'], travel['duration'],
                               **{k: travel[k] for k in ('mode', 'distance', 'detail') if k in travel})
                    warnings.append(f'{clock(ready-gap-(travel["duration"] if travel else 0))}起有{gap}分钟未安排，请调整出发时间或补充下午活动')
                else:
                    append('wait', '等待用餐时段', gap, detail='预留短暂休息；未固定景点预约时间')
            if is_main:
                original = meal.type
                meal.type = 'breakfast' if now < 630 else 'lunch' if now <= 870 else 'dinner' if now >= 1050 else 'main'
                actual_slots.add(meal.type)
                if original in {'breakfast', 'lunch', 'dinner'} and original != meal.type:
                    warnings.append(f'{meal.name}原{slot_label(original)}在{clock(now)}，已按实际时段标记为{slot_label(meal.type)}')
            append(kind, name, 60 if is_main else 30, cost=meal.estimated_cost,
                   detail=slot_label(meal.type))
        elif kind == 'hotel' and detail.hotel:
            append(kind, name, 30, cost=detail.hotel.estimated_cost, detail=detail.hotel.address)
        previous = name

    if detail.attractions or detail.meals:
        for slot in ['lunch', 'dinner']:
            if slot not in actual_slots:
                warnings.append(f'{slot_label(slot)}未安排，请自行安排或补充餐厅')
        if clock_minutes(detail.day_start_time) < 600 and 'breakfast' not in actual_slots:
            warnings.append('早餐未安排，请出发前自行安排')
    detail.timeline_schedule = schedule
    detail.meal_warnings = list(dict.fromkeys(warnings))


def slot_label(value: str) -> str:
    return {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'main': '正餐'}.get(value, value)
