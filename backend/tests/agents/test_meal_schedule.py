"""Meal-clock extraction tests; hotel quotes, journey constraints and budget rules are excluded."""
import pytest
from app.models.schemas import Attraction, Hotel, DayDetail, DiningPoolDay, DraftDayContext
from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.agents.langgraph_agent.assemble.schedule import schedule_day, route_minutes, opening_windows
from app.agents.langgraph_agent.assemble.meals import meal_plan_violations


def attraction(name, minutes=90):
    return Attraction(name=name, address='', description='', visit_duration=minutes, ticket_price=0)


@pytest.mark.parametrize('raw,expected', [('1小时20分钟', 80), ('2小时', 120), ('5分钟', 5), ('未知', 20)])
def test_route_time_units_do_not_move_meals_an_hour_early(raw, expected):
    assert route_minutes(raw) == expected


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


@pytest.mark.parametrize("text,expected", [
    ("11:00-14:00 17:00-22:00", [(660,840),(1020,1320)]),
    ("22:00-02:00", [(1320,1560)]), ("全天营业", [(0,1440)]),
    ("周一至周日 11:00-22:00", [(660,1320)]),
    ("周六 11:00-22:00", []), ("节假日另行通知", []), (None, []),
])
def test_known_simple_windows_and_date_dependent_unknowns(text, expected):
    assert opening_windows(text) == expected


@pytest.mark.parametrize("hours", [None, "周六 11:00-22:00"])
def test_unknown_hours_are_visible_and_not_treated_as_known_closed(hours):
    ctx = DraftDayContext(day_index=0,date='2026-10-15',day_start_time='10:00',attractions=[attraction('A',60)])
    detail = rule_assemble_day_timeline(ctx, {'meals':[{'name':'Lunch','category':'main','type':'lunch','insert_after':'A','open_hours':hours}]})
    before = detail.model_copy(deep=True)
    schedule_day(detail)
    assert any('未知' in w or '人工确认' in w for w in detail.meal_warnings)
    assert meal_plan_violations(detail, before) == []


def test_default_candidate_zero_price_and_unverified_hotel_are_preserved():
    ctx = DraftDayContext(day_index=0,date='2026-10-15',day_start_time='10:00',attractions=[attraction('A',60)],
        hotel=Hotel(name='H',estimated_cost=123), dining_pool=DiningPoolDay(main=[{'name':'M','category':'main','avg_cost':0,'open_hours':'11:00-23:00'}]))
    detail = rule_assemble_day_timeline(ctx)
    assert len(detail.meals) == 1 and detail.meals[0].estimated_cost == 0
    assert detail.meals[0].schedule_mode == 'auto' and detail.meals[0].preferred_slot == 'lunch'
    schedule_day(detail)
    hotel = next(x for x in detail.timeline_schedule if x['kind']=='hotel')
    assert hotel['duration'] == 30 and hotel['cost'] is None
