"""Bounded, explicit transport-first preview. Proposals are server held and CAS saved."""
import copy
import hashlib
import json
import time
import uuid

from fastapi import HTTPException
from ..models.schemas import Attraction, Location, Budget
from .journey_service import apply_context, travel_window
from .journey_planning import capacity, pending_item
from .transport_adjustment import violations as transport_violations
from .place_hours import place_hours_report
from .external_calls import operation_deadline
from ..agents.langgraph_agent.assemble.route import compute_day_route
from ..agents.langgraph_agent.assemble.schedule import schedule_day, clock, clock_minutes, slot_label
from ..agents.langgraph_agent.assemble.narrative import refresh_day_description
from ..agents.langgraph_agent.assemble.budget import compute_day_budget, combine_budgets
from .meal_recovery import recover_slot, missing_slots, record_recovery

_proposals={}
FIELDS=('request_json','days_detail_json','macro_plan_json','clusters_data_json','hotels_by_day_json',
        'dining_pool_json','weather_info_json','selected_attractions_json','status')


def violations(day, baseline):
    # Use the same dated hours/admission checks as daily save and finalize.
    problems=transport_violations(day, baseline) + place_hours_report(day)['violations']
    if day.coordination_policy:
        from .trip_coordination import pace_problems
        problems+=pace_problems(day,None,[])
    return list(dict.fromkeys(problems))


def snapshot(record):
    return {key:getattr(record,key) for key in FIELDS}


def basis(record):
    return hashlib.sha256(json.dumps(snapshot(record),sort_keys=True).encode()).hexdigest()


def remember(record, args, value):
    now=time.monotonic()
    for key in list(_proposals):
        if _proposals[key]['expires']<=now: del _proposals[key]
    while len(_proposals)>=32: del _proposals[next(iter(_proposals))]
    ident=uuid.uuid4().hex
    token=hashlib.sha256((basis(record)+ident+json.dumps(args,sort_keys=True)).encode()).hexdigest()
    _proposals[ident]=dict(expires=now+900,basis=basis(record),expected=snapshot(record),args=copy.deepcopy(args),
                         value=copy.deepcopy(value),token=token)
    return ident,token


def resolve(record, args, ident, token):
    proposal=_proposals.get(ident)
    if not proposal or proposal['expires']<=time.monotonic() or proposal['basis']!=basis(record) or proposal['args']!=args or proposal['token']!=token:
        raise HTTPException(409,'交通调整预览已过期或草稿、输入已改变，请重新预览；本次未保存')
    return copy.deepcopy(proposal)


def as_cluster(attraction):
    value=attraction.model_dump(mode='json')
    loc=value.pop('location',None) or {}
    value.update(longitude=loc.get('longitude'),latitude=loc.get('latitude'),visit_minutes=attraction.visit_duration)
    return value


def as_attraction(cluster):
    fields={k:v for k,v in cluster.items() if k in Attraction.model_fields}
    fields['visit_duration']=cluster.get('visit_minutes') or cluster.get('visit_duration') or 120
    fields['address']=fields.get('address') or ''
    fields['description']=fields.get('description') or ''
    fields['category']=fields.get('category') or '景点'
    fields['poi_id']=fields.get('poi_id') or ''
    if cluster.get('longitude') is not None and cluster.get('latitude') is not None:
        fields['location']=Location(longitude=cluster['longitude'],latitude=cluster['latitude'])
    from ..agents.langgraph_agent.assemble.budget import parse_ticket_price
    fields['ticket_price']=parse_ticket_price(cluster.get('ticket_price'))
    return Attraction.model_validate(fields)


async def propose(record, payload, request, *, placements=None, discard_ids=None, assemble_pending=False, refill_meals=False):
    started = time.monotonic()
    placements,discard_ids=placements or [],discard_ids or []
    raw=json.loads(record.request_json)
    pending=copy.deepcopy(raw.get('_transport_unassigned',[]))
    discarded=copy.deepcopy(raw.get('_transport_discarded',[]))
    clusters=copy.deepcopy(json.loads(record.clusters_data_json))
    while len(clusters)<request.travel_days: clusters.append([])
    details=[d.model_copy(deep=True) if d else None for d in payload.days_detail]
    macro=payload.macro_plan.model_copy(deep=True)
    changes=[]
    dining_pool = copy.deepcopy(json.loads(record.dining_pool_json or '[]'))
    while len(dining_pool) < request.travel_days: dining_pool.append({})
    displaced_meals = {}
    meal_recovery = []
    meals_only = refill_meals and request.journey == payload.request.journey and not (placements or discard_ids or assemble_pending)
    if set(discard_ids)-{p['id'] for p in pending}:
        raise HTTPException(409,'待安排景点已变化，请重新加载')
    for item in list(pending):
        if item['id'] in discard_ids:
            pending.remove(item);discarded.append(item);changes.append('明确不再安排 '+item['name']+'；不会自动重新加入')
    if len(placements)>1 or any(p['id'] not in {a['id'] for a in pending} or not 0<=p['day_index']<request.travel_days for p in placements):
        raise HTTPException(422,'每次选择一个仍在待安排列表中的景点及有效日期')
    only_catalog=bool(discard_ids) and not placements and request.journey==payload.request.journey
    routes=0

    async def rebuild(day):
        nonlocal routes
        pairs=list(zip(day.timeline_order,day.timeline_order[1:]))
        if any(a.get('ref_name')!=b.get('ref_name') for a,b in pairs):
            if routes>=12: raise HTTPException(422,'本次有界路线核对已达上限，请先减少当天活动；原安排未改变')
            routes+=1
            day.route_segments=await compute_day_route(day,request.city,request.transportation)
        else: day.route_segments=[]
        schedule_day(day)
        if any(r.is_estimated for r in day.route_segments) or any(x['kind']=='travel' and '路线尚未获取' in x.get('detail','') for x in day.timeline_schedule):
            raise HTTPException(422,'有市内路线尚未核实，不能确认交通调整；原安排未改变')

    def protected(day):
        return set(day.locked_attraction_names) | {a.ref_name for a in day.time_constraints.appointments if a.kind=='attraction'} if day.time_constraints else set(day.locked_attraction_names)

    async with operation_deadline(110):
        if not only_catalog and not placements and not meals_only:
            kept=[]
            for rest in request.rest_periods:
                w=travel_window(request,rest.date.isoformat())
                if clock_minutes(rest.start_time)<w.get('start_minutes',0) or clock_minutes(rest.end_time)>w.get('end_minutes',1440) or w.get('unavailable'):
                    changes.append(f'{rest.date}：取消无法容纳的休息 {rest.start_time}—{rest.end_time}（{rest.label}）')
                else: kept.append(rest)
            request.rest_periods=kept
            for i,day in enumerate(details):
                if day is None and assemble_pending:
                    from ..agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
                    ctx=payload.days[i].model_copy(deep=True)
                    apply_context(ctx,request)
                    ctx.day_start_time=clock(max(clock_minutes(request.default_day_start_time),
                                                ctx.travel_window.get('start_minutes',0))) if not ctx.travel_window.get('unavailable') else request.default_day_start_time
                    day=rule_assemble_day_timeline(ctx)
                    details[i]=day
                    await rebuild(day)
                    changes.append(f'{day.date}：按交通窗口核对原选景点、用餐和实际路线')
                if day is None:
                    # Skeletons need the same catalog protection before their first assembly.
                    available=capacity(request,payload.days[i].date)
                    group=clusters[i]
                    while group and sum(a.get('visit_minutes') or a.get('visit_duration') or 120 for a in group)+20*len(group)+120>available:
                        attraction=group.pop()
                        item=pending_item(attraction,payload.days[i].date,'交通占用后移出原日骨架，尚未核对路线及营业时间')
                        if item['id'] not in {x['id'] for x in pending}: pending.append(item)
                        changes.append(f"{payload.days[i].date}：{attraction['name']}移出原日骨架，原游览时长保留")
                    continue
                apply_context(day,request)
                day.day_start_time=day.day_start_time or '08:00'
                # New journey context also changes hotel handling time. Normalize
                # with the saved routes now so finalize cannot silently change it later.
                schedule_day(day)
                removed=[]
                if not violations(day,day) and (payload.days_detail[i] is None or day.rest_periods==payload.days_detail[i].rest_periods):
                    continue  # Keep successful saved routes/times when no activity changes.
                if day.travel_window.get('unavailable') or capacity(request,day.date)==0:
                    if protected(day) or (day.time_constraints and day.time_constraints.appointments):
                        raise HTTPException(422,f'{day.date}锁定景点或固定预约无法放入交通日，请先解锁或调整班次；原安排未改变')
                    if any(m.schedule_mode=='manual' for m in day.meals):
                        raise HTTPException(422,f'{day.date}手动用餐无法放入交通日，请先调整该用餐；原安排未改变')
                    removed=list(day.attractions);day.attractions=[]
                    for meal in day.meals:
                        slot = meal.preferred_slot or meal.type
                        if slot in ('lunch','dinner'): displaced_meals[(i,slot)] = meal.name
                        else: changes.append(f'{day.date}：移除本城用餐 {meal.name}；本城已无可用时段')
                    day.meals=[];day.hotel=None;day.timeline_order=[]
                    await rebuild(day)
                else:
                    start=max(clock_minutes(day.day_start_time),day.travel_window.get('start_minutes',0))
                    day.day_start_time=clock(start)
                    # Four reduction passes, with a verified route for each proposed arrangement.
                    for attempt in range(5):
                        await rebuild(day)
                        problems=violations(day,day)
                        if not problems: break
                        names={x.name for x in [*day.attractions,*day.meals] if any(x.name in p for p in problems)}
                        # A missing meal slot is reported without a restaurant
                        # name. Match that slot as well, otherwise an impossible
                        # lunch can make every unrelated attraction get removed.
                        attraction=next((a for a in reversed(day.attractions) if a.name in names and a.name not in protected(day)),None)
                        meal=next((m for m in reversed(day.meals) if (m.name in names or f'{slot_label(m.preferred_slot or m.type)}未能保留' in problems) and m.schedule_mode!='manual' and not(day.time_constraints and any(a.ref_name==m.name for a in day.time_constraints.appointments))),None)
                        if meal and attempt<4:
                            day.meals.remove(meal)
                            slot = meal.preferred_slot or meal.type
                            if slot in ('lunch','dinner'): displaced_meals[(i,slot)] = meal.name
                            else: changes.append(f'{day.date}：移除本城用餐 {meal.name}；原餐厅无法容纳')
                        elif attraction and attempt<4:
                            removed.append(attraction);day.attractions.remove(attraction)
                        else:
                            attraction=next((a for a in reversed(day.attractions) if a.name not in protected(day)),None)
                            if not attraction or attempt==4:
                                raise HTTPException(422,f'{day.date}保留锁定、固定时间或手动用餐后仍放不下，请先调整；原安排未改变')
                            removed.append(attraction);day.attractions.remove(attraction)
                        live={x.name for x in [*day.attractions,*day.meals]}
                        day.timeline_order=[x for x in day.timeline_order if x.get('kind')=='hotel' or x.get('ref_name') in live]
                for attraction in removed:
                    item=pending_item(as_cluster(attraction),day.date,'交通占用后移出原日，尚未安排')
                    if item['id'] not in {x['id'] for x in pending}: pending.append(item)
                    clusters[i]=[a for a in clusters[i] if a['name']!=attraction.name]
                    changes.append(f'{day.date}：{attraction.name}移出原日，原游览时长保留')

        if not only_catalog and not meals_only:
            for item in list(pending):
                if placements and item['id']!=placements[0]['id']: continue
                attraction=as_attraction(item['cluster'])
                targets=[placements[0]['day_index']] if placements else sorted(range(request.travel_days),key=lambda i:(payload.days[i].date==item.get('from_date'),i))
                placed=False
                for i in targets:
                    if capacity(request,payload.days[i].date)<(attraction.visit_duration or 120): continue
                    target=details[i]
                    deleted=set(target.removed_attraction_names if target else [])
                    if attraction.name in deleted or any(a['name']==attraction.name for a in clusters[i]): continue
                    if target is None:
                        visits=sum(a.get('visit_minutes') or a.get('visit_duration') or 120 for a in clusters[i])
                        if visits+(attraction.visit_duration or 120)+20*(len(clusters[i])+1)+120>capacity(request,payload.days[i].date): continue
                        changes.append(f'{attraction.name}移至{payload.days[i].date}骨架；当天尚未装配，路线和餐饮仍待核对')
                    else:
                        trial=target.model_copy(deep=True);apply_context(trial,request)
                        trial.day_start_time=clock(max(clock_minutes(trial.day_start_time),trial.travel_window.get('start_minutes',0)))
                        trial.attractions.append(attraction)
                        index=next((j for j,x in enumerate(trial.timeline_order) if x.get('kind')=='hotel' and x.get('phase')!='start'),len(trial.timeline_order))
                        trial.timeline_order.insert(index,dict(kind='attraction',ref_name=attraction.name))
                        if routes>=12: continue
                        await rebuild(trial)
                        if violations(trial,target): continue
                        details[i]=trial
                        changes.append(f'{attraction.name}移至{trial.date}，保留原游览时长；已核对当前路线和已知营业时段')
                    clusters[i].append(copy.deepcopy(item['cluster']));pending.remove(item);placed=True;break
                if placements and not placed:
                    raise HTTPException(422,'所选日期无法容纳该景点，请换一天或调整该天安排；原安排未改变')
                if not placed:
                    item['reason']='本次有界调整未找到可容纳日期，保留待安排；未删除，也不代表不存在其他排法'
                    changes.append(item['name']+'保留待安排，不会自动缩短游览或计入已安排内容')

        # Only recover meals displaced by this operation. The separate opt-in is
        # needed for older gaps, so normal reordering never restores deleted meals.
        if refill_meals:
            for i, day in enumerate(details):
                for slot in missing_slots(day): displaced_meals.setdefault((i,slot), None)
        for (i, slot), old_name in displaced_meals.items():
            day = details[i]
            if not day or any(m.type == slot for m in day.meals): continue
            remaining = 108 - (time.monotonic() - started)
            result = dict(date=day.date, slot=slot, status='unavailable', old_restaurant=old_name)
            if remaining < 3:
                result['reason'] = '本次路线核对已用完可用时间，补餐尚未完成；可在保存后重试推荐。'
            else:
                try:
                    async with operation_deadline(min(40, remaining)):
                        day, pool, result = await recover_slot(day,slot,request,dining_pool[i] or {},
                            rebuild=rebuild,validate=violations,old_restaurant=old_name)
                    details[i] = day
                    dining_pool[i] = pool
                except TimeoutError:
                    result['reason'] = '本次查店或路线核对超时，补餐尚未完成；可重试推荐。'
            record_recovery(day, result)
            meal_recovery.append(result)
            changes.append(f'{day.date}：'+day.meal_adjustments[-1])

    budgets=[];impacts=[]
    from .schedule_constraints import schedule_changes
    for i,ctx in enumerate(payload.days):
        if i<len(macro.days): macro.days[i].attraction_names=[a['name'] for a in clusters[i]]
        day=details[i]
        if day:
            apply_context(day,request);day.day_budget=compute_day_budget(day)
            refresh_day_description(day,ctx.weather);budgets.append(day.day_budget)
            problems=violations(day,day)
            if problems: raise HTTPException(422,f'{day.date}调整后仍有冲突：'+'；'.join(problems))
            old=payload.days_detail[i]
            hotels={x['ref_name']:x for x in old.timeline_schedule if x['kind']=='hotel'} if old else {}
            for row in day.timeline_schedule:
                previous=hotels.get(row['ref_name']) if row['kind']=='hotel' else None
                if previous and (previous['start_minutes'],previous['end_minutes'])!=(row['start_minutes'],row['end_minutes']):
                    changes.append(f"{day.date}：{row['ref_name']}酒店办理／位置参考 {previous['start_time']}—{previous['end_time']} → {row['start_time']}—{row['end_time']}（按本次交通缓冲计时）")
        else:
            amount=travel_window(request,ctx.date).get('intercity_cost',0)
            budgets.append(Budget(total=amount,total_transportation=amount,total_intercity=amount,
                is_complete=False,unknown_cost_items=[ctx.date+'市内安排尚未装配']))
        impacts.append(dict(date=ctx.date,window=travel_window(request,ctx.date),conflicts=[],changes=[],
            activities=[a.name for a in day.attractions] if day else [a['name'] for a in clusters[i]]))
    for shift in schedule_changes(payload.days_detail,details,request.city):
        changes.append(f"{shift['date']}：{shift['ref_name']} {shift['before']} → {shift['after']}")
    budget=combine_budgets(budgets,request.budget)
    if pending or any(d is None for d in details):
        budget.is_complete=False
        if budget.is_within_budget is not False: budget.is_within_budget=None
        budget.unknown_cost_items.append('待安排景点或尚未装配日期的费用未计入')
    return dict(request=request,details=details,clusters=clusters,macro=macro,unassigned=pending,discarded=discarded,
                changes=changes,impacts=impacts,budget=budget,dining_pool=dining_pool,meal_recovery=meal_recovery)
