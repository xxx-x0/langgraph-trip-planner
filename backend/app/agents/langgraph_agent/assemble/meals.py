"""Keep saved meal intent when an attraction disappears or an AI proposal omits it."""
from collections import Counter
from copy import deepcopy

from ....models.schemas import DayDetail, DiningCategory, DraftDayContext
from .schedule import clock_minutes, estimated_lunch_anchor, opening_windows, slot_label

MAIN_SLOTS = ('breakfast', 'lunch', 'dinner')


def is_main(meal) -> bool:
    return meal.category == DiningCategory.MAIN or meal.type in (*MAIN_SLOTS, 'main')


def desired_slot(meal):
    return meal.preferred_slot or (meal.type if meal.type in MAIN_SLOTS else None)


def saved_meals(current: DayDetail) -> list[dict]:
    anchors = {}
    anchor = 'hotel_start'
    for item in current.timeline_order:
        if item.get('kind') == 'attraction':
            anchor = item.get('ref_name', '')
        elif item.get('kind') == 'hotel':
            anchor = 'hotel_start' if item.get('phase') == 'start' else 'hotel_end'
        elif item.get('kind') == 'meal':
            anchors[item.get('ref_name')] = anchor
    return [{**m.model_dump(mode='json'), 'insert_after': anchors.get(m.name, '')}
            for m in current.meals]


def repair_deleted_anchors(meals, previous: DayDetail | None, order: list[str]):
    """Keep the old gap: nearest preceding surviving attraction, otherwise day start."""
    result, notes = deepcopy(meals), []
    if previous is None:
        return result, notes
    present = set(order)
    previous_names = [i.get('ref_name') for i in previous.timeline_order if i.get('kind') == 'attraction']
    meal_positions = {i.get('ref_name'): n for n, i in enumerate(previous.timeline_order) if i.get('kind') == 'meal'}
    repaired = set()
    for meal in result:
        anchor = meal.get('insert_after') or ''
        if not anchor or anchor in present or anchor in {'hotel_start', 'hotel_end'}:
            continue
        if anchor not in previous_names:
            continue
        if meal.get("schedule_mode") == "auto":
            notes.append(f"原景点已删除，{meal['name']}按原餐次重新安排。")
            continue
        predecessors = previous_names[:previous_names.index(anchor)]
        surviving = [n for n in predecessors if n in present]
        meal['insert_after'] = surviving[-1] if surviving else 'hotel_start'
        repaired.add(meal['name'])
        label = f"{meal['insert_after']}之后" if surviving else '首个景点之前' if order else '本日用餐安排中'
        notes.append(f"原景点已删除，{meal['name']}保留在{label}。")
    # Several deleted anchors can collapse onto one gap; preserve their original meal order.
    for anchor in {m.get('insert_after') for m in result if m['name'] in repaired}:
        indices = [i for i,m in enumerate(result) if m.get('insert_after') == anchor and m['name'] in meal_positions]
        ordered = sorted((result[i] for i in indices), key=lambda m: meal_positions[m['name']])
        for i,meal in zip(indices,ordered): result[i] = meal
    return result, notes


def _auto_anchor(slot, attractions, start):
    if slot == 'breakfast' or not attractions:
        return 'hotel_start'
    if slot == 'lunch':
        return estimated_lunch_anchor(attractions, start)
    return attractions[-1].name


def normalize_ai_meals(proposals, current: DayDetail, ctx: DraftDayContext, order: list[str]):
    """AI selects facts from the pool/current meals; every existing main meal gets a seat."""
    sources = {c.name: c.model_dump(mode='json') for category in type(ctx.dining_pool).model_fields
               for c in getattr(ctx.dining_pool, category)}
    current_by_name = {m.name: m for m in current.meals}
    for meal in current.meals:
        sources.setdefault(meal.name, meal.model_dump(mode='json'))
    required = [m for m in current.meals if is_main(m)]
    assigned, result, notes, used = set(), [], [], set()
    manual = [m for m in saved_meals(current) if m.get('schedule_mode') == 'manual']
    manual, repairs = repair_deleted_anchors(manual, current, order)
    manual_names = {m['name'] for m in manual}
    notes.extend(repairs)
    for meal in manual:
        result.append(meal); used.add(meal['name'])
        assigned.update(i for i,m in enumerate(required) if m.name == meal['name'])
    if manual: notes.append('已保留你手动选择的餐厅和用餐位置。')
    by_attr = {a.name:a for a in ctx.attractions}
    attractions = [by_attr[n] for n in order if n in by_attr]
    for proposal in proposals or []:
        name = proposal.get('name')
        if name in manual_names:
            continue
        if name in used:
            notes.append('AI重复推荐同一餐厅，已忽略重复项。')
            continue
        source = sources.get(name)
        if source is None:
            notes.append('AI推荐的餐厅不在当前可用列表中，已忽略。')
            continue
        meal = deepcopy(source)
        main = meal.get('category') == 'main' or meal.get('type') in (*MAIN_SLOTS, 'main')
        slot = proposal.get('preferred_slot') or proposal.get('type')
        slot = slot if slot in MAIN_SLOTS else None
        if main:
            original = current_by_name.get(name)
            # Reusing an existing restaurant cannot silently change its intended main slot.
            if original and is_main(original):
                if slot and desired_slot(original) and slot != desired_slot(original):
                    notes.append(f"{name}沿用已保存的{slot_label(desired_slot(original))}餐次。")
                slot = desired_slot(original)
            matching = [i for i,m in enumerate(required) if i not in assigned and (slot is None or desired_slot(m) in {slot,None})]
            if not matching:
                notes.append('AI新增的正餐不属于当前已安排餐次，未自动加入；如需要请手动添加。')
                continue
            index = next((i for i in matching if required[i].name == name),matching[0])
            assigned.add(index)
            slot = desired_slot(required[index]) or slot
            anchor = proposal.get('insert_after')
            valid_anchor = anchor in set(order)|{'hotel_start','hotel_end'}
            meal.update(type=slot or 'main', preferred_slot=slot,
                        schedule_mode='manual' if valid_anchor else 'auto')
            meal['insert_after'] = anchor if valid_anchor else _auto_anchor(slot,attractions,current.day_start_time)
        else:
            # Only selection/position comes from the model, never price/coordinates/hours.
            meal.update(type=meal.get('category') or meal.get('type') or 'snack', schedule_mode='manual')
            anchor = proposal.get('insert_after') or ''
            meal['insert_after'] = anchor if anchor in set(order)|{'hotel_start','hotel_end'} else (order[-1] if order else 'hotel_start')
        used.add(name);result.append(meal)
    for i,original in enumerate(required):
        if i in assigned:
            continue
        # Reserve the original restaurant for its own slot rather than duplicating its name.
        if original.name in used:
            raise ValueError('已有正餐餐厅存在重复，无法安全重排；请先核对用餐安排')
        slot = desired_slot(original)
        meal = original.model_dump(mode='json')
        meal.update(schedule_mode='auto', preferred_slot=slot, type=slot or 'main',
                    insert_after=_auto_anchor(slot,attractions,current.day_start_time))
        result.append(meal);used.add(original.name)
        notes.append(f"AI未完整安排{slot_label(slot) if slot else '正餐'}，已保留{original.name}。")
    # Within each attraction gap, coffee/snacks precede a later dinner rather than vice versa.
    elapsed = clock_minutes(current.day_start_time)
    estimated = {'hotel_start':elapsed}
    for attraction in attractions:
        elapsed += 20 + (attraction.visit_duration or 120)
        estimated[attraction.name] = elapsed
    targets = {'breakfast':420,'lunch':690,'dinner':1050}
    result.sort(key=lambda m: targets.get(m.get('preferred_slot'),estimated.get(m.get('insert_after'),elapsed)))
    return result, list(dict.fromkeys(notes))


def meal_plan_violations(detail: DayDetail, required_from: DayDetail) -> list[str]:
    """Check actual main slots and known opening hours after real routes, never just labels."""
    required = Counter(desired_slot(m) for m in required_from.meals if is_main(m))
    actual = Counter(m.type for m in detail.meals if is_main(m))
    problems = [f'{slot_label(slot)}未能保留' for slot,count in required.items()
                if slot is not None and actual[slot] < count]
    if sum(actual.values()) < sum(required.values()):
        problems.append('已有正餐数量减少')
    meals = {m.name:m for m in detail.meals}
    for item in detail.timeline_schedule:
        if item.get('kind') != 'meal':
            continue
        meal = meals[item['ref_name']]
        if any(w in (meal.name+' '+(meal.open_hours or '')) for w in ('暂停营业','永久关闭','已歇业')):
            problems.append(f'{meal.name}已被来源标为停止营业')
        windows = opening_windows(meal.open_hours)
        if windows and not any(a <= item['start_minutes'] and item['end_minutes'] <= b for a,b in windows):
            problems.append(f'{meal.name}用餐不在已知营业时段内')
    return list(dict.fromkeys(problems))
