"""Explicit clock facts shared by preview, save and recommendation. No persistence."""


def minute(value):
    hour, minutes = value.split(':')
    return int(hour) * 60 + int(minutes)


def time_conflicts(day):
    contract = getattr(day, 'time_constraints', None)
    if contract is None:
        return []
    errors = []
    start = day.day_start_time or '08:00'
    try:
        start_minutes = minute(start)
    except (ValueError, AttributeError):
        return ['开始时间格式无效，请核对当天时间']
    if contract.earliest_start_time and start_minutes < minute(contract.earliest_start_time):
        errors.append('开始时间早于本次设置的最早出发时间')
    if contract.fixed_start_time and start_minutes != minute(contract.fixed_start_time):
        errors.append('固定开始时间不可随交通平移')
    for fixed in contract.appointments:
        rows = [x for x in day.timeline_schedule if x['kind'] == fixed.kind and x['ref_name'] == fixed.ref_name]
        if len(rows) != 1 or rows[0]['start_minutes'] != minute(fixed.start_time):
            errors.append(f'{fixed.ref_name}未满足固定时刻{fixed.start_time}')
    return errors


def activity_times(day):
    raw = day.model_dump(mode='json') if hasattr(day, 'model_dump') else day
    return {(x['kind'], x['ref_name']): (x['start_minutes'], x['end_minutes'])
            for x in raw.get('timeline_schedule', []) if x['kind'] in {'attraction', 'meal', 'rest'}}


def legacy_time_changes(before, proposed):
    if (before.time_constraints is None and before.timeline_schedule
            and proposed.travel_window.get('intercity_cost') is not None
            and activity_times(before) != activity_times(proposed)):
        return ['旧安排尚未声明可移动时刻，保留原时间；可在当天“时间约束”中核对后设置']
    return []


def schedule_changes(before, after, city):
    originals = {(d.date if hasattr(d, 'date') else d['date']): d for d in before if d}
    changes = []
    for d in after:
        if not d:
            continue
        raw = d.model_dump(mode='json') if hasattr(d, 'model_dump') else d
        old = originals.get(raw['date'])
        if not old:
            continue
        a, b = activity_times(old), activity_times(raw)
        for key in a:
            if key in b and a[key] != b[key]:
                clock = lambda v: f'{v // 60:02d}:{v % 60:02d}'
                changes.append(dict(date=raw['date'], city=city, kind=key[0], ref_name=key[1],
                                    before=clock(a[key][0]), after=clock(b[key][0]),
                                    shift_minutes=b[key][0] - a[key][0]))
    return changes
