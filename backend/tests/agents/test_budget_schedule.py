import pytest
from app.models.schemas import Attraction, Hotel, DayDetail, DiningPoolDay, DraftDayContext
from app.agents.langgraph_agent.assemble.budget import compute_day_budget, combine_budgets, parse_ticket_price
from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.agents.langgraph_agent.assemble.schedule import schedule_day, route_minutes


def attraction(name, minutes=90, price=None):
    return Attraction(name=name, address='', description='', visit_duration=minutes, ticket_price=price)


@pytest.mark.parametrize('raw,expected', [('1小时20分钟', 80), ('2小时', 120), ('5分钟', 5), ('未知', 20)])
def test_route_time_units_do_not_move_meals_an_hour_early(raw, expected):
    assert route_minutes(raw) == expected


@pytest.mark.parametrize('raw,expected', [(None, None), ('未知', None), ('免费', 0), (0, 0), ('60元', 60), ('-20', None)])
def test_unknown_is_distinct_from_free(raw, expected):
    assert parse_ticket_price(raw) == expected


@pytest.mark.parametrize('days,nights', [(1, 0), (2, 1), (3, 2)])
def test_stays_charge_only_travel_nights(days, nights):
    from app.models.schemas import HotelQuote, HotelOccupancy
    quote = HotelQuote(queried_at='2026-10-15T00:00:00Z', status='detail_returned', cost_kind='query_quote', amount=310, currency='CNY', unit='average_per_room_night', check_in='2026-10-14', check_out=f'2026-10-{14+nights}', nights=nights, occupancy=HotelOccupancy(), occupancy_confirmed=True, taxes_included=True, meal_plan='不含早', cancellation_policy='不可退', availability='returned')
    budgets = [compute_day_budget(DayDetail(day_index=i, date=f'2026-10-{14+i}',
                hotel=Hotel(name='H', quote=quote), overnight_stay=i < days-1)) for i in range(days)]
    assert combine_budgets(budgets).total_hotels == nights * 310


def test_missing_cost_cannot_claim_within_limit_but_known_excess_is_reported():
    budget = compute_day_budget(DayDetail(day_index=0, date='2026-10-14', overnight_stay=False,
                  attractions=[attraction('免费', price=0), attraction('未知'), attraction('收费', price=60)]))
    assert budget.total_attractions == 60
    assert '2026-10-14 未知门票' in budget.unknown_cost_items
    assert any('往返大交通未纳入' in item for item in budget.unknown_cost_items)
    assert combine_budgets([budget], 1000).is_within_budget is None
    assert combine_budgets([budget], 10).is_within_budget is False
    known = compute_day_budget(DayDetail(day_index=0, date='2026-10-14', overnight_stay=False, attractions=[attraction('免费', price=0)]))
    assert combine_budgets([known], 1000).is_within_budget is None


def test_default_meals_reanchor_on_reorder_without_moving_locks():
    pool = DiningPoolDay(main=[dict(name=n, category='main', avg_cost=60, open_hours='11:00-23:00') for n in ['午餐店', '晚餐店']])
    ctx = DraftDayContext(day_index=0, date='2026-10-14', day_start_time='10:00',
                         attractions=[attraction('山塘'), attraction('留园'), attraction('虎丘', 150)], dining_pool=pool)
    first = rule_assemble_day_timeline(ctx)
    assert [m.type for m in first.meals] == ['lunch', 'dinner']
    overrides = {'attractions_order': ['虎丘', '留园', '山塘'], 'locked_attraction_names': ['留园'],
                 'meals': [m.model_dump() for m in first.meals]}
    detail = rule_assemble_day_timeline(ctx, overrides)
    assert [a.name for a in detail.attractions] == ['虎丘', '留园', '山塘']
    assert detail.locked_attraction_names == ['留园']
    assert [x['ref_name'] for x in detail.timeline_order] == ['虎丘', '午餐店', '留园', '山塘', '晚餐店']
    schedule_day(detail)
    slots = [s for s in detail.timeline_schedule if s['kind'] == 'meal']
    assert 690 <= slots[0]['start_minutes'] <= 870
    assert slots[1]['start_minutes'] >= 1050
    assert not any('午餐未安排' in w or '晚餐未安排' in w for w in detail.meal_warnings)


def test_explicit_late_meal_keeps_anchor_and_is_labeled_dinner_with_missing_lunch():
    ctx = DraftDayContext(day_index=0, date='2026-10-14', day_start_time='10:00',
                          attractions=[attraction('A', 240), attraction('B', 180)])
    detail = rule_assemble_day_timeline(ctx, {'meals': [{'name': '自选餐厅', 'category': 'main',
                'type': 'lunch', 'insert_after': 'B', 'open_hours': '11:00-23:00'}]})
    schedule_day(detail)
    assert [s['ref_name'] for s in detail.timeline_order] == ['A', 'B', '自选餐厅']
    assert detail.meals[0].type == 'dinner'
    assert any('午餐未安排' in w for w in detail.meal_warnings)


def test_opening_hours_wait_and_closed_restaurant_are_explicit():
    ctx = DraftDayContext(day_index=0, date='2026-10-14', day_start_time='08:00', attractions=[attraction('A', 30)])
    detail = rule_assemble_day_timeline(ctx, {'meals': [{'name':'早到餐厅','category':'main','type':'lunch',
              'insert_after':'A','open_hours':'12:00-16:00'}]})
    schedule_day(detail)
    meal = next(s for s in detail.timeline_schedule if s['kind']=='meal')
    assert meal['start_time']=='12:00'
    assert any(s['kind']=='free_time' for s in detail.timeline_schedule)
    assert detail.timeline_schedule[-2]['kind'] == 'travel'  # leave shortly before the meal
    detail.day_start_time='18:00'
    schedule_day(detail)
    assert any('不在营业时段' in w for w in detail.meal_warnings)


def test_explicit_empty_meals_do_not_restore_defaults():
    pool = DiningPoolDay(main=[dict(name='M', category='main')])
    ctx = DraftDayContext(day_index=0, date='2026-10-14', attractions=[attraction('A')], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, {'meals':[]})
    schedule_day(detail)
    assert detail.meals==[]
    assert any('午餐未安排' in w for w in detail.meal_warnings)
    assert not compute_day_budget(detail).is_complete


@pytest.mark.parametrize('raw', [float('nan'),float('inf'),float('-inf'),True,False])
def test_invalid_numeric_ticket_prices_remain_unknown(raw):
    assert parse_ticket_price(raw) is None


def test_empty_overnight_day_still_reports_missing_lodging():
    day=DayDetail(day_index=0,date='2026-10-19',overnight_stay=True)
    budget=compute_day_budget(day)
    assert budget.total_hotels==0 and not budget.is_complete
    assert '2026-10-19 住宿未安排' in budget.unknown_cost_items
    assert combine_budgets([budget],1000).is_within_budget is None


def test_party_scaling_keeps_room_quote_separate_from_per_person_costs():
    from app.models.schemas import Meal
    from tests.services.test_hotel_quotes import parsed
    detail=DayDetail(day_index=0,date='2026-10-19',companion_count=2,hotel=parsed(),
        attractions=[attraction('A',price=20)],meals=[Meal(name='M',type='lunch',estimated_cost=30)])
    budget=compute_day_budget(detail)
    assert budget.total_hotels==123.45
    assert budget.total_attractions==40 and budget.total_meals==60
    assert budget.total_transportation==100 and budget.total==323.45


def test_departure_day_retains_hotel_position_without_new_night_charge():
    from tests.services.test_hotel_quotes import parsed
    ctx=DraftDayContext(day_index=2,date='2026-10-21',overnight_stay=False,hotel=parsed(),attractions=[attraction('A',price=0)])
    detail=rule_assemble_day_timeline(ctx,{'meals':[]});schedule_day(detail)
    assert detail.hotel is not None and detail.overnight_stay is False
    assert compute_day_budget(detail).total_hotels==0
    assert all(x['cost'] is None for x in detail.timeline_schedule if x['kind']=='hotel')
