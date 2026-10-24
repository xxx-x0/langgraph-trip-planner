"""Explicit, preview-only transport-first adjustment of the two boundary days.

No new attractions/restaurants or shortened visits. Changed routes are verified once
per bounded reduction pass. Only server-held proposals may be committed by CAS.
"""
import copy
import json
import time
import uuid
from fastapi import HTTPException
from . import multicity
from .journey_service import travel_window, apply_context, conflicts
from ..models.schemas import DayDetail, WeatherInfo
from ..agents.langgraph_agent.assemble.budget import compute_day_budget
from ..agents.langgraph_agent.assemble.narrative import refresh_day_description
from ..agents.langgraph_agent.assemble.route import compute_day_route
from ..agents.langgraph_agent.assemble.schedule import schedule_day, clock, clock_minutes, opening_windows
from ..agents.langgraph_agent.assemble.meals import meal_plan_violations
from .external_calls import operation_deadline

_proposals = {}


def remember(document, plan, snapshots, changes):
    now = time.monotonic()
    for key, value in list(_proposals.items()):
        if value['expires'] <= now:
            del _proposals[key]
    while len(_proposals) >= 32:
        del _proposals[next(iter(_proposals))]
    ident = uuid.uuid4().hex
    _proposals[ident] = dict(expires=now+900, basis=multicity.token(document),
        plan=plan.model_dump(mode='json'), snapshots=copy.deepcopy(snapshots), changes=changes)
    return ident


def resolve(ident, document, plan):
    value = _proposals.get(ident)
    if not value or value['expires'] <= time.monotonic() or value['basis'] != multicity.token(document) or value['plan'] != plan.model_dump(mode='json'):
        raise HTTPException(409, '交通调整预览已过期或安排已改变，请重新生成；本次未保存')
    return copy.deepcopy(value)


def violations(day, baseline):
    problems = conflicts(day) + meal_plan_violations(day, baseline)
    by_name = {x.name:x for x in [*day.attractions, *day.meals]}
    for item in day.timeline_schedule:
        place = by_name.get(item['ref_name'])
        if place:
            windows = opening_windows(place.open_hours)
            if windows and not any(lo <= item['start_minutes'] and item['end_minutes'] <= hi for lo,hi in windows):
                problems.append(place.name+'超出已知开放时间')
    return list(dict.fromkeys(problems))


async def propose(document, proposed):
    plan = proposed.model_copy(deep=True)
    old = type(plan).model_validate(document['plan'])
    # This operation is deliberately scoped to one adjacent leg, not arbitrary form edits.
    before = old.model_dump(mode='json'); after = plan.model_dump(mode='json')
    before.pop('transfers'); after.pop('transfers')
    if before != after:
        raise HTTPException(422, '请先保存其他修改，再按交通调整当天安排')
    changed = [(a,b,leg) for a,b,_,_,leg in multicity.edges(plan)
               if leg != next((l for x,y,_,_,l in multicity.edges(old) if (x,y)==(a,b)),None)]
    if len(changed) != 1 or changed[0][2] is None:
        raise HTTPException(422, '每次选择一段新班次，再生成两侧当天安排')
    a,b,leg = changed[0]
    targets = {a:leg.departure_time[:10], b:leg.arrival_time[:10]}
    snapshots = copy.deepcopy(document['snapshots'])
    changes = []
    async with operation_deadline(110):
        for stop in plan.stops:
            if stop.id not in targets: continue
            day_date = targets[stop.id]
            snapshot = snapshots.get(stop.id)
            if not snapshot: continue
            if snapshot['request']['start_date'] != stop.start_date.isoformat() or snapshot['request']['end_date'] != stop.end_date.isoformat():
                raise HTTPException(409, '城市日期已变化，请重新规划后再按交通调整')
            index = next((i for i,d in enumerate(snapshot['days_detail']) if d and d['date']==day_date),None)
            if index is None: continue
            original = DayDetail.model_validate(snapshot['days_detail'][index])
            req = multicity.city_request(plan,stop)
            window = travel_window(req,day_date)
            lo,hi = max(480,window['start_minutes']),min(1320,window['end_minutes'])
            prefix = f'{stop.city.name} {day_date}：'
            changes.append(prefix+f'含原接驳与办理缓冲，可安排 {clock(lo)}—{clock(hi)}')
            for rest in list(stop.rest_periods):
                if rest.date.isoformat()==day_date and (clock_minutes(rest.start_time)<lo or clock_minutes(rest.end_time)>hi):
                    stop.rest_periods.remove(rest)
                    changes.append(prefix+f'取消无法容纳的休息 {rest.start_time}—{rest.end_time}（{rest.label}）')
            req = multicity.city_request(plan,stop)
            day = original.model_copy(deep=True)
            day.day_start_time = clock(max(lo,clock_minutes(original.day_start_time)))
            apply_context(day,req)
            removed_meals = []
            for meal in list(day.meals):
                slot = meal.preferred_slot if meal.preferred_slot not in (None,'auto') else meal.type
                limits = {'breakfast':(420,630),'lunch':(690,870),'dinner':(1050,1290)}.get(slot)
                if limits and min(hi,limits[1]+60)-max(lo,limits[0])<60:
                    day.meals.remove(meal);removed_meals.append(meal.name)
            # At most four route batches; if it still cannot fit, return an honest failure.
            for attempt in range(4):
                names = {x.name for x in [*day.attractions,*day.meals]}
                day.timeline_order = [x for x in original.timeline_order if x.get('kind')=='hotel' or x.get('ref_name') in names] if names else []
                day.route_segments = await compute_day_route(day,req.city,req.transportation)
                for meal in day.meals:
                    saved_meal=next(m for m in original.meals if m.name==meal.name)
                    meal.type=saved_meal.type
                    meal.preferred_slot=saved_meal.preferred_slot
                reference = day.model_copy(deep=True)
                schedule_day(day)
                if any(r.is_estimated for r in day.route_segments) or any(
                    x['kind']=='travel' and x.get('detail')=='路线尚未获取，暂按20分钟估算'
                    for x in day.timeline_schedule
                ):
                    raise HTTPException(422, prefix+'有市内路线尚未核实，不能确认调整；原安排未改变')
                issues = violations(day,reference)
                if not issues: break
                # Remove a conflicting meal first; never change its original lunch/dinner slot.
                bad_names = {name for name in names if any(name in p for p in issues)}
                meal = next((m for m in reversed(day.meals) if m.name in bad_names),None)
                if meal:
                    day.meals.remove(meal);removed_meals.append(meal.name)
                else:
                    attraction = next((x for x in reversed(day.attractions) if x.name not in day.locked_attraction_names),None)
                    if not attraction or attempt==3:
                        raise HTTPException(422, prefix+'在保留锁定景点、游览时长和可用时段后仍放不下；请先解锁或调整班次。原安排未改变')
                    day.attractions.remove(attraction)
                    day.removed_attraction_names=list(dict.fromkeys([*day.removed_attraction_names,attraction.name]))
                    changes.append(prefix+'取消放不下的景点 '+attraction.name+'；可在每日编辑中明确恢复')
            else:
                raise HTTPException(422,prefix+'本次未找到可用安排，原安排未改变')
            if day.day_start_time != original.day_start_time:
                changes.append(prefix+f'市内开始时间 {original.day_start_time} → {day.day_start_time}')
            for name in removed_meals:
                changes.append(prefix+'取消本城无法容纳的用餐 '+name+'；请核对另一城或在途用餐')
            day.meal_adjustments = [prefix+'交通调整后取消本城用餐：'+n for n in removed_meals]
            # Same-city ordering and duration remain; deleted names never get resurrected.
            day.day_budget=compute_day_budget(day)
            weather=next((WeatherInfo.model_validate(w) for w in json.loads(snapshot.get('editor_data',{}).get('weather_info_json','[]')) if w['date']==day_date),None)
            refresh_day_description(day,weather)
            snapshot['days_detail'][index] = day.model_dump(mode='json')
            snapshot['request'] = req.model_dump(mode='json')
            snapshot['basis'] = multicity.stop_basis(plan,stop)
    summary = multicity.projection(plan,snapshots)
    if summary['conflicts']:
        raise HTTPException(422,'调整后仍有冲突，原安排未改变：'+'；'.join(summary['conflicts']))
    return plan,snapshots,changes,summary
