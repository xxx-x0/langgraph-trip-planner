"""Reserve fixed rest periods without shortening visits or deleting meals."""
from ..agents.langgraph_agent.assemble.schedule import clock, clock_minutes, opening_windows


def period_minutes(period):
    return clock_minutes(period.start_time), clock_minutes(period.end_time)


def reserve_rest(detail):
    # Waiting is elastic; activities and their saved relative order are not.
    activities=[dict(x) for x in detail.timeline_schedule if x['kind'] not in {'wait','free_time','rest'}]
    rests=iter(sorted(detail.rest_periods,key=lambda r:r.start_time))
    pending=next(rests,None)
    cursor=clock_minutes(detail.day_start_time)
    result=[]

    def gap(until):
        nonlocal cursor
        if until>cursor:
            result.append(dict(kind='free_time',ref_name='这段时间尚未安排',start_time=clock(cursor),end_time=clock(until),start_minutes=cursor,end_minutes=until,duration=until-cursor,detail='留在当前区域自行安排；离开后需重新核对路线。'))
            cursor=until

    def rest():
        nonlocal cursor,pending
        lo,hi=period_minutes(pending)
        gap(lo)
        result.append(dict(kind='rest',rest_id=pending.id,ref_name=pending.label,start_time=clock(lo),end_time=clock(hi),start_minutes=lo,end_minutes=hi,duration=hi-lo,detail='在当前区域自行休息，地点与设施待确认；如需回酒店，请调整路线。'))
        cursor=max(cursor,hi)
        pending=next(rests,None)

    for item in activities:
        start=max(cursor,item['start_minutes'])
        while pending and (period_minutes(pending)[0]<start+item['duration'] or period_minutes(pending)[1]<=start):
            rest()
            start=max(cursor,item['start_minutes'])
        gap(start)
        item.update(start_minutes=start,end_minutes=start+item['duration'],start_time=clock(start),end_time=clock(start+item['duration']))
        result.append(item)
        cursor=item['end_minutes']
    while pending: rest()
    detail.timeline_schedule=result


def rest_conflicts(detail):
    if not detail.rest_periods: return []
    problems=[]
    schedule=detail.timeline_schedule
    for r in detail.rest_periods:
        lo,hi=period_minutes(r)
        if lo<clock_minutes(detail.day_start_time): problems.append(r.label+'早于每日开始时间，请调整开始时间或休息时段')
        matches=[x for x in schedule if x.get('kind')=='rest' and x.get('rest_id')==r.id and x.get('start_minutes')==lo and x.get('end_minutes')==hi]
        if len(matches)!=1: problems.append(r.label+' '+r.start_time+'—'+r.end_time+'尚未落实到时间轴')
        for x in schedule:
            if x['kind'] in {'attraction','meal','travel','hotel'} and x['start_minutes']<hi and x['end_minutes']>lo:
                problems.append(r.label+'与'+x['ref_name']+'重叠')
    meals={m.name:m for m in detail.meals}
    attractions={a.name:a for a in detail.attractions}
    for x in schedule:
        lo,hi=x['start_minutes'],x['end_minutes']
        if hi>1440: problems.append(x['ref_name']+'被顺延到次日，请减少当天安排')
        if x['kind']=='meal' and x['ref_name'] in meals:
            meal=meals[x['ref_name']]
            slot=meal.preferred_slot or meal.type
            bounds={'breakfast':(360,630),'lunch':(660,870),'dinner':(1020 if detail.coordination_policy else 1050,1320)}.get(slot)
            if bounds and not bounds[0]<=lo<=bounds[1]: problems.append(meal.name+'休息后不在原正餐时段，请调整休息或用餐')
            hours=opening_windows(meal.open_hours)
        elif x['kind']=='attraction' and x['ref_name'] in attractions:
            hours=opening_windows(attractions[x['ref_name']].open_hours)
        else: continue
        if hours and not any(a<=lo and hi<=b for a,b in hours): problems.append(x['ref_name']+'不在已知开放时间内')
    return list(dict.fromkeys(problems))
