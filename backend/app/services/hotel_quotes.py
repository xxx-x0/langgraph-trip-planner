"""Quote provenance and cost allocation. Provider facts never come from an LLM."""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
from urllib.parse import urlparse, parse_qs

from ..models.schemas import Hotel, HotelOccupancy, HotelQuote, TripRequest


def occupancy_for(request: TripRequest) -> tuple[HotelOccupancy, bool]:
    if request.hotel_occupancy:
        return request.hotel_occupancy, True
    # Legacy requests lack ages/rooms. Keep the assumption visible and unconfirmed.
    return HotelOccupancy(adults_per_room=request.companions.count if request.companions else 1), False


def quote_context(request: TripRequest) -> HotelQuote:
    occupancy, confirmed = occupancy_for(request)
    from .journey_service import stay_dates
    start, end = stay_dates(request)
    return HotelQuote(check_in=start, check_out=end,
                      nights=(date.fromisoformat(end)-date.fromisoformat(start)).days,
                      occupancy=occupancy, occupancy_confirmed=confirmed,
                      queried_at=datetime.now(timezone.utc).isoformat(),
                      unsupported_conditions=[] if confirmed else ['入住配置未确认：暂按全部为成人、1间房查询'])


def positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def apply_detail(hotel: dict, raw: dict, context: HotelQuote) -> dict:
    """Only adopt a matching identity/date/occupancy response and an explicit rate plan.

    averagePrice is treated as an average for a single room only. This endpoint
    does not document multi-room amount units; never multiply a possibly-total price.
    """
    result = dict(hotel)
    q = context.model_copy(deep=True)
    q.queried_at = datetime.now(timezone.utc).isoformat()
    q.status = 'detail_returned'
    if not isinstance(raw, dict) or raw.get('success') is not True:
        q.status = 'failed'
        q.unsupported_conditions.append('酒店详情未取得，搜索价格不能作为房型报价')
    elif str(raw.get('hotelId')) != str(hotel.get('hotel_id')) or raw.get('checkIn') != q.check_in or raw.get('checkOut') != q.check_out:
        q.status = 'failed'
        q.unsupported_conditions.append('详情酒店或入住日期与请求不一致')
    else:
        # The returned booking link is the provider's echo, not proof of a booking.
        echo = parse_qs(urlparse(str(raw.get('bookingUrl') or '')).query)
        expected = {'roomCount': str(q.occupancy.room_count), 'adultCount': str(q.occupancy.adults_per_room),
                    'childCount': str(len(q.occupancy.children_ages))}
        if any(echo.get(k, [None])[0] != v for k, v in expected.items()):
            q.unsupported_conditions.append('详情未回显匹配的房间/入住人数')
        actual_ages = echo.get('childAgeDetails', [''])[0]
        if q.occupancy.children_ages and actual_ages != ','.join(map(str, q.occupancy.children_ages)):
            q.unsupported_conditions.append('详情未回显匹配的儿童年龄')
        if q.occupancy.room_count > 1:
            q.unsupported_conditions.append('多房报价口径待确认，不能将展示价乘房间数')
        rates = raw.get('roomRatePlans')
        if not isinstance(rates, list):
            q.unsupported_conditions.append('详情没有可识别的房型报价')
        else:
            candidates = [r for r in rates if isinstance(r, dict) and positive_number(r.get('averagePrice')) is not None]
            # Compare only one currency, never sort different currencies as if equivalent.
            people = q.occupancy.adults_per_room + len(q.occupancy.children_ages)
            candidates = [r for r in candidates if not isinstance((r.get('roomInfo') or {}).get('maxOccupancy'), (int, float)) or (r.get('roomInfo') or {})['maxOccupancy'] >= people]
            candidates = [r for r in candidates if r.get('currency') == 'CNY'] or candidates[:1]
            if not candidates:
                q.status, q.availability = 'unavailable', 'unavailable'
                q.unsupported_conditions.append('未返回可用房型报价')
            else:
                r = min(candidates, key=lambda r: (r.get('isOnRequest') is not False, float(r['averagePrice'])))
                q.amount, q.currency = positive_number(r['averagePrice']), r.get('currency')
                q.unit = 'average_per_room_night' if q.occupancy.room_count == 1 else 'unknown'
                q.provider_price_field, q.cost_kind = 'roomRatePlans.averagePrice', 'query_quote'
                q.room_name, q.rate_plan_id = r.get('roomName'), r.get('ratePlanId')
                q.bed_type, q.meal_plan = r.get('bedTypeDescription'), r.get('mealTypeStr')
                q.cancellation_policy = r.get('cancelPolicy')
                q.taxes_included = r.get('taxesIncluded') if isinstance(r.get('taxesIncluded'), bool) else None
                q.availability = 'on_request' if r.get('isOnRequest') is True else 'returned' if r.get('isOnRequest') is False else 'unknown'
                capacity = (r.get('roomInfo') or {}).get('maxOccupancy')
                if isinstance(capacity, (int, float)) and capacity < q.occupancy.adults_per_room + len(q.occupancy.children_ages):
                    q.unsupported_conditions.append('房型标注入住上限不足')
                result['detail_url'] = raw.get('bookingUrl') or result.get('detail_url')
    result.update(quote=q.model_dump(), price=q.amount, currency=q.currency or hotel.get('currency', 'CNY'), estimated_cost=0)
    return result


async def enrich_selected_hotel(hotel: dict, request: TripRequest, service, detail_tool) -> dict:
    q = quote_context(request)
    q.unsupported_conditions.append('搜索初筛未核对房型，儿童和房间数以详情为准')
    result = dict(hotel, quote=q.model_dump(), estimated_cost=0)
    if not detail_tool or not hotel.get('hotel_id'):
        return result
    schema = getattr(detail_tool, 'args_schema', None)
    schema = schema if isinstance(schema, dict) else schema.model_json_schema() if schema and hasattr(schema, 'model_json_schema') else {}
    props = schema.get('properties', {})
    dates = props.get('dateParam', {}).get('properties', {})
    occupancy = props.get('occupancyParam', {}).get('properties', {})
    if not {'checkInDate', 'checkOutDate'} <= dates.keys() or not {'adultCount', 'roomCount', 'childCount', 'childAgeDetails'} <= occupancy.keys():
        q.unsupported_conditions.append('当前详情接口不能完整表达入住条件')
        result['quote'] = q.model_dump()
        return result
    q.unsupported_conditions.remove('搜索初筛未核对房型，儿童和房间数以详情为准')
    try:
        raw = await service.get_hotel_detail(hotel['hotel_id'], check_in=q.check_in, stay_nights=q.nights,
                                             adult_count=q.occupancy.adults_per_room, room_count=q.occupancy.room_count,
                                             children_ages=q.occupancy.children_ages)
    except Exception:
        q.status = 'failed'
        q.unsupported_conditions.append('酒店详情查询失败，房型价格待确认')
        return dict(result, quote=q.model_dump())
    return apply_detail(hotel, raw, q)


def hotel_cost_for_date(hotel: Hotel, day: str) -> tuple[float, list[str]]:
    q = hotel.quote
    if not q:
        # Original JSON is left untouched; old unproven estimates cannot become known quotes.
        return 0, ['旧记录住宿报价条件未核对']
    missing = list(q.unsupported_conditions)
    try:
        start, end, current = map(date.fromisoformat, (q.check_in, q.check_out, day))
        valid_dates = start <= current < end and (end-start).days == q.nights and q.nights > 0
    except ValueError:
        valid_dates = False
    if not valid_dates:
        return 0, missing + ['住宿报价日期不覆盖本晚']
    if q.status == 'unavailable' or q.availability == 'unavailable':
        return 0, missing + ['未返回可售房型，请重新选择住宿']
    if q.status != 'detail_returned' or q.amount is None or q.cost_kind not in {'query_quote', 'user_estimate', 'system_estimate', 'paid'}:
        return 0, missing + ['住宿房型报价待确认']
    if not q.occupancy_confirmed:
        missing.append('入住配置未确认')
    if q.currency != 'CNY' or q.unit == 'unknown' or missing:
        return 0, missing + (['住宿币种或计费单位待确认'] if q.currency != 'CNY' or q.unit == 'unknown' else [])
    if q.availability in {'unavailable', 'unknown', 'on_request'}:
        missing.append('住宿可售状态待确认')
    if q.taxes_included is not True:
        missing.append('住宿税费未确认或未包含')
    if not q.meal_plan:
        missing.append('住宿早餐条件待确认')
    if not q.cancellation_policy:
        missing.append('住宿退改条件待确认')
    if q.cost_kind in {'user_estimate', 'system_estimate'}:
        missing.append('住宿为估算，尚无查询报价')
    total = Decimal(str(q.amount))
    if q.unit == 'average_per_room_night':
        total *= q.nights * q.occupancy.room_count
    cents = int((total * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    base, extra = divmod(cents, q.nights)
    offset = (current-start).days
    return (base + (1 if offset < extra else 0)) / 100, missing
