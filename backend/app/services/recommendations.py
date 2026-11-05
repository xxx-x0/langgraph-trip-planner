"""Explain selections from this request and provider facts. No profile or model claims."""
from datetime import datetime, timezone
import math
from ..models.schemas import Attraction
from ..agents.langgraph_agent.assemble.schedule import estimated_lunch_anchor, opening_windows
from ..agents.langgraph_agent.utils.geo import _haversine_distance


def intent_for(request):
    return {k: getattr(request, k) for k in ('food_preference', 'free_text_input', 'meal_budget_per_person',
                                           'dietary_requirements', 'dining_style', 'preferences')} | {
        'companion_type': request.companions.type if request.companions else 'solo',
        'companion_count': request.companions.count if request.companions else 1,
        'children': bool(request.hotel_occupancy and request.hotel_occupancy.children_ages),
    }


def meal_anchors(attractions, start='08:00', schedule=None, hotel=None, meals=None):
    """Use saved meal gaps when present; otherwise estimate lunch from visit durations."""
    by_name = {a.name:a for a in attractions}
    by_meal = {m.name:m for m in meals or []}
    lunch = estimated_lunch_anchor(attractions, start)
    result = {}
    for slot in ('lunch', 'dinner'):
        before = by_name.get(lunch) if slot == 'lunch' else (attractions[-1] if attractions else None)
        after = None
        if before:
            index = attractions.index(before)
            after = attractions[index+1] if index+1 < len(attractions) else hotel
        target = 720 if slot == 'lunch' else 1080
        activities = [x for x in schedule or [] if x.get('kind') in {'meal','attraction','hotel'}]
        actual = next((i for i,x in enumerate(activities) if x.get('kind')=='meal' and (not by_meal or (by_meal.get(x.get('ref_name')) and by_meal[x['ref_name']].type == slot)) and
                       ((slot=='lunch' and 630 <= x.get('start_minutes',0) <= 870) or
                        (slot=='dinner' and 1050 <= x.get('start_minutes',0) <= 1290))), None)
        if actual is not None:
            prev = next((x for x in reversed(activities[:actual]) if x['kind'] in {'attraction','hotel'} or x['ref_name'] in by_meal), None)
            nxt = next((x for x in activities[actual+1:] if x['kind'] in {'attraction','hotel'} or x['ref_name'] in by_meal), None)
            lookup = {**by_name, **by_meal}
            if hotel: lookup[hotel.name] = hotel
            before = lookup.get(prev['ref_name']) if prev else None
            after = lookup.get(nxt['ref_name']) if nxt else None
            target = activities[actual]['start_minutes']
        result[slot] = (before, after, target)
    return result


def cluster_attractions(cluster):
    return [Attraction(name=p['name'], address=p.get('address') or '',
                       location={'longitude':p['longitude'],'latitude':p['latitude']} if p.get('longitude') and p.get('latitude') else None,
                       visit_duration=p.get('visit_minutes') or p.get('visit_duration') or 120,
                       description='') for p in cluster if p.get('name')]


def distance(a,b):
    if not a or not b: return None
    return _haversine_distance(a.latitude,a.longitude,b.latitude,b.longitude)


def explain_dining(candidates, attractions, intent, start='08:00', schedule=None, hotel=None, meals=None, *, anchors_override=None):
    anchors=anchors_override or meal_anchors(attractions,start,schedule,hotel,meals)
    for c in candidates:
        old=c.recommendation
        if c.cuisine in {'餐饮相关','餐饮相关场所','餐饮服务','中餐厅'}: c.cuisine=None
        reasons=[]; cautions=[]; matches=[]
        closed = any(word in (c.name+' '+(c.open_hours or '')) for word in ('暂停营业','永久关闭','已歇业'))
        if closed: cautions.append('来源标注暂停或停止营业，不可作为当前用餐选择')
        cap=intent.get('meal_budget_per_person')
        if c.avg_cost is not None:
            reasons.append(f'高德参考人均{c.avg_cost}元；{intent.get("companion_count",1)}人约{c.avg_cost*intent.get("companion_count",1)}元，按成人均价估算')
            if cap:
                (cautions if c.avg_cost>cap else reasons).append(f'{"高于" if c.avg_cost>cap else "不高于"}你设定的每人每餐{cap}元')
        else: cautions.append('人均价格未提供')
        preference=intent.get('food_preference','')
        if c.cuisine and preference and preference not in {'本地特色','无特殊要求'} and preference in c.cuisine:
            reasons.append(f'来源分类为{c.cuisine}，与你本次想吃的{preference}相符')
        if intent.get('dietary_requirements'):
            cautions.append(f'你要求「{intent["dietary_requirements"]}」；来源未证实，请向店家确认后再决定')
        if intent.get('children') or intent.get('companion_type')=='family':
            cautions.append('儿童餐、儿童座椅及儿童实际费用未确认')
        if intent.get('companion_type')=='elderly': cautions.append('无障碍入口、座位及电梯未确认')
        if not c.cuisine: cautions.append('菜系与具体菜单未提供，正餐份量也需向店家确认')
        cautions.append('招牌菜、排队时长和评价量未提供；评分仅来自高德')
        if not c.open_hours: cautions.append('营业时间未提供，请出发前联系店家')
        elif not opening_windows(c.open_hours): cautions.append('营业规则需人工核对：'+c.open_hours)
        stamp=old.get('queried_at')
        if stamp:
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()
                if age>86400: cautions.append('查询已超过24小时，营业状态和价格请重新确认')
            except (ValueError,TypeError): cautions.append('查询时间无法核对')
        else: cautions.append('旧候选未记录查询时间，请重新核实')
        for slot,(before,after,target) in anchors.items():
            first=distance(before.location if before else None,c.location)
            last=distance(c.location,after.location if after else None)
            direct=distance(before.location if before else None,after.location if after else None)
            extra=max(0,first+last-direct) if first is not None and last is not None and direct is not None else (2*first if first is not None else None)
            windows=opening_windows(c.open_hours)
            # This is a screening estimate, never a navigation claim.
            match={'slot':slot,'before':before.name if before else None,'after':after.name if after else None,
                   'distance_km':round(first,1) if first is not None else None,
                   'extra_walk_minutes':math.ceil(extra/4*60) if extra is not None else None,
                   'route_basis':'直线距离按4公里/小时折算，非导航；选择后核对实际路线',
                   'style':'unknown' if first is None else 'on_route' if first<=1.5 and extra is not None and extra<=2 else 'dedicated',
                   'hours_fit':False if closed else any(a<=target and target+60<=b for a,b in windows) if windows else None}
            matches.append(match)
        c.recommendation={'source':'高德地图 POI','queried_at':stamp,'reasons':reasons,'cautions':cautions,'matches':matches}
    return candidates


def dining_for_slot(candidates,slot,intent=None):
    intent=intent or {}
    def key(c):
        m=next((m for m in c.recommendation.get('matches',[]) if m['slot']==slot),{})
        return (m.get('hours_fit') is False,
                bool(intent.get('meal_budget_per_person') and (c.avg_cost is None or c.avg_cost>intent['meal_budget_per_person'])),
                0 if intent.get('dining_style')=='dedicated' and intent.get('food_preference','!') in (c.cuisine or '') else 1,
                m.get('extra_walk_minutes') if m.get('extra_walk_minutes') is not None else 9999,
                -(c.rating or 0))
    return sorted(candidates,key=key)


def explain_hotel(hotel, request):
    reasons=[];cautions=[]
    d=hotel.get('_centroid_distance_km')
    if d is not None:
        reasons.append(f'距本次游玩区域中心直线约{d:.1f}公里；优先比较位置，再参考星级')
        if d>5: cautions.append('距离游玩区域较远，建议先核对每日往返时间再预订')
    else: cautions.append('缺少可核对的位置，无法判断通勤是否方便')
    q=hotel.get('quote') or {}
    reasons.append(f'按本次{max(0,request.travel_days-1)}晚住宿查询')
    if q.get('occupancy_confirmed') and q.get('status') == 'detail_returned' and not q.get('unsupported_conditions'): reasons.append('详情已回显本次入住人数和房间配置；报价限制仍需核对')
    else: cautions.append('入住人数、房间配置或房型报价尚未完整匹配')
    if request.hotel_occupancy and request.hotel_occupancy.children_ages:
        cautions.append('儿童床位、加床费用及适用年龄须向酒店确认')
    cautions.append('位置按坐标估算；隔音、卫生和近期入住体验未验证')
    hotel['recommendation']={'reasons':reasons,'cautions':cautions,'source':'AIGoHotel','queried_at':q.get('queried_at')}
    return hotel
