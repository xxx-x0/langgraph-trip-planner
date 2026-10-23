"""Meal intent and anchor rules; route timings here are explicitly synthetic."""
from copy import deepcopy
import pytest
from app.models.schemas import Attraction, DayDetail, DraftDayContext, Meal, DiningPoolDay, DiningCandidate
from app.agents.langgraph_agent.assemble.meals import repair_deleted_anchors, normalize_ai_meals, meal_plan_violations, saved_meals
from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.agents.langgraph_agent.assemble.schedule import schedule_day


def context():
    return DraftDayContext(day_index=0,date='2026-10-15',attractions=[Attraction(name=n,address='',description='',visit_duration=60) for n in 'ABC'],
        dining_pool=DiningPoolDay(main=[DiningCandidate(name=n,category='main',avg_cost=c,open_hours='07:00-23:00',source='nearby') for n,c in [('Lunch',20),('Dinner',30),('Other',40)]],
                                  cafe=[DiningCandidate(name='Coffee',category='cafe',avg_cost=10,open_hours='08:00-20:00',source='popular')]),day_start_time='08:00')


def saved():
    c=context()
    d=rule_assemble_day_timeline(c,{'meals':[
        {'name':'Lunch','type':'lunch','category':'main','avg_cost':20,'insert_after':'A','open_hours':'07:00-23:00'},
        {'name':'Dinner','type':'dinner','category':'main','avg_cost':30,'insert_after':'C','open_hours':'07:00-23:00'}]})
    schedule_day(d);return d


@pytest.mark.parametrize('remaining,lunch_anchor,dinner_anchor',[
    ('BC','hotel_start','C'),('AB','A','B'),('AC','A','C'),('B','hotel_start','B'),('A','A','A'),('C','hotel_start','C'),('','hotel_start','hotel_start')])
def test_deleted_first_last_consecutive_or_all_keeps_original_gaps(remaining,lunch_anchor,dinner_anchor):
    d=saved();raw=saved_meals(d);before=deepcopy(raw)
    repaired,notes=repair_deleted_anchors(raw,d,list(remaining))
    assert [m['insert_after'] for m in repaired]==[lunch_anchor,dinner_anchor]
    assert raw==before
    assembled=rule_assemble_day_timeline(context(),{'attractions_order':list(remaining),'removed_attraction_names':[n for n in 'ABC' if n not in remaining],'meals':repaired,'meal_adjustments':notes})
    schedule_day(assembled)
    assert [m.type for m in assembled.meals]==['lunch','dinner']
    assert not meal_plan_violations(assembled,d)


def test_collapsed_gaps_keep_original_meal_order_and_hotel_anchors():
    d=saved()
    reversed_meals=list(reversed(saved_meals(d)))
    repaired,_=repair_deleted_anchors(reversed_meals,d,[])
    assert [m['name'] for m in repaired]==['Lunch','Dinner']
    explicit=[{**reversed_meals[0],'insert_after':'hotel_end'},{**reversed_meals[1],'insert_after':'hotel_start'}]
    assert repair_deleted_anchors(explicit,d,[])[0]==explicit


def test_auto_meal_remains_auto_and_uses_its_slot_after_deletion():
    d=saved();raw=saved_meals(d);raw[0].update(schedule_mode='auto',preferred_slot='lunch')
    repaired,notes=repair_deleted_anchors(raw,d,['B','C'])
    assert repaired[0]['schedule_mode']=='auto'
    assembled=rule_assemble_day_timeline(context(),{'removed_attraction_names':['A'],'meals':repaired})
    assert all(i['ref_name']!='A' for i in assembled.timeline_order)
    assert any('按原餐次' in x for x in notes)


@pytest.mark.parametrize('proposal',[[],None,[{'name':'Lunch','category':'main'}],[{'name':'Unknown','category':'main'}],[{'name':'Coffee','category':'main','type':'dinner'}]])
def test_missing_main_slots_preserve_saved_restaurants_and_optional_is_not_a_main(proposal):
    d=saved();meals,notes=normalize_ai_meals(proposal,d,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals});schedule_day(detail)
    assert not meal_plan_violations(detail,d)
    assert {'Lunch','Dinner'} <= {m.name for m in detail.meals}
    assert any('已保留' in note for note in notes)
    if proposal and proposal[0]['name']=='Coffee':assert next(m for m in detail.meals if m.name=='Coffee').type=='cafe'


def test_duplicates_and_fabricated_fields_cannot_replace_candidate_facts():
    current = saved()
    for m in current.meals: m.schedule_mode = "auto"
    meals,notes=normalize_ai_meals([
        {'name':'Other','preferred_slot':'lunch','estimated_cost':999,'location':{'longitude':0},'source':'fake','open_hours':'24小时'},
        {'name':'Other','preferred_slot':'dinner'},
        {'name':'Unknown','preferred_slot':'dinner'}],current,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals});schedule_day(detail)
    other=next(m for m in detail.meals if m.name=='Other')
    assert other.avg_cost==other.estimated_cost==40 and other.location is None
    assert other.source=='nearby' and other.open_hours=='07:00-23:00'
    assert len({m.name for m in detail.meals})==len(detail.meals)
    assert any('重复' in x for x in notes) and any('可用列表' in x for x in notes)
    assert not meal_plan_violations(detail,saved())


@pytest.mark.parametrize('keep_dinner',[False,True])
def test_explicitly_missing_main_slots_are_not_automatically_recreated(keep_dinner):
    d=saved();d.meals=[m for m in d.meals if keep_dinner and m.type=='dinner']
    d.timeline_order=[i for i in d.timeline_order if i['kind']!='meal' or i['ref_name']=='Dinner' and keep_dinner]
    meals,_=normalize_ai_meals([{'name':'Lunch','preferred_slot':'lunch'},{'name':'Dinner','preferred_slot':'dinner'},{'name':'Other','preferred_slot':'breakfast'}],d,context(),list('ABC'))
    assert [m['name'] for m in meals]==(['Dinner'] if keep_dinner else [])


def test_saved_custom_main_outside_pool_retains_factual_fields():
    d=saved();d.meals[1]=Meal(name='Custom',type='dinner',category='main',estimated_cost=55,source='user_custom',open_hours='16:00-23:00')
    d.timeline_order=[{**i,'ref_name':'Custom'} if i['ref_name']=='Dinner' else i for i in d.timeline_order]
    meals,_=normalize_ai_meals([],d,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals});schedule_day(detail)
    custom=next(m for m in detail.meals if m.name=='Custom')
    assert custom.estimated_cost==55 and custom.source=='user_custom' and custom.open_hours=='16:00-23:00'
    assert not meal_plan_violations(detail,d)


def test_actual_clock_and_opening_window_can_reject_a_nominal_dinner():
    d=saved();bad=d.model_copy(deep=True)
    bad.meals[1].open_hours='08:00-12:00'
    schedule_day(bad)
    assert any('营业时段' in x for x in meal_plan_violations(bad,d))
    bad=d.model_copy(deep=True);bad.day_start_time='16:00';schedule_day(bad)
    assert any('午餐未能保留' in x for x in meal_plan_violations(bad,d))


def test_saved_explicit_zero_cost_and_custom_details_survive_omission_recovery():
    d=saved();d.meals[1]=Meal(name='Custom',type='dinner',category='main',avg_cost=0,estimated_cost=0,description='用户确认的用餐说明',source='user_custom',open_hours='16:00-23:00')
    d.timeline_order=[{**i,'ref_name':'Custom'} if i['ref_name']=='Dinner' else i for i in d.timeline_order]
    meals,_=normalize_ai_meals([],d,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals})
    custom=next(m for m in detail.meals if m.name=='Custom')
    assert custom.estimated_cost==custom.avg_cost==0
    assert custom.description=='用户确认的用餐说明' and custom.source=='user_custom'


def test_saved_unknown_source_is_not_relabeled_as_user_confirmed():
    d=saved();d.meals[1].source=None
    meals,_=normalize_ai_meals([],d,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals})
    assert next(m for m in detail.meals if m.name=='Dinner').source is None


def test_valid_ai_position_is_kept_and_only_missing_positions_use_slot_recovery():
    current = saved()
    for m in current.meals: m.schedule_mode = 'auto'
    meals,_=normalize_ai_meals([{'name':'Lunch','preferred_slot':'lunch','insert_after':'hotel_start'}],current,context(),list('ABC'))
    detail=rule_assemble_day_timeline(context(),{'meals':meals});schedule_day(detail)
    assert detail.timeline_order[0]['ref_name']=='Lunch'
    assert next(m for m in detail.meals if m.name=='Lunch').schedule_mode=='manual'
    assert next(m for m in detail.meals if m.name=='Dinner').schedule_mode=='auto'
    assert not meal_plan_violations(detail,saved())
