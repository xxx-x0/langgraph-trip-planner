"""Atomic whole-trip snapshots; city editors are working copies, never live joins."""
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select, text
from ..database import async_session
from ..models.db_models import TripDraft
from ..models.multicity import MultiTrip
from ..models.schemas import TripRequest, DayDetail, DraftDayContext, WeatherInfo
from ..models.journey import Journey, local_instant
from .journey_service import travel_window
from .recommendations import intent_for
from .journey_comparison import synchronize_days
from ..agents.langgraph_agent.assemble.budget import compute_day_budget
from ..agents.langgraph_agent.assemble.narrative import refresh_day_description

KIND='multi_city_v1'


def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def token(value): return hashlib.sha256(dump(value).encode()).hexdigest()
def dates(start,end): return [date.fromordinal(n).isoformat() for n in range(start.toordinal(),end.toordinal()+1)]
def edges(plan):
    visits=[('origin',plan.origin)]+[(s.id,s.city) for s in plan.stops]+[('destination',plan.destination)]
    selected={(t.from_stop,t.to_stop):t.leg for t in plan.transfers}
    return [(a[0],b[0],a[1],b[1],selected.get((a[0],b[0]))) for a,b in zip(visits,visits[1:])]


def stop_basis(plan,stop):
    relevant=[t.model_dump(mode='json') for t in plan.transfers if stop.id in (t.from_stop,t.to_stop)]
    return token(dict(stop=stop.model_dump(mode='json'),transfers=relevant,companions=plan.companions.model_dump(),occupancy=plan.hotel_occupancy.model_dump() if plan.hotel_occupancy else None,pace=plan.pace,preferences=plan.preferences,transportation=plan.transportation,accommodation=plan.accommodation,dietary=plan.dietary_requirements,meal_budget=plan.meal_budget_per_person))


def city_request(plan,stop):
    index=plan.stops.index(stop);es=edges(plan)
    incoming,outgoing=es[index][4],es[index+1][4]
    # Include the physical travel dates so the existing single-city validator can
    # express an overnight incoming/outgoing leg. Only the stay dates own nights.
    legs=[leg for leg in (incoming,outgoing) if leg]
    start=min([stop.start_date]+[date.fromisoformat(leg.departure_time[:10]) for leg in legs])
    end=max([stop.end_date]+[date.fromisoformat(leg.arrival_time[:10]) for leg in legs])
    req=TripRequest(city=stop.city.name,start_date=start.isoformat(),end_date=end.isoformat(),travel_days=(end-start).days+1,
        transportation=plan.transportation,accommodation=plan.accommodation,preferences=plan.preferences,
        companions=plan.companions,hotel_occupancy=plan.hotel_occupancy,budget=None,rest_periods=stop.rest_periods,
        meal_budget_per_person=plan.meal_budget_per_person,dietary_requirements=plan.dietary_requirements,
        free_text_input={'slow':'希望慢慢逛，每隔两三天留出休息。','balanced':'移动当天少安排景点，留出用餐和休息。','active':'希望多体验，但移动和正餐时间要保留。'}[plan.pace],
        journey=Journey(origin_city=es[index][2].name,return_city=es[index+1][3].name,outbound=incoming,inbound=outgoing))
    return req


def transport_metrics(leg,label,lodging_sides=2):
    if not leg: return dict(known=0,minutes=None,missing=[label+'班次和费用待确认'],notes=[],night=False)
    req=SimpleNamespace(journey=Journey(origin_city='出发',return_city='返回',outbound=leg),start_date=leg.departure_time[:10],end_date=leg.arrival_time[:10])
    w=travel_window(req,req.start_date)
    dep=local_instant(leg.departure_time,leg.departure_timezone);arr=local_instant(leg.arrival_time,leg.arrival_timezone)
    # Both checkout and checkin are needed between cities, one at each endpoint.
    mins=int((arr-dep).total_seconds()/60)+leg.transfer_before_minutes+leg.station_buffer_minutes+leg.baggage_minutes+leg.transfer_after_minutes+lodging_sides*leg.lodging_buffer_minutes
    missing=[x.replace('去程',label) for x in w['unknown_cost_items'] if not x.startswith('返程')]
    return dict(known=w['intercity_cost'],minutes=mins,missing=missing,notes=[label+'接驳及办理时间为可编辑估计'],night=dep.date()!=arr.date() or dep.hour<7 or arr.hour>=22)


def projection(plan,snapshots=None):
    snapshots=snapshots or {};missing=[];problems=[];city_views=[];night_owners={};hotel_total=0;local_total=0;transport_total=0;all_minutes=0;complete_legs=True;moving=set();transfers=[]
    es=edges(plan)
    for a,b,frm,to,leg in es:
        label=frm.name+' → '+to.name;m=transport_metrics(leg,label,int(a!='origin')+int(b!='destination'));transport_total+=m['known'];missing+=m['missing']
        if m['minutes'] is None: complete_legs=False
        else: all_minutes+=m['minutes']
        transfers.append(dict(from_stop=a,to_stop=b,from_city=frm.name,to_city=to.name,**m))
        if leg:
            dep,arr=date.fromisoformat(leg.departure_time[:10]),date.fromisoformat(leg.arrival_time[:10])
            moving.update(dates(dep,arr))
            for n in dates(dep,arr)[:-1]: night_owners.setdefault(n,[]).append('在途：'+label)
            for sid,expected in [(a,dep),(b,arr)]:
                s=next((x for x in plan.stops if x.id==sid),None)
                if s and (s.end_date if sid==a else s.start_date)!=expected: problems.append(label+'班次日期与城市抵离日期不一致，请调整停留日期或班次')
    for i,s in enumerate(plan.stops):
        req=city_request(plan,s);snap=snapshots.get(s.id);details=[];stale=False;impacts=[]
        if snap:
            # Date/city/party changes cannot relabel old activities or old quotes.
            old=TripRequest.model_validate(snap['request'])
            stale=(old.city,old.start_date,old.end_date,old.companions,old.hotel_occupancy)!=(req.city,req.start_date,req.end_date,req.companions,req.hotel_occupancy)
            if stale: missing.append(s.city.name+'每日安排日期或人数已变，旧安排保留待重新规划，暂不计其费用')
            else:
                saved=[DayDetail.model_validate(x) if x else None for x in snap['days_detail']]
                weather={w['date']:WeatherInfo.model_validate(w) for w in json.loads(snap.get('editor_data',{}).get('weather_info_json','[]'))}
                ctx=[DraftDayContext(day_index=n,date=d,attraction_names=[],weather=weather.get(d)) for n,d in enumerate(dates(date.fromisoformat(req.start_date),date.fromisoformat(req.end_date)))]
                payload=SimpleNamespace(days=ctx,days_detail=saved)
                details,impacts,_=synchronize_days(payload,req)
                for detail in details:
                    if not detail: continue
                    # Lodging ownership is explicit, even when a transfer is unknown.
                    detail.overnight_stay=s.start_date.isoformat()<=detail.date<s.end_date.isoformat()
                    if s.lodgings:
                        detail.overnight_stay=False  # explicit stay replaces daily hotel cost
                        for h in s.lodgings:
                            if h.check_in.isoformat()<=detail.date<h.check_out.isoformat() and detail.hotel and detail.hotel.name!=h.name:
                                problems.append(s.city.name+' '+detail.date+'手动住宿与每日酒店不同，请重新核对接驳及每日路线')
                    detail.travel_window['intercity_cost']=0
                    detail.travel_window['unknown_cost_items']=[]
                    detail.trip_intent=intent_for(req)
                    from .hotel_quotes import hotel_cost_for_date
                    for item in detail.timeline_schedule:
                        if item.get('kind')=='hotel':
                            amount, unknown=hotel_cost_for_date(detail.hotel,detail.date) if detail.hotel and detail.overnight_stay else (0,[])
                            item['cost']=(amount if amount or not unknown else None) if detail.overnight_stay else None
                    detail.day_budget=compute_day_budget(detail)
                    refresh_day_description(detail, weather.get(detail.date))
                    local_total+=detail.day_budget.total-detail.day_budget.total_hotels
                    hotel_total+=detail.day_budget.total_hotels
                    missing.extend(s.city.name+' '+x for x in detail.day_budget.unknown_cost_items)
                for impact in impacts: problems.extend(s.city.name+' '+x for x in impact['conflicts'])
        if not snap or stale or any(d is None for d in details): missing.append(s.city.name+'每日活动、用餐和市内费用尚未全部安排')
        nightly={}
        for h in s.lodgings:
            ns=(h.check_out-h.check_in).days;known=0
            if h.amount is None or h.currency!='CNY': missing.append(s.city.name+' '+h.name+'住宿金额未知或币种未换算')
            else: known=h.amount*(h.rooms*ns if h.basis=='room_night' else 1)
            hotel_total+=known
            if h.taxes_included is not True: missing.append(s.city.name+' '+h.name+'住宿税费待确认')
            if h.source!='paid': missing.append(s.city.name+' '+h.name+'住宿价格需重新核价')
            for n in dates(h.check_in,h.check_out)[:-1]: nightly[n]=h.name
        for n in dates(s.start_date,s.end_date)[:-1]:
            night_owners.setdefault(n,[]).append(s.city.name)
            if n not in nightly and (bool(s.lodgings) or not details or stale or not any(d and d.date==n and d.hotel and d.hotel.quote for d in details)):
                missing.append(n+' '+s.city.name+'住宿尚未确认')
        windows=[]
        for d in dates(s.start_date,s.end_date):
            w=travel_window(req,d)
            available=max(0,min(1320,w['end_minutes'])-max(480,w['start_minutes']))
            windows.append(dict(date=d,start_minutes=w['start_minutes'],end_minutes=w['end_minutes'],available_minutes=available,provisional=w['provisional'],moving=d in moving,rest=(date.fromisoformat(d)-plan.start_date).days%3==2,notes=w['notes']))
            from .rest_schedule import period_minutes
            rests=[r for r in s.rest_periods if r.date.isoformat()==d]
            windows[-1]['rest_periods']=[r.model_dump(mode='json') for r in rests]
            windows[-1]['rest_minutes']=sum(period_minutes(r)[1]-period_minutes(r)[0] for r in rests)
            windows[-1]['available_minutes']=max(0,available-sum(max(0,min(period_minutes(r)[1],min(1320,w['end_minutes']))-max(period_minutes(r)[0],max(480,w['start_minutes']))) for r in rests))
            for r in rests:
                lo,hi=period_minutes(r)
                if lo<w['start_minutes'] or hi>w['end_minutes']: problems.append(s.city.name+' '+d+'休息时段与抵离交通冲突')
                detail=next((x for x in details if x and x.date==d),None)
                if not detail or not any(x.get('rest_id')==r.id and x['start_time']==r.start_time and x['end_time']==r.end_time for x in detail.timeline_schedule):
                    missing.append(s.city.name+' '+d+' '+r.start_time+'—'+r.end_time+'休息尚未落实到每日安排')
            if w['unavailable']: problems.append(s.city.name+' '+d+'抵离含缓冲后没有可用时间')
        city_views.append(dict(id=s.id,city=s.city.name,nights=(s.end_date-s.start_date).days,windows=windows,stale=stale,days=[d.model_dump(mode='json') if d else None for d in details],impacts=impacts,source_draft=snap.get('draft_id') if snap else None))
    nights=[]
    for n in dates(plan.start_date,plan.end_date)[:-1]:
        owners=night_owners.get(n,[])
        if len(owners)>1: problems.append(n+'夜晚归属冲突：'+'、'.join(owners))
        if not owners: missing.append(n+'夜晚尚未归属城市或已填写的跨日交通')
        nights.append(dict(date=n,owners=owners))
    # Adjacent door intervals must not overlap, even if station times look valid.
    known=[e[4] for e in es if e[4]]
    for a,b in zip(known,known[1:]):
        arrival=local_instant(a.arrival_time,a.arrival_timezone)+timedelta(minutes=a.baggage_minutes+a.transfer_after_minutes+a.lodging_buffer_minutes)
        departure=local_instant(b.departure_time,b.departure_timezone)-timedelta(minutes=b.transfer_before_minutes+b.station_buffer_minutes+b.lodging_buffer_minutes)
        if arrival>departure: problems.append('前后交通含接驳与办理缓冲后衔接不足，请调整班次')
    # Rest and transfer days still need food; an empty activity list is not a free day.
    for day in dates(plan.start_date,plan.end_date):
        meals={m['type'] for c in city_views for detail in c['days'] if detail and detail['date']==day for m in detail['meals']}
        for kind,label in [('breakfast','早餐'),('lunch','午餐'),('dinner','晚餐')]:
            if kind not in meals: missing.append(day+' '+label+'尚未在本次安排中确认，费用待补充')
    missing=list(dict.fromkeys(missing));problems=list(dict.fromkeys(problems));total=round(transport_total+hotel_total+local_total,2)
    return dict(cities=city_views,transfers=transfers,nights=nights,conflicts=problems,missing=missing,
        budget=dict(total=total,transport=round(transport_total,2),hotels=round(hotel_total,2),local=round(local_total,2),limit=plan.budget,complete=not missing,is_within_budget=False if plan.budget and total>plan.budget else True if plan.budget and not missing else None),
        usable_minutes=sum(w['available_minutes'] for c in city_views for w in c['windows']) if complete_legs else None,door_minutes=all_minutes if complete_legs else None,hotel_changes=max(0,len(plan.stops)-1),
        description=f'这趟{(plan.end_date-plan.start_date).days+1}天旅行依次停留'+ '、'.join(s.city.name for s in plan.stops)+'。移动日先留出赶车、行李和正餐时间，休息时段会占用可安排时间；是否落实请查看每日时间轴，尚未安排的正餐仍需补充。具体安排以已保存时间轴为准。')


def change_report(old,new):
    changes=[];booked=[]
    old_ids={s.id for s in old.stops}
    changes.extend(s.city.name+'加入旅行；请安排住宿与衔接交通' for s in new.stops if s.id not in old_ids)
    if (old.start_date,old.end_date)!=(new.start_date,new.end_date): changes.append('整趟日期改变，请核对所有城市和交通日期')
    if (old.origin,old.destination)!=(new.origin,new.destination): changes.append('出发或返家城市改变，请重新核对首末段车票')
    for s in old.stops:
        new_s=next((x for x in new.stops if x.id==s.id),None)
        if new_s!=s:
            changes.append(s.city.name+'停留、住宿或休息改变；请核对每日安排与报价')
            if new_s and s.rest_periods!=new_s.rest_periods:
                changes.append(s.city.name+'休息时段更新：'+('、'.join(r.date.isoformat()+' '+r.start_time+'—'+r.end_time for r in new_s.rest_periods) or '已移除')+'；保留景点顺序和正餐，放不下时列出冲突')
            for h in s.lodgings:
                if h.booked and (not new_s or h not in new_s.lodgings): booked.append(s.city.name+'已订住宿 '+h.name)
    before={(t.from_stop,t.to_stop):t.leg for t in old.transfers};after={(t.from_stop,t.to_stop):t.leg for t in new.transfers}
    old_cities={(a,b):(frm.name,to.name) for a,b,frm,to,_ in edges(old)}
    new_cities={(a,b):(frm.name,to.name) for a,b,frm,to,_ in edges(new)}
    for edge in before.keys() | after.keys():
        l=before.get(edge)
        if l!=after.get(edge) or old_cities.get(edge)!=new_cities.get(edge):
            names=new_cities.get(edge) or old_cities.get(edge) or edge
            changes.append('交通 '+names[0]+' → '+names[1]+'改变，两侧活动窗口及预算将更新')
            if l and l.booking_status=='booked': booked.append('已订班次 '+(l.service_number or l.departure_station))
    if old.companions!=new.companions: changes.append('同行人数变化；各城报价和每日费用需重新核对')
    if old.budget!=new.budget: changes.append('整趟预算上限改变')
    return changes,booked


def suggest(plan):
    options=[dict(name='按你的顺序',reason='保留当前城市顺序和停留日期。',plan=plan.model_dump(mode='json'))]
    if len(plan.stops)>1:
        raw=plan.model_dump(mode='json');stops=raw['stops']
        # Only propose a one-night shift; do not pretend to know faster rail routes.
        if (plan.stops[0].end_date-plan.stops[0].start_date).days>=2:
            boundary=plan.stops[0].end_date-timedelta(days=1)
            stops[0]['end_date']=boundary.isoformat();stops[1]['start_date']=boundary.isoformat()
            for s in stops[:2]: s['lodgings']=[h for h in s['lodgings'] if h['booked']]
            raw['transfers']=[t for t in raw['transfers'] if t['leg'] and t['leg']['booking_status']=='booked']
            try: candidate=MultiTrip.model_validate(raw);options.append(dict(name='后段多留一晚',reason='前一城少一晚，后一城多一晚；新日期票价与住宿需重新查询，未订旧报价不沿用。',plan=candidate.model_dump(mode='json')))
            except ValueError: pass
        raw=plan.model_dump(mode='json');order=list(reversed(raw['stops']));cursor=plan.start_date
        for s in order:
            nights=(date.fromisoformat(s['end_date'])-date.fromisoformat(s['start_date'])).days
            s['start_date']=cursor.isoformat();cursor+=timedelta(days=nights);s['end_date']=cursor.isoformat();s['lodgings']=[h for h in s['lodgings'] if h['booked']]
        raw['stops']=order;raw['transfers']=[]
        try: options.append(dict(name='反向走一遍',reason='比较另一种城市顺序；需要重新查各段车票，不表示更省时或更便宜。',plan=MultiTrip.model_validate(raw).model_dump(mode='json')))
        except ValueError: pass
    optional=next((s for s in plan.stops if not s.must_visit),None)
    if len(plan.stops)==3 and optional:
        raw=plan.model_dump(mode='json');i=next(i for i,s in enumerate(raw['stops']) if s['id']==optional.id)
        removed=raw['stops'].pop(i)
        if i<len(raw['stops']): raw['stops'][i]['start_date']=removed['start_date']
        else: raw['stops'][-1]['end_date']=removed['end_date']
        raw['transfers']=[]
        try:
            candidate=MultiTrip.model_validate(raw)
            options=options[:2]+[dict(name='少换一座城市',reason='减少可选城市，把时间留给其余两城，少搬一次行李；已订约束仍需核对，交通和住宿重新查价。',plan=candidate.model_dump(mode='json'))]
        except ValueError: pass
    for option in options:
        new=MultiTrip.model_validate(option['plan']);_,booked=change_report(plan,new);option['blocked']=booked;option['summary']=projection(new)
    return options[:3]


def document(row):
    d=json.loads(row.request_json)
    if d.get('kind')!=KIND: raise HTTPException(404,'多城市旅行不存在')
    return d

async def load(trip_id):
    async with async_session() as s:
        row=await s.get(TripDraft,trip_id)
        if not row: raise HTTPException(404,'多城市旅行不存在')
        return document(row)

async def create(plan,source_id=None,snapshots=None):
    trip_id='mc_'+uuid.uuid4().hex
    d=dict(kind=KIND,id=trip_id,revision=1,status='draft',source_id=source_id,plan=plan.model_dump(mode='json'),snapshots=snapshots or {})
    async with async_session() as s:
        s.add(TripDraft(id=trip_id,user_id='default',status='multi_city',request_json=dump(d),selected_attractions_json='[]',macro_plan_json='{}',clusters_data_json='[]',hotels_by_day_json='[]',dining_pool_json='[]',weather_info_json='[]',days_detail_json='[]'))
        await s.commit()
    return d

async def write(trip_id,expected_revision,transform):
    async with async_session() as s:
        await s.execute(text('BEGIN IMMEDIATE'));row=await s.get(TripDraft,trip_id)
        if not row: raise HTTPException(404,'多城市旅行不存在')
        d=document(row)
        if d['revision']!=expected_revision: raise HTTPException(409,'整趟旅行已更新，本次修改尚未保存，请重新加载')
        if d['status']=='saved': raise HTTPException(409,'已保存版本只读，请先创建新版本')
        d=await transform(d,s)
        d['revision']+=1;row.request_json=dump(d);row.updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
        if d['status']=='saved': row.status='multi_saved'
        await s.commit()
        return d


def response(d):
    return {**d,'summary':d.get('saved_summary') or projection(MultiTrip.model_validate(d['plan']),d['snapshots'])}


def suggest_rest(plan):
    """User-invoked proposal. Existing reservations are retained, never replaced."""
    from ..models.rest import RestPeriod
    from ..agents.langgraph_agent.assemble.schedule import clock
    proposed=plan.model_copy(deep=True);notes=[]
    for i,stop in enumerate(proposed.stops):
        req=city_request(proposed,stop)
        incoming=edges(proposed)[i][4]
        for day in dates(stop.start_date,stop.end_date):
            if any(r.date.isoformat()==day for s in proposed.stops for r in s.rest_periods): continue
            regular=(date.fromisoformat(day)-plan.start_date).days%3==2
            recovery=bool(incoming and incoming.arrival_time[:10]==day and transport_metrics(incoming,'',1)['minutes']>=240)
            if not regular and not recovery: continue
            w=travel_window(req,day)
            # Keep common lunch/dinner windows free; do not claim a shorter break is half a day.
            duration=180 if regular else 60
            choices=[(840,1020),(540,660),(1140,1260)] if regular else [(max(480,w['start_minutes']),660),(840,1020),(1140,1260)]
            selected=next((max(lo,w['start_minutes']) for lo,hi in choices if max(lo,w['start_minutes'])+duration<=min(hi,w['end_minutes'])),None)
            if selected is None and regular:
                duration=60
                selected=next((max(lo,w['start_minutes']) for lo,hi in choices if max(lo,w['start_minutes'])+duration<=min(hi,w['end_minutes'])),None)
            if selected is None:
                # On a shared transfer day, the next city may have the usable interval.
                if day==stop.end_date.isoformat() and i+1<len(proposed.stops): continue
                notes.append(stop.city.name+' '+day+'没有足够连续时段，请先减少活动或调整交通，再添加休息')
                continue
            stop.rest_periods.append(RestPeriod(id=uuid.uuid4().hex,date=day,start_time=clock(selected),end_time=clock(selected+duration),label='换城后歇一歇' if recovery else '连续出行后，留一段休息'))
    return dict(plan=proposed.model_dump(mode='json'),notes=notes)
