from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from app.models.schemas import Hotel, HotelQuote, HotelOccupancy, TripRequest
from app.services.hotel_quotes import apply_detail, quote_context, hotel_cost_for_date, enrich_selected_hotel


def request(**overrides):
    return TripRequest(**(dict(city='苏州', start_date='2026-10-19', end_date='2026-10-21', travel_days=3,
        transportation='公共交通', accommodation='经济型', companions={'count':2},
        hotel_occupancy={'room_count':1,'adults_per_room':2,'children_ages':[]}) | overrides))


def response(**overrides):
    return dict(success=True, hotelId=123, checkIn='2026-10-19', checkOut='2026-10-21',
        bookingUrl='https://rollinggo.cn/pages/hotel/detail/index?id=123&roomCount=1&adultCount=2&childCount=0',
        roomRatePlans=[dict(averagePrice=123.45,currency='CNY',roomName='双床',ratePlanId='rate',
        bedTypeDescription='双床',mealTypeStr='含双早',cancelPolicy='不可退',isOnRequest=False,
        roomInfo={'maxOccupancy':2})]) | overrides


def parsed(raw=None, req=None):
    return Hotel(**apply_detail({'name':'H','hotel_id':123,'estimated_cost':800},
                               raw if raw is not None else response(), quote_context(req or request())))


def test_real_room_quote_keeps_provenance_and_does_not_round_yuan():
    hotel=parsed()
    assert hotel.estimated_cost == 0
    assert hotel.quote.provider_price_field == 'roomRatePlans.averagePrice'
    assert hotel.quote.queried_at and hotel.quote.room_name == '双床'
    cost, missing = hotel_cost_for_date(hotel,'2026-10-19')
    assert cost == 123.45
    assert '住宿税费未确认或未包含' in missing
    assert hotel.quote.nights == 2 and hotel.quote.cost_kind == 'query_quote'


@pytest.mark.parametrize('override', [{'success':False},{'hotelId':999},{'checkIn':'2026-10-20'},{'checkOut':'2026-10-22'}])
def test_identity_or_dates_mismatch_never_charges(override):
    h=parsed(response(**override))
    assert h.quote.status=='failed' and h.quote.amount is None
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


@pytest.mark.parametrize('value', [None,True,-1,float('nan'),float('inf'),'unknown'])
def test_invalid_or_missing_room_price_never_becomes_known(value):
    raw=response();raw['roomRatePlans'][0]['averagePrice']=value
    h=parsed(raw)
    assert h.quote.amount is None and hotel_cost_for_date(h,'2026-10-19')[0]==0


@pytest.mark.parametrize('rates', [None,[],[{'totalPrice':500,'currency':'CNY'}]])
def test_missing_inventory_or_different_price_field_stays_unknown(rates):
    h=parsed(response(roomRatePlans=rates))
    assert h.quote.amount is None
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_capacity_filters_cheapest_room_for_family():
    req=request(companions={'count':3},hotel_occupancy={'adults_per_room':2,'children_ages':[8]})
    raw=response(bookingUrl='https://rollinggo.cn/?roomCount=1&adultCount=2&childCount=1&childAgeDetails=8')
    bigger=deepcopy(raw['roomRatePlans'][0]);bigger.update(averagePrice=200,roomName='家庭房',roomInfo={'maxOccupancy':3})
    raw['roomRatePlans'].append(bigger)
    h=parsed(raw,req)
    assert h.quote.room_name=='家庭房' and h.quote.amount==200
    assert not h.quote.unsupported_conditions


@pytest.mark.parametrize('echo', ['', 'roomCount=1&adultCount=1&childCount=0', 'roomCount=1&adultCount=2&childCount=1&childAgeDetails=9'])
def test_missing_or_different_occupancy_echo_is_not_confirmed(echo):
    h=parsed(response(bookingUrl='https://rollinggo.cn/?'+echo))
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_children_age_mismatch_blocks_budget():
    req=request(companions={'count':3},hotel_occupancy={'adults_per_room':2,'children_ages':[8]})
    raw=response(bookingUrl='https://rollinggo.cn/?roomCount=1&adultCount=2&childCount=1&childAgeDetails=9')
    raw['roomRatePlans'][0]['roomInfo']['maxOccupancy']=3
    h=parsed(raw,req)
    assert any('儿童年龄' in s for s in h.quote.unsupported_conditions)
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_multi_room_amount_is_not_multiplied_without_unit_contract():
    req=request(hotel_occupancy={'room_count':2,'adults_per_room':1})
    h=parsed(response(bookingUrl='https://rollinggo.cn/?roomCount=2&adultCount=1&childCount=0'),req)
    assert h.quote.unit=='unknown'
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_old_request_occupancy_is_explicitly_unconfirmed():
    h=parsed(req=request(hotel_occupancy=None))
    assert not h.quote.occupancy_confirmed
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_currency_is_not_converted_or_summed_as_cny():
    raw=response();raw['roomRatePlans'][0]['currency']='USD'
    h=parsed(raw)
    assert h.quote.amount==123.45 and h.quote.currency=='USD'
    assert hotel_cost_for_date(h,'2026-10-19')[0]==0


def test_total_stay_allocates_cents_once_including_rounding():
    h=parsed();h.quote.unit='total_stay';h.quote.amount=101.01
    assert [hotel_cost_for_date(h,d)[0] for d in ['2026-10-19','2026-10-20']]==[50.51,50.5]
    assert hotel_cost_for_date(h,'2026-10-21')[0]==0


def test_legacy_star_estimate_never_counted():
    h=Hotel(name='旧酒店',estimated_cost=800,price=800)
    assert hotel_cost_for_date(h,'2026-10-19')==(0,['旧记录住宿报价条件未核对'])


@pytest.mark.parametrize('availability', ['unknown','on_request','unavailable'])
def test_unconfirmed_inventory_remains_visible(availability):
    h=parsed();h.quote.availability=availability
    value,missing=hotel_cost_for_date(h,'2026-10-19')
    assert missing
    if availability=='unavailable':assert value==0


@pytest.mark.parametrize('occupancy', [{'room_count':0},{'children_ages':[18]},{'adults_per_room':0},{'room_count':2,'adults_per_room':2}])
def test_invalid_occupancy_or_group_mismatch_is_rejected(occupancy):
    with pytest.raises(ValidationError):request(hotel_occupancy=occupancy)


@pytest.mark.asyncio
async def test_detail_failure_or_unsupported_tool_schema_leaves_candidate_unknown():
    service=SimpleNamespace(get_hotel_detail=AsyncMock(side_effect=TimeoutError()))
    schema={'properties':{'dateParam':{'properties':{'checkInDate':{},'checkOutDate':{}}},
            'occupancyParam':{'properties':{k:{} for k in ['adultCount','roomCount','childCount','childAgeDetails']}}}}
    hotel={'name':'H','hotel_id':123,'estimated_cost':500}
    out=await enrich_selected_hotel(hotel,request(),service,SimpleNamespace(args_schema=schema))
    assert out['quote']['status']=='failed' and out['estimated_cost']==0
    assert hotel['estimated_cost']==500 # no in-place change
    out=await enrich_selected_hotel(hotel,request(),service,SimpleNamespace(args_schema=None))
    assert out['quote']['status']=='search_only'
    assert service.get_hotel_detail.await_count==1


@pytest.mark.parametrize('start,end', [('invalid','2026-10-21'),('2026-10-22','2026-10-21'),('2026-10-01','2026-11-01')])
def test_invalid_date_range_is_rejected_before_provider(start,end):
    with pytest.raises(ValidationError): request(start_date=start,end_date=end)


def test_stay_average_rounds_total_once_not_every_night():
    h=parsed();h.quote.amount=213.335
    assert [hotel_cost_for_date(h,d)[0] for d in ['2026-10-19','2026-10-20']]==[213.34,213.33]


@pytest.mark.asyncio
async def test_child_age_and_room_count_reach_detail_request():
    from app.services.aigohotel_mcp_service import AIGoHotelService
    service=AIGoHotelService();service._call_tool=AsyncMock(return_value={})
    await service.get_hotel_detail(123,check_in='2026-12-31',stay_nights=2,adult_count=2,room_count=2,children_ages=[8])
    args=service._call_tool.await_args.args[1]
    assert args['dateParam']=={'checkInDate':'2026-12-31','checkOutDate':'2027-01-02'}
    assert args['occupancyParam']=={'adultCount':2,'roomCount':2,'childCount':1,'childAgeDetails':[8]}


@pytest.mark.asyncio
async def test_primary_and_fallback_search_preserve_stay_conditions():
    from unittest.mock import patch
    from app.agents.langgraph_agent.nodes.search import _aigohotel_search_for_day, _aigohotel_city_fallback
    call=AsyncMock(return_value={'hotelInformationList':[]})
    with patch('app.agents.langgraph_agent.nodes.search._invoke_tool_with_retry',new=call):
        await _aigohotel_search_for_day(object(),'留园','苏州','经济型',(120,31),3,[2,3],'2026-10-19',3,2)
        await _aigohotel_city_fallback(object(),'苏州','经济型',[2,3],'2026-10-19',3,2)
    for called in call.await_args_list:
        args=called.args[1]
        assert args['checkInParam']=={'checkInDate':'2026-10-19','stayNights':3,'adultCount':2}
        assert 'withHotelAmenities' not in args and 'withRoomAmenities' not in args
    assert call.await_args_list[0].args[1]['place']=='留园 苏州'
    assert call.await_args_list[1].args[1]['place']=='苏州 中国'


def test_unavailable_status_without_price_is_explicit_not_generic_missing_quote():
    h=parsed();h.quote.status='unavailable';h.quote.availability='unavailable';h.quote.amount=None
    amount,missing=hotel_cost_for_date(h,'2026-10-19')
    assert amount==0 and any('未返回可售房型' in item for item in missing)
    assert not any('房型报价待确认' in item for item in missing)
