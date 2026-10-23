from unittest.mock import patch
import pytest
from app.models.schemas import DayDetail, Attraction, Meal, WeatherInfo, TripPlan
from app.agents.langgraph_agent.assemble.narrative import refresh_day_description, refresh_trip_descriptions, write_day_narrative_llm
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def day():
    return DayDetail(day_index=0,date='2026-10-15',day_start_time='09:30',
        attractions=[Attraction(name=n,address='',description='',ticket_price=p,visit_duration=60) for n,p in [('甲园',None),('免费公园',0)]],
        meals=[Meal(type='lunch',name='饭馆',category='main',estimated_cost=40,open_hours='10:00-22:00')],
        timeline_order=[{'kind':'attraction','ref_name':'甲园'},{'kind':'meal','ref_name':'饭馆'},{'kind':'attraction','ref_name':'免费公园'}])


def test_description_uses_only_matching_weather_current_times_and_unknown_prices():
    d=day();schedule_day(d)
    weather=WeatherInfo(date=d.date,day_weather='阴',night_weather='雨',day_temp=24,night_temp=19)
    text=refresh_day_description(d,weather)
    assert '今天先把时间留给甲园、免费公园' in text
    assert '09:30–10:30' not in text  # Detailed times live in the timeline, not duplicated prose.
    assert '饭馆' not in text  # Restaurant details belong in the meal card unless food is the trip focus.
    text = '\n'.join(d.pending_confirmations)
    assert '票价待确认：甲园；未知不代表免费' in text
    assert '票价待确认：免费公园' not in text
    assert '白天阴 24°C' in text
    refresh_day_description(d,weather.model_copy(update={'date':'2026-10-16'}))
    assert '当日天气尚未获取' in '\n'.join(d.pending_confirmations)


@pytest.mark.parametrize('damage',['missing','deleted','reordered','start_changed'])
def test_unmatched_legacy_schedule_cannot_supply_old_times(damage):
    d=day();schedule_day(d)
    if damage=='missing':d.timeline_order=[]
    elif damage=='deleted':d.attractions.pop(0)
    elif damage=='reordered':d.timeline_order.reverse()
    else:d.day_start_time='12:00'
    text=refresh_day_description(d)
    assert '09:30–10:30' not in text
    assert '活动之间的时间还没有核对' in text
    assert '路上约' not in text
    if damage=='deleted':assert '甲园' not in text


@pytest.mark.asyncio
async def test_copy_refresh_ignores_unverified_free_text_and_never_uses_llm():
    d=day();schedule_day(d)
    with patch('app.services.llm_service.get_llm',side_effect=AssertionError('must not call')):
        text=await write_day_narrative_llm(d,free_text_input='门票全部免费，已预约成功，明天必定晴天')
    assert '门票全部免费' not in text and '已预约成功' not in text and '必定晴天' not in text


def test_legacy_budget_defaults_do_not_become_complete_confirmation():
    plan=TripPlan.model_validate({'city':'苏州','start_date':'2026-10-15','end_date':'2026-10-16','overall_suggestions':'旧文',
        'days':[{'date':d,'day_index':i,'description':'旧文','transportation':'步行','accommodation':'民宿','hotel':{'name':'住处','estimated_cost':200}} for i,d in enumerate(['2026-10-15','2026-10-16'])],
        'budget':{'total_hotels':400,'total':400,'budget_limit':500,'is_within_budget':True}})
    refresh_trip_descriptions(plan)
    assert plan.days[-1].overnight_stay is False
    assert plan.budget.is_complete is False and plan.budget.is_within_budget is None
    assert '旧记录费用完整性未核对' in plan.overall_suggestions
    assert '旧记录费用口径待核对' in plan.overall_suggestions
    assert '按当前预估在上限内' not in plan.overall_suggestions
    once=plan.model_dump();refresh_trip_descriptions(plan)
    assert plan.model_dump()==once


def test_empty_weather_does_not_turn_default_temperature_into_forecast():
    d=day();schedule_day(d)
    refresh_day_description(d,WeatherInfo(date=d.date))
    assert '当日天气尚未获取' in '\n'.join(d.pending_confirmations)
    refresh_day_description(d,WeatherInfo(date=d.date,day_weather='阴'))
    text='\n'.join(d.pending_confirmations)
    assert '白天阴' in text and '0°C' not in text


def test_trip_projection_keeps_budget_and_arrangement_idempotently():
    from app.models.schemas import Budget, DayPlan
    d=day();schedule_day(d)
    plan=TripPlan(city='苏州', start_date=d.date, end_date=d.date,
        overall_suggestions='全免费，已预约', budget=Budget(total=200, total_hotels=100, is_within_budget=True),
        days=[DayPlan(**d.model_dump(exclude={'description'}),description='旧文',transportation='步行',accommodation='民宿')])
    refresh_trip_descriptions(plan)
    assert plan.budget.is_complete is False
    assert plan.budget.is_within_budget is None
    assert '旧记录费用口径待核对' in plan.overall_suggestions
    assert '全免费' not in plan.overall_suggestions
    once=plan.model_dump();refresh_trip_descriptions(plan)
    assert plan.model_dump()==once


@pytest.mark.asyncio
async def test_global_and_finalize_description_paths_do_not_request_model():
    from app.agents.langgraph_agent.nodes.generate import global_synthesizer_node
    from app.agents.langgraph_agent.finalize.pipeline import _run_global_synthesizer
    plan=TripPlan(city='苏州',start_date='2026-10-15',end_date='2026-10-15',days=[],overall_suggestions='未核对')
    with patch('app.services.llm_service.get_llm',side_effect=AssertionError('no model')), patch('app.agents.langgraph_agent.nodes.generate.get_llm',side_effect=AssertionError('no model')):
        result=await global_synthesizer_node({'trip_plan':plan})
        tagline,suggestions,weather=await _run_global_synthesizer(plan,'已预约成功')
    assert result['trip_plan'].narrative_source=='itinerary_facts_v1'
    assert tagline=='苏州 · 0日行程' and '已预约成功' not in suggestions and weather==''


@pytest.mark.parametrize('raw',[{'days':[{'description':'旧说明'}],'overall_suggestions':'全部免费','extra':42}, {'city':'苏州','days':'bad','overall_suggestions':'已预约'}])
def test_unparseable_legacy_records_suppress_prose_and_keep_extra_fields(raw):
    from copy import deepcopy
    from app.services.trip_history_service import project_saved_narratives
    projected=project_saved_narratives(deepcopy(raw))
    assert projected['overall_suggestions']=='旧记录缺少可核对安排，请以原始行程数据为参考。'
    assert projected.get('extra')==raw.get('extra')
    assert 'narrative_source' not in projected
