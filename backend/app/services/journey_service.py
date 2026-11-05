"""Time/cost projections of explicit travel inputs, independent of provider access."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from ..models.journey import local_instant


def stay_dates(request):
    j = request.journey
    start, end = request.start_date, request.end_date
    if j:
        tz = ZoneInfo(j.destination_timezone)
        if j.outbound: start = local_instant(j.outbound.arrival_time,j.outbound.arrival_timezone).astimezone(tz).date().isoformat()
        if j.inbound: end = local_instant(j.inbound.departure_time,j.inbound.departure_timezone).astimezone(tz).date().isoformat()
    return start,end


def travel_window(request, day):
    j = request.journey
    if not j:
        return {'provisional':True, 'notes':['抵离交通尚未填写；首末日可用时间暂定']} if day in {request.start_date,request.end_date} else {}
    tz = ZoneInfo(j.destination_timezone)
    midnight = datetime.combine(date.fromisoformat(day),time(),tzinfo=tz)
    lower, upper = 0,1440
    notes, legs = [], []
    cost, unknown = 0, []
    for key, label, cost_date in [('outbound','去程',request.start_date),('inbound','返程',request.end_date)]:
        leg = getattr(j,key)
        if not leg:
            notes.append(f'{label}未填写，可用时间暂定')
            planning = j.planning
            if planning:
                policy = planning.arrival_policy if key == 'outbound' else planning.departure_policy
                boundary = (planning.ready_at if key == 'outbound' else planning.leave_by) if policy == 'time_window' else None
                if policy == 'travel_day':
                    boundary = ((date.fromisoformat(request.start_date)+timedelta(days=1)).isoformat() if key == 'outbound' else request.end_date)+'T00:00'
                if boundary:
                    relative = round((local_instant(boundary,j.destination_timezone)-midnight).total_seconds()/60)
                    if key == 'outbound': lower=max(0,min(1440,relative))
                    else: upper=max(0,min(1440,relative))
                    if day == cost_date or boundary[:10] == day:
                        notes.append(f'{label}按本次交通时间预留：'+('目的地活动从'+boundary.replace('T',' ')+'后开始' if key=='outbound' else '目的地活动须在'+boundary.replace('T',' ')+'前结束')+'；不是实际班次，已含本次暂定接驳预留')
            if day == cost_date: unknown.append(f'{label}票价及接驳/行李等费用未知')
            continue
        dep=local_instant(leg.departure_time,leg.departure_timezone)
        arr=local_instant(leg.arrival_time,leg.arrival_timezone)
        buffer = leg.baggage_minutes+leg.transfer_after_minutes+leg.lodging_buffer_minutes if key=='outbound' else leg.transfer_before_minutes+leg.station_buffer_minutes+leg.lodging_buffer_minutes
        boundary=(arr.astimezone(timezone.utc)+timedelta(minutes=buffer) if key=='outbound' else dep.astimezone(timezone.utc)-timedelta(minutes=buffer)).astimezone(tz)
        relative=round((boundary-midnight).total_seconds()/60)
        if key=='outbound': lower=max(0,min(1440,relative))
        else: upper=max(0,min(1440,relative))
        door_start=dep.astimezone(timezone.utc)-timedelta(minutes=leg.transfer_before_minutes+leg.station_buffer_minutes+(leg.lodging_buffer_minutes if key=='inbound' else 0))
        door_end=arr.astimezone(timezone.utc)+timedelta(minutes=leg.baggage_minutes+leg.transfer_after_minutes+(leg.lodging_buffer_minutes if key=='outbound' else 0))
        if day==cost_date and (door_start.astimezone(tz).date().isoformat()<request.start_date or door_end.astimezone(tz).date().isoformat()>request.end_date):
            notes.append(f'{label}含缓冲预计覆盖{door_start.astimezone(tz).strftime("%m-%d %H:%M")}至{door_end.astimezone(tz).strftime("%m-%d %H:%M")}，超出所填旅行日期，请核对出行日期范围')
        if boundary.date().isoformat()==day or day==cost_date:
            state='已订时间约束' if leg.booking_status=='booked' else '暂定班次约束'
            notes.append(f'{label}{state}：{boundary.strftime("%m-%d %H:%M")}'+('后可开始市内安排' if key=='outbound' else '前须结束市内安排')+f'；含{buffer}分钟接驳、行李/候车及入住/退房缓冲（用户可编辑估计）')
            legs.append({'direction':key,'label':label,**leg.model_dump(mode='json'),
                         'door_departure':door_start.astimezone(ZoneInfo(leg.departure_timezone)).isoformat(timespec='minutes'),
                         'door_arrival':door_end.astimezone(ZoneInfo(leg.arrival_timezone)).isoformat(timespec='minutes'),
                         'duration_minutes':round((arr.astimezone(timezone.utc)-dep.astimezone(timezone.utc)).total_seconds()/60),
                         'door_to_door_minutes':round((arr.astimezone(timezone.utc)-dep.astimezone(timezone.utc)).total_seconds()/60)+leg.transfer_before_minutes+leg.station_buffer_minutes+leg.baggage_minutes+leg.transfer_after_minutes+leg.lodging_buffer_minutes})
        if day==cost_date:
            if leg.currency!='CNY': unknown.append(f'{label}{leg.currency}金额未换算计入人民币预算')
            else:
                if leg.ticket_total is not None: cost+=leg.ticket_total
                else: unknown.append(f'{label}票价未知')
                if leg.extras_total is not None: cost+=leg.extras_total
                else: unknown.append(f'{label}税费/行李/两端接驳等额外费用未知')
            if leg.extra_costs:
                labels={'taxes':'未含税费','baggage':'额外行李','transfers':'两端接驳','overnight':'途中额外住宿'}
                unknown.extend(f'{label}{labels[k]}费用未知' for k,v in leg.extra_costs.model_dump().items() if v is None)
            if leg.price_source!='paid' and leg.quote_expires_at and local_instant(leg.quote_expires_at,leg.departure_timezone)<=datetime.now(timezone.utc):
                unknown.append(f'{label}报价已过期，金额仅保留作参考，请重新核价')
            if leg.price_source!='paid': unknown.append(f'{label}为用户录入估算或报价，尚需核实实时价格及条件')
    stay_start, stay_end=stay_dates(request)
    usable=max(0,min(1320,upper)-max(480,lower))
    if usable == 0: notes.append('本日留给交通或抵离办理，未安排目的地游玩；在途用餐及住宿仍需核对')
    return dict(start_minutes=lower,end_minutes=max(lower,upper),unavailable=lower>=upper,
                day_role='travel' if not usable else 'partial' if usable<840 else 'full',usable_minutes=usable,
                provisional=not(j.outbound and j.inbound), notes=notes,legs=legs,
                intercity_cost=round(cost,2),unknown_cost_items=unknown,
                overnight_stay=stay_start<=day<stay_end)


def apply_context(ctx,request):
    ctx.travel_window=travel_window(request,ctx.date)
    if hasattr(ctx, 'coordination_policy') and hasattr(request, 'coordination_policy'):
        ctx.coordination_policy = dict(request.coordination_policy)
    if hasattr(request, "rest_periods"):
        ctx.rest_periods=[r.model_copy(deep=True) for r in request.rest_periods if r.date.isoformat()==ctx.date]
    if 'overnight_stay' in ctx.travel_window: ctx.overnight_stay=ctx.travel_window['overnight_stay']
    if ctx.hotel and ctx.hotel.quote:
        start,end=stay_dates(request)
        if ctx.hotel.quote.check_in!=start or ctx.hotel.quote.check_out!=end:
            ctx.hotel.quote=None
    return ctx


def conflicts(detail):
    from .rest_schedule import rest_conflicts
    window=detail.travel_window
    lo,hi=window.get('start_minutes',0),window.get('end_minutes',1440)
    from .schedule_constraints import time_conflicts
    return time_conflicts(detail) + rest_conflicts(detail) + [f"{x['ref_name']}（{x['start_time']}—{x['end_time']}）" for x in detail.timeline_schedule
            if x['kind'] in {'attraction','meal','hotel','travel','rest'} and (window.get('unavailable') or x['start_minutes']<lo or x['end_minutes']>hi)]
