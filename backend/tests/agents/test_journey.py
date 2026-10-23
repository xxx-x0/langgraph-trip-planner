"""Manual travel scenarios; no live fare assertions."""
import pytest
from pydantic import ValidationError
from app.models.schemas import TripRequest, DayDetail, DraftDayContext, Attraction, DiningPoolDay
from app.models.journey import JourneyLeg, Journey, local_instant
from app.services.journey_service import travel_window, stay_dates, apply_context, conflicts
from app.agents.langgraph_agent.assemble.budget import compute_day_budget,combine_budgets
from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def leg(**changes):
    return JourneyLeg(**(dict(departure_station='上海虹桥',arrival_station='苏州',departure_time='2026-10-19T08:00',arrival_time='2026-10-19T09:00',ticket_total=120.5,extras_total=30,price_source='user_estimate',passengers=2)|changes))


def request(**changes):
    return TripRequest(**(dict(city='苏州',start_date='2026-10-19',end_date='2026-10-21',travel_days=3,transportation='步行',accommodation='民宿',companions={'count':2},journey=Journey(origin_city='上海',return_city='上海',outbound=leg(),inbound=leg(departure_time='2026-10-21T10:00',arrival_time='2026-10-21T11:00')))|changes))


def test_roundtrip_total_is_party_price_once_and_return_cuts_last_day():
    req=request(); days=[]
    for i,d in enumerate(['2026-10-19','2026-10-20','2026-10-21']):
        detail=apply_context(DayDetail(day_index=i,date=d),req);days.append(compute_day_budget(detail))
    assert combine_budgets(days).total_intercity==301
    assert combine_budgets(days).total_transportation==301
    assert travel_window(req,'2026-10-19')['start_minutes']==660
    assert travel_window(req,'2026-10-21')['end_minutes']==450
    assert not travel_window(req,'2026-10-21')['overnight_stay']


def test_cross_midnight_arrival_has_no_first_day_stay_and_no_free_unknown_price():
    req=request(journey=Journey(origin_city='上海',return_city='上海',outbound=leg(departure_time='2026-10-19T23:00',arrival_time='2026-10-20T08:00',ticket_total=None,extras_total=None,price_source='unknown')))
    assert stay_dates(req)==('2026-10-20','2026-10-21')
    first=travel_window(req,'2026-10-19')
    assert first['unavailable'] and not first['overnight_stay']
    assert first['intercity_cost']==0 and first['unknown_cost_items']
    assert travel_window(req,'2026-10-20')['start_minutes']==600


def test_overnight_international_elapsed_and_destination_window():
    req=request(journey=Journey(origin_city='洛杉矶',return_city='上海',outbound=leg(departure_time='2026-10-19T23:00',arrival_time='2026-10-21T05:00',departure_timezone='America/Los_Angeles')))
    w=travel_window(req,'2026-10-21');assert w['start_minutes']==420
    assert w['legs'][0]['duration_minutes']==900


@pytest.mark.parametrize('value,zone',[('2026-03-08T02:30','America/New_York'),('2026-11-01T01:30','America/New_York'),('2026-10-19T08:00','Bad/Zone'),('2026-10-19T08:00+08:00','Asia/Shanghai')])
def test_invalid_or_ambiguous_local_time_rejected(value,zone):
    with pytest.raises(ValueError):local_instant(value,zone)


@pytest.mark.parametrize('changes',[{'arrival_time':'2026-10-19T07:00'},{'ticket_total':-1},{'ticket_total':float('inf')},{'price_source':'unknown'},{'price_source':'paid'},{'station_buffer_minutes':-1}])
def test_invalid_leg_rejected(changes):
    with pytest.raises(ValidationError):leg(**changes)


def test_passengers_and_dates_checked_at_request_boundary():
    with pytest.raises(ValidationError):request(companions={'count':1})
    with pytest.raises(ValidationError):request(end_date='2026-10-20',travel_days=2)


def test_late_arrival_skips_default_lunch_and_conflicts_are_named():
    req=request(journey=Journey(origin_city='上海',return_city='上海',outbound=leg(arrival_time='2026-10-19T16:00')))
    ctx=apply_context(DraftDayContext(day_index=0,date=req.start_date,attractions=[Attraction(name='园林',address='',description='',visit_duration=90)],dining_pool=DiningPoolDay(main=[{'name':n,'category':'main'} for n in ['甲餐馆','乙餐馆']])),req)
    detail=rule_assemble_day_timeline(ctx);assert detail.day_start_time=='18:00'
    assert [m.type for m in detail.meals]==['dinner']
    schedule_day(detail);assert not conflicts(detail)
    detail.travel_window['end_minutes']=19*60
    assert any('园林' in x for x in conflicts(detail))


def test_foreign_currency_is_not_added_as_yuan():
    req=request(journey=Journey(origin_city='上海',return_city='上海',outbound=leg(currency='USD')))
    w=travel_window(req,req.start_date)
    assert w['intercity_cost']==0
    assert any('USD' in x for x in w['unknown_cost_items'])


def test_sparse_real_shape_delays_restaurant_trip_and_offers_opt_in_shift():
    ctx=DraftDayContext(day_index=0,date='2026-10-19',day_start_time='08:00',attractions=[Attraction(name=n,address='',description='',visit_duration=90) for n in ['西园','山塘']])
    detail=rule_assemble_day_timeline(ctx,{'meals':[{'name':'午餐','type':'lunch','category':'main','insert_after':'山塘','open_hours':'11:00-22:00'}, {'name':'晚餐','type':'dinner','category':'main','insert_after':'山塘','open_hours':'11:00-22:00'}]})
    schedule_day(detail)
    gap=next(x for x in detail.timeline_schedule if x['kind']=='free_time' and x['duration']>100)
    index=detail.timeline_schedule.index(gap)
    assert detail.timeline_schedule[index+1]['kind']=='travel'
    assert detail.timeline_schedule[index+2]['start_time']=='17:30'
    assert detail.day_start_time=='08:00'  # never silently change user intent
    assert detail.schedule_suggestion['saved_minutes']>=60
    after=detail.model_copy(deep=True);after.day_start_time=detail.schedule_suggestion['day_start_time'];schedule_day(after)
    assert sum(x['duration'] for x in after.timeline_schedule if x['kind'] in {'wait','free_time'}) < sum(x['duration'] for x in detail.timeline_schedule if x['kind'] in {'wait','free_time'})
    assert [a.name for a in after.attractions]==[a.name for a in detail.attractions]
    assert [m.type for m in after.meals]==['lunch','dinner']


def test_empty_in_transit_day_has_no_hotel_activity_or_default_meals():
    from app.models.schemas import Hotel
    req=request(journey=Journey(origin_city='上海',return_city='上海',outbound=leg(departure_time='2026-10-19T23:00',arrival_time='2026-10-20T08:00')))
    ctx=apply_context(DraftDayContext(day_index=0,date=req.start_date,hotel=Hotel(name='H')),req)
    detail=rule_assemble_day_timeline(ctx);schedule_day(detail)
    assert detail.timeline_schedule==[] and not detail.overnight_stay
    assert conflicts(detail)==[]


def test_later_departure_suggestion_does_not_make_booked_return_impossible():
    from app.models.schemas import Meal
    detail=DayDetail(day_index=0,date='2026-10-19',day_start_time='08:00',attractions=[],meals=[Meal(name='午餐',type='lunch',preferred_slot='lunch')],timeline_order=[{'kind':'meal','ref_name':'午餐'}],travel_window={'start_minutes':0,'end_minutes':760})
    schedule_day(detail)
    assert detail.schedule_suggestion
    trial=detail.model_copy(deep=True)
    trial.day_start_time=detail.schedule_suggestion['day_start_time']
    schedule_day(trial)
    assert not conflicts(trial)
    assert all(x['end_minutes'] <= 760 for x in trial.timeline_schedule if x['kind']=='meal')


def test_idle_gap_is_not_an_unknown_expense_and_buffers_show_next_day_arrival():
    detail=DayDetail(day_index=0,date='2026-10-19',meal_warnings=['13:00起有246分钟未安排，请调整出发时间或补充下午活动','午餐未安排，请自行安排或补充餐厅'])
    budget=compute_day_budget(detail)
    assert not any('246' in x for x in budget.unknown_cost_items)
    assert any('午餐未安排' in x for x in budget.unknown_cost_items)
    req=request(journey=Journey(origin_city='上海',return_city='上海',inbound=leg(departure_time='2026-10-21T22:00',arrival_time='2026-10-21T23:00')))
    window=travel_window(req,req.end_date)
    assert window['legs'][0]['door_arrival'].startswith('2026-10-22T00:30')
    assert any('超出所填旅行日期' in x for x in window['notes'])


def test_history_projection_updates_travel_facts_and_costs_without_mutating_input():
    import copy
    from app.models.schemas import TripPlan,DayPlan,Budget
    from app.services.trip_history_service import project_saved_narratives
    req=request()
    plan=TripPlan(city=req.city,start_date=req.start_date,end_date=req.end_date,journey=req.journey,companions=req.companions,overall_suggestions='',budget=Budget(unknown_cost_items=['13:00起有246分钟未安排']),days=[DayPlan(date=d,day_index=i,description='',transportation='步行',accommodation='民宿') for i,d in enumerate(['2026-10-19','2026-10-20','2026-10-21'])])
    raw=plan.model_dump(mode='json');snapshot=copy.deepcopy(raw)
    projected=project_saved_narratives(copy.deepcopy(raw))
    assert raw==snapshot
    assert projected['budget']['total_intercity']==301
    assert projected['days'][-1]['travel_window']['legs'][0]['door_arrival']
    assert not any('246' in x for x in projected['budget']['unknown_cost_items'])
