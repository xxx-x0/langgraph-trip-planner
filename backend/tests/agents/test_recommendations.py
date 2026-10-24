"""Synthetic facts test ranking/provenance, not taste, actual traffic or adoption."""
from datetime import datetime, timezone, timedelta
from app.models.schemas import Attraction, DiningCandidate, TripRequest, CompanionInfo, DayDetail
from app.services.recommendations import explain_dining, dining_for_slot, meal_anchors, intent_for
from app.agents.langgraph_agent.nodes.search import _rank_day_hotels
from app.agents.langgraph_agent.assemble.narrative import refresh_day_description


def attrs():
    return [Attraction(name=n,address='',description='',visit_duration=120,location={'longitude':lon,'latitude':31.3}) for n,lon in [('园林',120.6),('博物馆',120.62),('湖边',120.8)]]


def candidate(name,lon,cost=50,rating=4.0,hours='10:00-22:00'):
    return DiningCandidate(name=name,category='main',avg_cost=cost,rating=rating,open_hours=hours,cuisine='苏帮菜',
        location={'longitude':lon,'latitude':31.3},recommendation={'queried_at':datetime.now(timezone.utc).isoformat()})


def test_lunch_and_dinner_use_different_activity_gaps():
    a=attrs(); anchors=meal_anchors(a,'08:00')
    assert anchors['lunch'][0].name=='博物馆' and anchors['dinner'][0].name=='湖边'
    choices=[candidate('午餐近',120.621),candidate('晚餐近',120.801)]
    explain_dining(choices,a,{},'08:00')
    assert dining_for_slot(choices,'lunch')[0].name=='午餐近'
    assert dining_for_slot(choices,'dinner')[0].name=='晚餐近'
    assert '非导航' in choices[0].recommendation['matches'][0]['route_basis']


def test_saved_schedule_overrides_estimated_anchor_and_records_next_activity():
    schedule=[{'kind':'attraction','ref_name':'园林'},{'kind':'meal','ref_name':'餐厅','start_minutes':720},{'kind':'attraction','ref_name':'湖边'}]
    a=attrs(); choices=[candidate('餐厅',120.601)]
    explain_dining(choices,a,{},schedule=schedule)
    m=choices[0].recommendation['matches'][0]
    assert (m['before'],m['after'])==('园林','湖边')
    assert m['extra_walk_minutes'] is not None


def test_budget_child_diet_restrictions_do_not_invent_certification():
    intent={'meal_budget_per_person':60,'companion_count':3,'children':True,'dietary_requirements':'花生过敏'}
    choices=[candidate('近但贵',120.62,200,5),candidate('便宜',120.625,40,3.5)]
    explain_dining(choices,attrs(),intent)
    assert dining_for_slot(choices,'lunch',intent)[0].name=='便宜'
    notes=' '.join(choices[1].recommendation['cautions'])
    assert '儿童' in notes and '花生过敏' in notes and '来源未证实' in notes and '评价量未提供' in notes
    assert any('3人约120元' in r for r in choices[1].recommendation['reasons'])


def test_stale_and_closed_candidates_are_traceable_and_sorted_last():
    closed=candidate('暂停营业餐厅',120.62);closed.recommendation['queried_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    choices=[closed,candidate('营业餐厅',120.625)]
    explain_dining(choices,attrs(),{})
    assert dining_for_slot(choices,'lunch')[0].name=='营业餐厅'
    assert closed.recommendation['matches'][0]['hours_fit'] is False
    assert any('24小时' in n for n in closed.recommendation['cautions'])


def test_hotel_location_precedes_stars():
    hotels=[{'name':'远处五星','star_rating':5,'_centroid_distance_km':40},{'name':'近处三星','star_rating':3,'_centroid_distance_km':1},{'name':'未知位置','star_rating':5}]
    assert [h['name'] for h in _rank_day_hotels(hotels)]==['近处三星','远处五星','未知位置']


def test_same_itinerary_expresses_only_explicit_current_intent():
    d=DayDetail(day_index=0,date='2026-10-20',attractions=attrs(),overnight_stay=False)
    base=refresh_day_description(d)
    d.trip_intent={'free_text_input':'想慢游'};slow=refresh_day_description(d)
    d.trip_intent={'companion_type':'elderly'};elderly=refresh_day_description(d)
    assert '慢慢逛' in slow and '长辈同行' in elderly
    assert '长辈同行' not in base and '慢慢逛' not in base
    assert '锁定' not in elderly and '重算' not in elderly
    from app.models.schemas import Meal
    d.meals=[Meal(name='本次选的餐厅',type='lunch')]
    d.trip_intent={'dining_style':'dedicated'}
    foodie=refresh_day_description(d)
    assert '美食作为重点' in foodie and '本次选的餐厅' in foodie
    assert d.meals[0].name=='本次选的餐厅'
    assert [a.name for a in d.attractions]==['园林','博物馆','湖边']


def test_manual_restaurant_and_gap_survive_ai_replacement():
    from app.agents.langgraph_agent.assemble.meals import normalize_ai_meals, saved_meals
    from app.models.schemas import DraftDayContext, DiningPoolDay, Meal
    ctx=DraftDayContext(day_index=0,date='2026-10-20',attractions=attrs(),dining_pool=DiningPoolDay(main=[candidate('另一家',120.621)]))
    day=DayDetail(day_index=0,date=ctx.date,attractions=attrs(),meals=[Meal(type='lunch',name='我选的店',schedule_mode='manual')],
                  timeline_order=[{'kind':'attraction','ref_name':'园林'},{'kind':'meal','ref_name':'我选的店'}])
    meals,_=normalize_ai_meals([{'name':'另一家','preferred_slot':'lunch'}],day,ctx,[a.name for a in attrs()])
    assert meals==saved_meals(day)


def test_weekday_exceptions_never_become_confirmed_open():
    from app.agents.langgraph_agent.assemble.schedule import opening_windows
    assert opening_windows('周一休息，周二至周日10:00-22:00')==[]
    assert opening_windows('周一至周日 10:00-22:00')==[(600,1320)]


def test_actual_next_meal_is_not_skipped_when_comparing_lunch_route():
    from app.models.schemas import Meal, Location
    a=attrs(); dinner=Meal(name='晚餐店',type='dinner',location=Location(longitude=120.7,latitude=31.3))
    lunch=Meal(name='午餐店',type='lunch')
    schedule=[{'kind':'attraction','ref_name':'园林'}, {'kind':'meal','ref_name':'午餐店','start_minutes':720}, {'kind':'meal','ref_name':'晚餐店','start_minutes':1080}]
    anchors=meal_anchors(a,schedule=schedule,meals=[lunch,dinner])
    assert anchors['lunch'][1].name=='晚餐店'
    assert anchors['dinner'][0].name=='午餐店'


def test_explicit_closure_is_a_violation_even_without_clock_windows():
    from app.models.schemas import Meal
    from app.agents.langgraph_agent.assemble.meals import meal_plan_violations
    day=DayDetail(day_index=0,date='2026-10-20',meals=[Meal(name='店',type='lunch',open_hours='暂停营业')],timeline_schedule=[{'kind':'meal','ref_name':'店','start_minutes':720,'end_minutes':780}])
    assert any('停止营业' in x for x in meal_plan_violations(day,day))


import pytest
from pydantic import ValidationError

def test_dietary_request_remains_unconfirmed_and_does_not_change_saved_choices():
    d=DayDetail(day_index=0,date='2026-10-20',attractions=attrs(),overnight_stay=False,
                trip_intent={'dietary_requirements':'花生过敏'})
    before=[a.model_dump() for a in d.attractions]
    refresh_day_description(d)
    assert any('花生过敏' in n and '尚未由店家确认' in n for n in d.pending_confirmations)
    assert [a.model_dump() for a in d.attractions]==before


@pytest.mark.parametrize('overrides',[{'meal_budget_per_person':0},{'meal_budget_per_person':10001},{'dietary_requirements':'x'*301},{'dining_style':'unknown'}])
def test_invalid_dining_request_is_rejected(overrides):
    with pytest.raises(ValidationError):
        TripRequest(city='苏州',start_date='2026-10-20',end_date='2026-10-20',travel_days=1,
                    transportation='步行',accommodation='酒店',**overrides)


@pytest.mark.parametrize('quote',[
 {'occupancy_confirmed':True,'status':'search_only'},
 {'occupancy_confirmed':True,'status':'failed'},
 {'occupancy_confirmed':True,'status':'detail_returned','unsupported_conditions':['儿童年龄不匹配']},
])
def test_hotel_explanation_does_not_call_request_occupancy_a_provider_confirmation(quote):
    from app.services.recommendations import explain_hotel
    request=TripRequest(city='苏州',start_date='2026-10-20',end_date='2026-10-21',travel_days=2,transportation='步行',accommodation='酒店')
    hotel=explain_hotel({'name':'原名（分店）','quote':quote},request)
    assert not any('已回显' in text for text in hotel['recommendation']['reasons'])
    assert any('未完整匹配' in text for text in hotel['recommendation']['cautions'])


def test_hotel_explanation_keeps_branch_and_quote_and_discloses_unknown_quality():
    from copy import deepcopy
    from app.services.recommendations import explain_hotel
    request=TripRequest(city='苏州',start_date='2026-10-20',end_date='2026-10-21',travel_days=2,transportation='步行',accommodation='酒店')
    raw={'name':'原名（分店）','quote':{'occupancy_confirmed':True,'status':'detail_returned','unsupported_conditions':[],'queried_at':'2026-10-19T10:00:00Z'},'_centroid_distance_km':7}
    original=deepcopy(raw)
    result=explain_hotel(raw,request)
    assert result['name']==original['name'] and result['quote']==original['quote']
    assert any('直线约7.0公里' in text for text in result['recommendation']['reasons'])
    assert any('距离游玩区域较远' in text for text in result['recommendation']['cautions'])
    assert any('未验证' in text for text in result['recommendation']['cautions'])


def test_hotel_explanation_without_location_does_not_claim_nearby():
    from app.services.recommendations import explain_hotel
    request=TripRequest(city='苏州',start_date='2026-10-20',end_date='2026-10-21',travel_days=2,transportation='步行',accommodation='酒店')
    result=explain_hotel({'name':'H'},request)
    assert any('缺少可核对的位置' in text for text in result['recommendation']['cautions'])
    assert not any('直线约' in text for text in result['recommendation']['reasons'])
