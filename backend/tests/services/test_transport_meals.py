"""Synthetic providers/routes, independent from the live Wenzhou evidence."""
from unittest.mock import AsyncMock

import pytest

from app.models.schemas import Attraction, DayDetail, Meal, RouteSegment, TripRequest
from app.services import meal_recovery as recovery
from app.services.single_journey_adjustment import violations
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def candidate(name='顺路餐厅', **extra):
    return dict(name=name, category='main', poi_id=name, location={'longitude':120.01,'latitude':30},
                avg_cost=45, open_hours='10:00-22:00', source='nearby', **extra)


def day():
    value = DayDetail(day_index=0,date='2026-11-08',day_start_time='16:00',is_assembled=True,
        overnight_stay=False,travel_window={'start_minutes':960,'end_minutes':1320},
        attractions=[Attraction(name=n,address='测试地址',description='测试',visit_duration=60,
                               location={'longitude':120+i*.01,'latitude':30},open_hours='08:00-22:00') for i,n in enumerate(['公园','老街'])],
        locked_attraction_names=['公园'],removed_attraction_names=['已删除景点'],
        timeline_order=[{'kind':'attraction','ref_name':n} for n in ['公园','老街']],
        route_segments=[RouteSegment(from_name='公园',to_name='老街',duration='10分钟')])
    schedule_day(value)
    return value


def request():
    return TripRequest(city='温州',start_date='2026-11-08',end_date='2026-11-08',travel_days=1,
                       transportation='步行',accommodation='酒店',meal_budget_per_person=50)


async def rebuild(value):
    value.route_segments=[RouteSegment(from_name=a['ref_name'],to_name=b['ref_name'],duration='10分钟')
        for a,b in zip(value.timeline_order,value.timeline_order[1:])]
    schedule_day(value)


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(return_value={'main':[candidate()]}))
    monkeypatch.setattr(recovery,'get_llm',lambda:object())
    monkeypatch.setattr(recovery,'invoke_structured_or_json',AsyncMock(return_value=recovery.MealRanking(option_ids=['0'])))


@pytest.mark.asyncio
async def test_recovery_uses_current_gap_and_preserves_visits_locks_deleted_and_source():
    current=day();before=current.model_dump()
    result,pool,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert current.model_dump()==before
    assert result.attractions==current.attractions
    assert result.locked_attraction_names==['公园'] and result.removed_attraction_names==['已删除景点']
    assert note['status']=='scheduled' and note['selection_method']=='ai'
    assert result.meals[0].poi_id=='顺路餐厅' and result.meals[0].avg_cost==45
    assert pool['main'][0]['location']==candidate()['location']
    assert not violations(result,result)
    meal=next(r for r in result.timeline_schedule if r['kind']=='meal')
    assert meal['duration']==60 and meal['start_minutes']>=1050
    call=recovery.search_dining_for_day.call_args
    assert call.kwargs['main_only'] and tuple(call.kwargs['anchors_override'])==('dinner',)
    assert call.kwargs['anchors_override']['dinner'][0].name in ['公园','老街']


@pytest.mark.asyncio
@pytest.mark.parametrize('response',[{'option_ids':['made-up']},{'option_ids':['0','0']},TimeoutError()])
async def test_invalid_or_failed_ai_uses_real_candidates_only(monkeypatch,response):
    mock=AsyncMock(side_effect=response) if isinstance(response,Exception) else AsyncMock(return_value=recovery.MealRanking(**response))
    monkeypatch.setattr(recovery,'invoke_structured_or_json',mock)
    result,_,note=await recovery.recover_slot(day(),'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert note['selection_method']=='rules' and note['status']=='scheduled'
    assert [m.name for m in result.meals]==['顺路餐厅']


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'avg_cost':51},{'avg_cost':None},{'location':None},{'open_hours':'08:00-16:00'},{'name':'永久关闭餐厅'}])
async def test_hard_price_location_and_opening_filters_precede_ai(monkeypatch,change):
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(return_value={'main':[candidate()|change]}))
    current=day()
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert result==current and note['status']=='unavailable'
    recovery.invoke_structured_or_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_route_conflict_never_saves_optimistic_trial():
    async def slow(value):
        value.route_segments=[RouteSegment(from_name=a['ref_name'],to_name=b['ref_name'],duration='120分钟')
            for a,b in zip(value.timeline_order,value.timeline_order[1:])]
        schedule_day(value)
    current=day()
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=slow,validate=violations)
    assert result==current and note['status']=='unavailable'
    assert '已核对候选餐厅路线' in note['reason']


@pytest.mark.asyncio
async def test_provider_failure_keeps_day_and_falls_back_only_to_stored_facts(monkeypatch):
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(side_effect=TimeoutError()))
    current=day()
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{'main':[candidate()]},rebuild=rebuild,validate=violations)
    assert note['status']=='scheduled' and result.meals[0].name=='顺路餐厅'
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert result==current and note['status']=='unavailable' and '查询暂未成功' in note['reason']


@pytest.mark.asyncio
async def test_no_time_does_not_query_or_truncate_visits():
    current=day();current.travel_window['end_minutes']=1100
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert result==current and note['status']=='unavailable' and '完整的60分钟' in note['reason']
    recovery.search_dining_for_day.assert_not_awaited()


@pytest.mark.asyncio
async def test_preserves_manual_restaurant_and_fixed_time():
    current=day();current.day_start_time='12:00';current.travel_window['start_minutes']=720
    current.meals=[Meal(name='手选午餐',type='lunch',preferred_slot='lunch',schedule_mode='manual',open_hours='10:00-22:00',
        location={'longitude':120,'latitude':30},avg_cost=42)]
    current.timeline_order.insert(0,{'kind':'meal','ref_name':'手选午餐'})
    from app.models.schemas import DayTimeConstraints
    current.time_constraints=DayTimeConstraints(appointments=[{'kind':'meal','ref_name':'手选午餐','start_time':'12:00'}])
    await rebuild(current)
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert note['status']=='scheduled'
    assert result.meals[0]==current.meals[0] and result.time_constraints==current.time_constraints
    assert result.timeline_order[0]=={'kind':'meal','ref_name':'手选午餐'}
    assert next(r for r in result.timeline_schedule if r['ref_name']=='手选午餐')['start_time']=='12:00'


@pytest.mark.asyncio
async def test_verified_meal_gap_survives_recompute_without_becoming_manual(monkeypatch):
    from app.models.schemas import DraftDayContext
    from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
    from app.agents.langgraph_agent.assemble.meals import saved_meals
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(return_value={'main':[candidate()|{'location':{'longitude':120,'latitude':30}}]}))
    result,_,note=await recovery.recover_slot(day(),'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert note['status']=='scheduled'
    assert [e['ref_name'] for e in result.timeline_order]==['公园','顺路餐厅','老街']
    ctx=DraftDayContext(day_index=0,date=result.date,day_start_time=result.day_start_time,
        attractions=result.attractions,travel_window=result.travel_window,overnight_stay=False)
    rebuilt=rule_assemble_day_timeline(ctx,{'meals':saved_meals(result)})
    assert rebuilt.timeline_order==result.timeline_order
    assert rebuilt.meals[0].schedule_mode=='auto'
    await rebuild(rebuilt)
    assert rebuilt.timeline_schedule==result.timeline_schedule


@pytest.mark.asyncio
async def test_departure_dinner_tries_after_hotel_and_keeps_that_gap_on_recompute(monkeypatch):
    from app.models.schemas import Hotel, DraftDayContext
    from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
    from app.agents.langgraph_agent.assemble.meals import saved_meals
    current=day();current.day_start_time='14:00'
    current.travel_window={'start_minutes':840,'end_minutes':1113,'intercity_cost':0}
    current.hotel=Hotel(name='取行李酒店',location={'longitude':120.01,'latitude':30})
    current.timeline_order.append({'kind':'hotel','ref_name':current.hotel.name,'phase':'end'})
    current.timeline_order.insert(0,{'kind':'hotel','ref_name':current.hotel.name,'phase':'start'})
    await rebuild(current)
    choices=[candidate(str(i)) for i in range(8)]
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(return_value={'main':choices}))
    # Prefer all before-hotel candidates; a failed real route still tries another gap.
    async def rank(options,*args):
        return sorted(options,key=lambda o:o['gap']['index']),set()
    monkeypatch.setattr(recovery,'rank_options',rank)
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{},rebuild=rebuild,validate=violations)
    assert note['status']=='scheduled'
    assert result.timeline_order[-1]['kind']=='meal' and result.timeline_order[-2]['kind']=='hotel'
    assert result.timeline_schedule[-1]['end_time']=='18:30'
    match=next(m for m in result.meals[-1].recommendation['matches'] if m['slot']=='dinner')
    assert match['before']=='取行李酒店' and match['after'] is None
    ctx=DraftDayContext(day_index=0,date=result.date,day_start_time=result.day_start_time,attractions=result.attractions,
        hotel=result.hotel,travel_window=result.travel_window,overnight_stay=False)
    again=rule_assemble_day_timeline(ctx,{'meals':saved_meals(result)})
    assert again.timeline_order==result.timeline_order


@pytest.mark.asyncio
async def test_displaced_restaurant_can_be_reused_at_a_new_valid_gap(monkeypatch):
    monkeypatch.setattr(recovery,'search_dining_for_day',AsyncMock(return_value={'main':[]}))
    current=day()
    result,_,note=await recovery.recover_slot(current,'dinner',request(),{'main':[candidate()]},
        rebuild=rebuild,validate=violations,old_restaurant='顺路餐厅')
    assert note['status']=='scheduled' and note['restaurant']=='顺路餐厅'
    assert result.meals[0].preferred_slot=='dinner' and not violations(result,result)
