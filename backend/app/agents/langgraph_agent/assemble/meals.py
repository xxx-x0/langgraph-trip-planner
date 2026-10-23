"""Retain saved meal positions when attractions are edited."""
from copy import deepcopy
from ....models.schemas import DayDetail


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
