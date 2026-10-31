import copy
import json
from pathlib import Path

import pytest
import pytest_asyncio

from app.models.schemas import DayDetail,RouteSegment
from app.services.day_route_context import build_route_context
from app.services.day_route_optimizer import choose_route_plan,complete_comparison,route_total,result_basis
from app.agents.langgraph_agent.assemble.schedule import schedule_day
from app.agents.langgraph_agent.assemble.narrative import refresh_day_description
from app.services.place_hours import place_hours_report


@pytest_asyncio.fixture
async def sample():
    root=Path(__file__).parents[2]/'evals/datasets'
    day=DayDetail.model_validate(json.loads((root/'inputs/R10.json').read_text())['day_detail'])
    matrix={(e['from'],e['to']):e for e in json.loads((root/'routes/R10.json').read_text())['edges']}
    async def lookup(probe,*args):
        a,b=[r['ref_name'] for r in probe.timeline_order];e=matrix[a,b]
        return [RouteSegment(from_name=a,to_name=b,duration=f"{e['duration_minutes']}分钟",mode=e['mode'],is_estimated=False)]
    context=await build_route_context(day,'苏州','公共交通',lookup,enrich=True)
    return day,context


@pytest.mark.asyncio
async def test_search_uses_facts_and_preserves_protected_content(sample):
    base,context=sample;before=base.model_dump(mode='json')
    selected,info=choose_route_plan(base,base.model_copy(deep=True),context)
    assert route_total(selected)==138 and not place_hours_report(selected)['violations']
    assert [a.name for a in selected.attractions]==['七里山塘景区','留园','虎丘山风景区']
    assert {a.name:a.visit_duration for a in selected.attractions}=={a.name:a.visit_duration for a in base.attractions}
    assert base.model_dump(mode='json')==before
    final=complete_comparison(selected,base,info)
    assert final.route_comparison['status']=='improved' and final.route_comparison['delta_minutes']==42
    assert final.route_comparison['end_minutes']==1218
    refresh_day_description(final)
    assert '减少42分钟' in final.description and '20:18结束' in final.description
    assert '不保证全局最优' in final.route_comparison['limitations'][0]


@pytest.mark.asyncio
async def test_missing_edges_and_bound_do_not_invent_an_improvement(sample):
    base,context=sample
    context['directed_edges']=[e for e in context['directed_edges'] if e['source']=='saved_not_requeried']
    selected,info=choose_route_plan(base,base.model_copy(deep=True),context)
    assert route_total(selected)==180 and info['missing_edges']>0
    final=complete_comparison(selected,base,info)
    assert final.route_comparison['status']=='unchanged' and final.route_comparison['delta_minutes']==0
    _,info=choose_route_plan(base,base.model_copy(deep=True),context,max_candidates=1)
    assert info['search_truncated'] and info['examined']==1


@pytest.mark.asyncio
async def test_real_route_regression_or_estimate_preserves_old_arrangement(sample):
    base,context=sample
    for estimated in [False,True]:
        selected,info=choose_route_plan(base,base.model_copy(deep=True),context)
        for route in selected.route_segments:
            route.duration='100分钟';route.is_estimated=estimated
        schedule_day(selected,suggest=False)
        final=complete_comparison(selected,base,info)
        assert final.timeline_order==base.timeline_order and final.route_segments==base.route_segments
        assert final.route_comparison['status']==('not_comparable' if estimated else 'unchanged')


@pytest.mark.asyncio
async def test_manual_anchors_fixed_times_and_explicit_keep_order_are_protected(sample):
    base,context=sample
    for meal in base.meals:meal.schedule_mode='manual'
    selected,info=choose_route_plan(base,base.model_copy(deep=True),context,keep_order=True)
    assert selected.timeline_order==base.timeline_order and route_total(selected)==180
    # A fixed actual time makes the otherwise shorter permutation ineligible.
    from app.models.schemas import DayTimeConstraints,FixedActivityTime
    base.time_constraints=DayTimeConstraints(appointments=[FixedActivityTime(ref_name='虎丘山风景区',start_time='10:48')])
    selected,info=choose_route_plan(base,base.model_copy(deep=True),context)
    assert selected.attractions[0].name=='虎丘山风景区'


@pytest.mark.asyncio
async def test_changed_saved_facts_suppress_stale_result_explanation(sample):
    base,context=sample;selected,info=choose_route_plan(base,base.model_copy(deep=True),context)
    day=complete_comparison(selected,base,info);assert result_basis(day)==day.route_comparison['result_basis_sha256']
    day.route_segments[0].duration='99分钟';schedule_day(day,suggest=False);refresh_day_description(day)
    assert day.route_comparison=={} and '减少42分钟' not in day.description


@pytest.mark.asyncio
async def test_missing_old_routes_keeps_new_verified_routes_without_claiming_gain(sample):
    base,context=sample;verified=base.model_copy(deep=True);base.route_segments=[]
    _,info=choose_route_plan(base,base.model_copy(deep=True),context)
    schedule_day(verified,suggest=False)
    final=complete_comparison(verified,base,info)
    assert route_total(final)==180 and final.route_comparison['status']=='not_comparable'
    assert final.route_comparison['baseline_minutes'] is None and final.route_comparison['delta_minutes']==0
    refresh_day_description(final);assert '缺少可比较的已存路线' in final.description


@pytest.mark.asyncio
async def test_rejected_model_facts_do_not_mask_same_order_from_saved_sources(sample):
    base,context=sample;best,_=choose_route_plan(base,base.model_copy(deep=True),context)
    best.meals[0].recommendation={'test_only':'different source metadata'}
    selected,info=choose_route_plan(base,best,context)
    assert route_total(selected)==138
    assert selected.meals[0].recommendation==base.meals[0].recommendation
