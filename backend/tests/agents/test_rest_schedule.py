from types import SimpleNamespace
import pytest
from app.models.schemas import DayDetail, Attraction, Meal, TripRequest, DraftDayContext
from app.models.rest import RestPeriod
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from app.agents.langgraph_agent.assemble.narrative import refresh_day_description
from app.services.journey_service import conflicts

def rest(start='14:00',end='17:00'):
    return RestPeriod(id='r',date='2026-10-22',start_time=start,end_time=end)

def day():
    return DayDetail(day_index=0,date='2026-10-22',day_start_time='10:00',rest_periods=[rest()],
        attractions=[Attraction(name=n,address='',description='',visit_duration=m,open_hours='08:00-22:00') for n,m in [('上午园林',60),('下午公园',90)]],
        meals=[Meal(name=n,type=t,preferred_slot=t,category='main',open_hours='10:00-22:00') for n,t in [('午饭','lunch'),('晚饭','dinner')]],
        locked_attraction_names=['下午公园'],removed_attraction_names=['已删除'],timeline_order=[dict(kind=k,ref_name=n) for k,n in [('attraction','上午园林'),('meal','午饭'),('attraction','下午公园'),('meal','晚饭')]])

def test_fixed_rest_preserves_visits_meals_locks_and_is_idempotent():
    d=day();order=d.timeline_order.copy();schedule_day(d)
    assert d.timeline_order==order and d.locked_attraction_names==['下午公园'] and d.removed_attraction_names==['已删除']
    assert [x['duration'] for x in d.timeline_schedule if x['kind']=='attraction']==[60,90]
    assert [m.type for m in d.meals]==['lunch','dinner'] and not conflicts(d)
    assert all(a['end_minutes']<=b['start_minutes'] for a,b in zip(d.timeline_schedule,d.timeline_schedule[1:]))
    assert '14:00—17:00' in refresh_day_description(d)
    before=d.model_dump();schedule_day(d);assert d.timeline_schedule==before['timeline_schedule']

def test_rest_uses_gap_without_delaying_dinner():
    d=day();d.rest_periods=[rest('15:00','16:00')];schedule_day(d)
    assert next(x for x in d.timeline_schedule if x['ref_name']=='晚饭')['start_time']=='17:30'

def test_empty_day_can_have_real_rest():
    d=DayDetail(day_index=0,date='2026-10-22',rest_periods=[rest()]);schedule_day(d)
    assert sum(x['duration'] for x in d.timeline_schedule if x['kind']=='rest')==180
    assert not d.meals and not conflicts(d) and '14:00—17:00' in refresh_day_description(d)
    assert any('午餐未安排' in w for w in d.meal_warnings)

@pytest.mark.parametrize('start,end,expected',[('11:00','16:00','正餐'),('14:00','23:30','次日'),('09:00','10:00','早于')])
def test_infeasible_rest_does_not_delete_activity(start,end,expected):
    d=day();d.rest_periods=[rest(start,end)];schedule_day(d)
    assert len(d.attractions)==2 and len(d.meals)==2 and any(expected in p for p in conflicts(d))

def test_closing_and_arrival_windows():
    d=day();d.attractions[1].open_hours='08:00-16:00';d.travel_window={'start_minutes':600,'end_minutes':1050};schedule_day(d)
    assert any('开放时间' in x for x in conflicts(d)) and any('晚饭' in x for x in conflicts(d))


def test_remove_rest_has_no_ghost_blocks():
    d=day();schedule_day(d);d.rest_periods=[];schedule_day(d)
    assert not any(x['kind']=='rest' for x in d.timeline_schedule)


def test_short_gaps_are_not_called_an_afternoon_to_fill():
    d=day();schedule_day(d);text=refresh_day_description(d)
    for item in d.timeline_schedule:
        if item['kind']=='free_time' and item['duration']<=60:
            assert item['start_time']+'至'+item['end_time']+'尚未安排' not in text
    assert '补充下午活动' not in text
