"""Bounded comparison of saved activities using known directed edges only."""
from collections import Counter
import hashlib
from itertools import combinations_with_replacement, permutations
import json
import time

from ..models.schemas import RouteSegment
from .day_route_context import known_minutes, MAX_POINTS
from .place_hours import place_hours_report
from .journey_service import conflicts
from ..agents.langgraph_agent.assemble.meals import saved_meals, meal_plan_violations
from ..agents.langgraph_agent.assemble.schedule import schedule_day

MAX_CANDIDATES=256
SEARCH_SECONDS=.5


def sequence(day):
    return [x['ref_name'] for x in day.timeline_order if x['kind'] in {'attraction','meal','hotel'}]


def route_total(day):
    expected=[(a,b) for a,b in zip(sequence(day),sequence(day)[1:]) if a!=b]
    if [(s.from_name,s.to_name) for s in day.route_segments]!=expected:return None
    durations=[known_minutes(s.duration) if not s.is_estimated else None for s in day.route_segments]
    return sum(durations) if all(n is not None for n in durations) else None


def result_basis(day):
    facts=dict(order=day.timeline_order,attractions=[(a.name,a.visit_duration,a.open_hours) for a in day.attractions],
        meals=[(m.name,m.type,m.preferred_slot,m.schedule_mode,m.open_hours) for m in day.meals],
        locked=day.locked_attraction_names,removed=getattr(day,'removed_attraction_names',[]),
        constraints=day.time_constraints.model_dump(mode='json') if day.time_constraints else None,
        rests=[r.model_dump(mode='json') for r in day.rest_periods],
        window={k:day.travel_window.get(k) for k in ['start_minutes','end_minutes','unavailable']},
        routes=[(s.from_name,s.to_name,s.duration,s.mode,s.is_estimated) for s in day.route_segments],
        times=[(x['kind'],x['ref_name'],x['start_minutes'],x['end_minutes']) for x in day.timeline_schedule])
    return hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def _protected(base,trial):
    attrs=lambda d:{a.name:a.model_dump(mode='json') for a in d.attractions}
    if attrs(base)!=attrs(trial) or len(trial.attractions)!=len(base.attractions):return False
    before=[a.name for a in base.attractions];after=[a.name for a in trial.attractions]
    if set(after)&set(base.removed_attraction_names) or trial.locked_attraction_names!=base.locked_attraction_names:return False
    if any(after.index(n)!=before.index(n) for n in base.locked_attraction_names if n in before):return False
    if base.removed_attraction_names!=trial.removed_attraction_names or base.rest_periods!=trial.rest_periods:return False
    if base.time_constraints!=trial.time_constraints or base.day_start_time!=trial.day_start_time:return False
    if base.hotel!=trial.hotel:return False
    def meals(d):
        return {m.name:{k:v for k,v in m.model_dump(mode='json').items() if k not in {'type','schedule_mode'}} for m in d.meals}
    if meals(base)!=meals(trial) or len(trial.meals)!=len(base.meals):return False
    anchors={m['name']:m['insert_after'] for m in saved_meals(trial)}
    return all(anchors.get(m['name'])==m['insert_after'] for m in saved_meals(base) if m['schedule_mode']=='manual')


def valid_candidate(base,trial):
    return (_protected(base,trial) and not conflicts(trial) and not meal_plan_violations(trial,base)
            and not place_hours_report(trial)['violations'])


def _arrangements(base,keep_order):
    attrs=[a.name for a in base.attractions];by_name={a.name:a for a in base.attractions}
    meal_map={m.name:m for m in base.meals}
    meals=[meal_map[x['ref_name']] for x in base.timeline_order if x['kind']=='meal' and x['ref_name'] in meal_map]
    if len(meals)!=len(base.meals):return
    manual={m['name']:m['insert_after'] for m in saved_meals(base) if m['schedule_mode']=='manual'}
    for order in ([tuple(attrs)] if keep_order else permutations(attrs)):
        if any(order.index(n)!=attrs.index(n) for n in base.locked_attraction_names if n in attrs):continue
        for gaps in combinations_with_replacement(range(len(attrs)+1),len(meals)):
            if any(gaps[i]!=(0 if anchor=='hotel_start' else len(attrs) if anchor=='hotel_end' else order.index(anchor)+1)
                   for i,m in enumerate(meals) if (anchor:=manual.get(m.name))):continue
            trial=base.model_copy(deep=True);trial.attractions=[by_name[n].model_copy(deep=True) for n in order]
            timeline=[dict(kind='hotel',ref_name=base.hotel.name,phase='start')] if base.hotel else []
            for gap in range(len(attrs)+1):
                timeline.extend(dict(kind='meal',ref_name=m.name) for i,m in enumerate(meals) if gaps[i]==gap)
                if gap<len(attrs):timeline.append(dict(kind='attraction',ref_name=order[gap]))
            if base.hotel:timeline.append(dict(kind='hotel',ref_name=base.hotel.name,phase='end'))
            trial.timeline_order=timeline;yield trial


def choose_route_plan(base,proposed,context,*,keep_order=False,max_candidates=MAX_CANDIDATES,budget_seconds=SEARCH_SECONDS):
    """Return a candidate, not a global optimum or a guarantee of current opening."""
    baseline=route_total(base)
    info=dict(version='bounded-directed-routes-v1',status='unchanged',baseline_minutes=baseline,
        examined=0,missing_edges=0,rejected=0,search_truncated=False,coverage=context.get('coverage','partial'))
    names=[a.name for a in base.attractions]+[m.name for m in base.meals]+([base.hotel.name] if base.hotel else [])
    if baseline is None or len(names)>MAX_POINTS or len(names)!=len(set(names)):
        info.update(status='not_comparable',reason='已存路线、地点范围或名称不足以安全比较');return base.model_copy(deep=True),info
    edges={(e['from_name'],e['to_name']):e for e in context.get('directed_edges',[]) if e.get('is_estimated') is False}
    best=base.model_copy(deep=True);best_total=baseline;seen=set();start=time.monotonic()
    def trials():
        yield proposed
        yield from _arrangements(base,keep_order)
    for trial in trials():
        if info['examined']>=min(max_candidates,MAX_CANDIDATES) or time.monotonic()-start>=min(budget_seconds,SEARCH_SECONDS):
            info['search_truncated']=True;break
        key=tuple(sequence(trial))
        if key in seen:continue
        info['examined']+=1
        # A model draft with changed facts must not mask a valid reconstruction of
        # the same order from saved facts later in the bounded search.
        if not _protected(base,trial):info['rejected']+=1;continue
        seen.add(key)
        if keep_order and [a.name for a in trial.attractions]!=[a.name for a in base.attractions]:
            info['rejected']+=1;continue
        pairs=[(a,b) for a,b in zip(key,key[1:]) if a!=b]
        if any(p not in edges for p in pairs):info['missing_edges']+=1;continue
        facts=[edges[p] for p in pairs]
        if any(type(e.get('duration_minutes')) is not int or e['duration_minutes']<0 for e in facts):
            info['missing_edges']+=1;continue
        trial.route_segments=[RouteSegment(from_name=a,to_name=b,duration=f"{edges[a,b]['duration_minutes']}分钟",
            mode=edges[a,b]['mode'],is_estimated=False) for a,b in pairs]
        schedule_day(trial,suggest=False)
        if not valid_candidate(base,trial):info['rejected']+=1;continue
        total=route_total(trial)
        if total is not None and total<best_total:best,best_total=trial,total
    info.update(compared_minutes=best_total,status='candidate' if best_total<baseline else 'unchanged')
    return best,info


def complete_comparison(detail,base,info):
    """Only the final routed and validated arrangement can claim a reduction."""
    actual=route_total(detail);baseline=info['baseline_minutes']
    changed=sequence(detail)!=sequence(base)
    improved=(info['status']=='candidate' and changed and actual is not None and baseline is not None
              and actual<baseline and valid_candidate(base,detail))
    keep_routed=(baseline is None and actual is not None and valid_candidate(base,detail))
    if not improved and not keep_routed:detail=base.model_copy(deep=True);schedule_day(detail,suggest=False)
    note=('已按已知路线比较调整活动与正餐位置，保留景点、时长、锁定和手动用餐。' if improved else
          '已核对当前安排的路线；缺少可比较的已存路线，尚不能确认交通是否减少。' if keep_routed else
          '本次未找到可核实的更少交通方案，已保留原安排。')
    detail.meal_adjustments=list(dict.fromkeys([*detail.meal_adjustments,note]))
    final=route_total(detail)
    report=dict(info,status='improved' if improved else 'not_comparable' if info['status']=='not_comparable' or actual is None or baseline is None or final is None else 'unchanged',
        traffic_minutes=final,delta_minutes=baseline-final if improved else 0,
        end_minutes=max((x['end_minutes'] for x in detail.timeline_schedule),default=None),
        wait_minutes=sum(x['duration'] for x in detail.timeline_schedule if x['kind']=='wait'),
        free_minutes=sum(x['duration'] for x in detail.timeline_schedule if x['kind']=='free_time'),
        constraint_status='partial' if place_hours_report(detail)['unknown'] else 'known_constraints_checked',
        limitations=['只比较有界候选与已知有向路线，不保证全局最优；已存路段未重新核实。',
                     '交通变化与当天结束时间分别列示，开放日期及预约仍需确认。'])
    report['result_basis_sha256']=result_basis(detail);detail.route_comparison=report
    return detail
