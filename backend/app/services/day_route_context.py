"""Bounded, directed route facts for daily AI input. No reference-answer access."""
import asyncio
import math
import re

MAX_POINTS = 8
MAX_LOOKUPS = 24
LOOKUP_SECONDS = 20
CONCURRENCY = 3


def wants_route_facts(hint):
    text = hint or ''
    if re.search(r'(?:不要|不用|无需|不需要|不要求|不想)\s*(?:优化路线|减少交通|缩短交通|少绕路|减少路程|少走回头路)',text):
        return False
    return any(word in text for word in ['少绕路','减少交通','缩短交通','优化路线','减少路程','少走回头路'])


def keeps_attraction_order(hint):
    return bool(re.search(r'(?:不(?:要)?(?:改变|调整|改动|更改)|不改|保持(?:现有|当前|原)?)\s*(?:景点)?顺序|不要重排|景点顺序不变',hint or ''))


def known_minutes(value):
    match = re.fullmatch(r'\s*(?:(\d+(?:\.\d+)?)\s*小时)?\s*(?:(\d+(?:\.\d+)?)\s*分钟)?\s*',value or '')
    if not match or not any(match.groups()):return None
    minutes = float(match[1] or 0)*60+float(match[2] or 0)
    return round(minutes) if math.isfinite(minutes) and 0 <= minutes <= 2880 else None


def points(detail):
    candidates = []
    if detail.hotel:candidates.append(('hotel',detail.hotel))
    candidates += [('attraction',a) for a in detail.attractions if a.name not in detail.removed_attraction_names]
    candidates += [('meal',m) for m in detail.meals]
    names = [item.name for _,item in candidates]
    ambiguous = {n for n in names if names.count(n)>1}
    chosen = [(kind,item) for kind,item in candidates if item.name not in ambiguous][:MAX_POINTS]
    return [dict(kind=kind,name=item.name,location=item.location.model_dump() if item.location else None,
                 visit_minutes=getattr(item,'visit_duration',None),open_hours=getattr(item,'open_hours',None))
            for kind,item in chosen],len(candidates)-len(chosen)


def edge_fact(segment, a, b, source):
    if isinstance(segment,dict):
        from ..models.schemas import RouteSegment
        segment = RouteSegment.model_validate(segment)
    minutes = known_minutes(segment.duration)
    if (segment.from_name != a or segment.to_name != b or segment.is_estimated or minutes is None):return None
    return dict(from_name=a,to_name=b,duration_minutes=minutes,mode=segment.mode,
                is_estimated=False,source=source)


async def build_route_context(detail, city, transportation, lookup, *, enrich=False,
                              max_lookups=MAX_LOOKUPS, budget_seconds=LOOKUP_SECONDS):
    nodes,omitted = points(detail); by_name = {n['name']:n for n in nodes}
    pairs = [(a['name'],b['name']) for a in nodes for b in nodes if a['name']!=b['name']]
    facts = {}; unknown = {}; attempts = 0
    for segment in detail.route_segments:
        pair = (segment.from_name,segment.to_name)
        if pair not in pairs:continue
        fact = edge_fact(segment,*pair,'saved_not_requeried')
        if fact:facts[pair] = fact
    missing = [pair for pair in pairs if pair not in facts]
    selected = [pair for pair in missing if all(by_name[n]['location'] for n in pair)][:max(0,min(max_lookups,MAX_LOOKUPS))] if enrich else []
    for pair in missing:
        unknown[pair] = ('coordinates_unknown' if not all(by_name[n]['location'] for n in pair)
                         else 'not_queried_within_bound' if enrich else 'not_queried')
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async def acquire(pair):
        nonlocal attempts
        async with semaphore:
            attempts += 1
            probe = detail.model_copy(deep=True)
            probe.timeline_order = [dict(kind=by_name[n]['kind'],ref_name=n) for n in pair]
            try:
                result = await lookup(probe,city,transportation)
                fact = edge_fact(result[0],*pair,'bounded_lookup') if len(result)==1 else None
                if fact:
                    facts[pair] = fact;unknown.pop(pair,None)
                else:unknown[pair] = 'no_verified_directed_edge'
            except Exception:
                # Input enrichment may be partial. Final route/save validation stays strict.
                unknown[pair] = 'lookup_unavailable'
    tasks = [asyncio.create_task(acquire(pair)) for pair in selected]
    if tasks:
        try:
            async with asyncio.timeout(min(max(0,budget_seconds),LOOKUP_SECONDS)):
                await asyncio.gather(*tasks)
        except TimeoutError:
            for pair in selected:
                if pair not in facts and unknown.get(pair)=='not_queried_within_bound':
                    unknown[pair] = 'not_observed_before_deadline'
        finally:
            for task in tasks:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    return dict(schema='day-route-input-v1',city=city,transportation=transportation,points=nodes,
        directed_edges=[facts[pair] for pair in pairs if pair in facts],
        unknown_edges=[dict(from_name=a,to_name=b,reason=unknown[(a,b)]) for a,b in pairs if (a,b) in unknown],
        coverage='complete_for_listed_points' if not unknown and not omitted else 'partial',
        omitted_point_count=omitted,lookup_count=attempts,max_lookups=MAX_LOOKUPS,
        lookup_seconds=LOOKUP_SECONDS,saved_timeline=detail.timeline_order,
        fixed_times=detail.time_constraints.model_dump(mode='json') if detail.time_constraints else None,
        rest_periods=[r.model_dump(mode='json') for r in detail.rest_periods],travel_window=detail.travel_window,
        limitations=['仅供当前日已存活动和餐厅比较；已存路段未重新核实。',
                     '有向边不可反用；未知时长不是0，也没有直线距离代替。',
                     '不保证全局最优；须按真实路线再核对营业、餐次、锁定与固定时间。'])
