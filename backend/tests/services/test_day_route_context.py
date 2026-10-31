"""Route input uses frozen provider facts, never references or generated estimates."""
import asyncio
import copy
from itertools import combinations,permutations
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.models.schemas import DayDetail,RouteSegment
from app.services.day_route_context import build_route_context,known_minutes,wants_route_facts,keeps_attraction_order,MAX_LOOKUPS
from tests.api.test_narrative_consistency import case


def fixture():
    root=Path(__file__).parents[2]/'evals/datasets'
    inputs=json.loads((root/'inputs/R10.json').read_text())
    routes=json.loads((root/'routes/R10.json').read_text())
    return DayDetail.model_validate(inputs['day_detail']),routes


@pytest.mark.parametrize('text,expected',[('20分钟',20),('1小时5分钟',65),('未知',None),('',None),('-5分钟',None)])
def test_unknown_durations_never_get_default_twenty_minutes(text,expected):
    assert known_minutes(text)==expected


@pytest.mark.parametrize('hint',['不要求少绕路','不需要减少交通时间','无需优化路线','不用减少路程','不要少走回头路'])
def test_negative_route_intent_does_not_activate_search(hint):
    assert not wants_route_facts(hint)


@pytest.mark.parametrize('hint',['不改变景点顺序，只减少交通','保持现有顺序，减少交通','景点顺序不变，希望少绕路'])
def test_explicit_saved_order_is_not_overridden(hint):
    assert wants_route_facts(hint) and keeps_attraction_order(hint)


@pytest.mark.asyncio
async def test_saved_facts_only_for_ordinary_hint_and_unknown_is_not_reverse():
    detail,_=fixture();before=detail.model_dump(mode='json');lookup=AsyncMock()
    result=await build_route_context(detail,'苏州','公共交通',lookup)
    assert len(result['directed_edges'])==6 and result['lookup_count']==0
    assert len(result['unknown_edges'])==24 and result['coverage']=='partial'
    assert all(e['source']=='saved_not_requeried' for e in result['directed_edges'])
    lookup.assert_not_called();assert detail.model_dump(mode='json')==before
    assert wants_route_facts('希望少绕路') and not wants_route_facts('不要优化路线')


@pytest.mark.asyncio
async def test_R10_input_covers_declared_interleavings_from_frozen_tools_without_gold():
    detail,routes=fixture();before=detail.model_dump(mode='json')
    matrix={(e['from'],e['to']):e for e in routes['edges']};called=[]
    async def lookup(probe,*args):
        pair=tuple(e['ref_name'] for e in probe.timeline_order);called.append(pair)
        edge=matrix.get(pair)
        if edge is None:raise ConnectionError('frozen directed edge unavailable')
        return [RouteSegment(from_name=pair[0],to_name=pair[1],duration=f"{edge['duration_minutes']}分钟",mode=edge['mode'],is_estimated=False)]
    result=await build_route_context(detail,'苏州','公共交通',lookup,enrich=True)
    assert result['lookup_count']==len(called)==MAX_LOOKUPS
    assert len(result['directed_edges'])==23 and len(result['unknown_edges'])==7
    assert result['coverage']=='partial' and detail.model_dump(mode='json')==before
    facts={(e['from_name'],e['to_name']):e['duration_minutes'] for e in result['directed_edges']}
    hotel=detail.hotel.name;attrs=[a.name for a in detail.attractions];lunch,dinner=[m.name for m in detail.meals]
    totals=[]
    for order in permutations(attrs):
        if any(order.index(n)!=attrs.index(n) for n in detail.locked_attraction_names):continue
        for positions in combinations(range(5),2):
            itinerary=iter(order);seq=[hotel]+[lunch if i==positions[0] else dinner if i==positions[1] else next(itinerary) for i in range(5)]+[hotel]
            totals.append(sum(facts[a,b] for a,b in zip(seq,seq[1:])))
    # These are edge totals only. The 120-minute combination can violate meal/opening
    # windows; no minimum here is presented as a feasible or adopted itinerary.
    assert len(totals)==20 and min(totals)<180 and 138 in totals and 162 in totals


@pytest.mark.asyncio
async def test_estimated_or_mismatched_edges_stay_unknown():
    detail,_=fixture()
    async def lookup(probe,*args):
        a,b=[e['ref_name'] for e in probe.timeline_order]
        return [RouteSegment(from_name=a,to_name=b,duration='1分钟',mode='直线',is_estimated=True)]
    result=await build_route_context(detail,'苏州','公共交通',lookup,enrich=True,max_lookups=2)
    assert len(result['directed_edges'])==6 and result['lookup_count']==2
    assert sum(e['reason']=='no_verified_directed_edge' for e in result['unknown_edges'])==2


@pytest.mark.asyncio
async def test_timeout_and_cancellation_drain_lookup_children():
    detail,_=fixture();active=0;finished=0
    async def slow(*args):
        nonlocal active,finished
        active+=1
        try:await asyncio.Event().wait()
        finally:active-=1;finished+=1
    result=await build_route_context(detail,'苏州','公共交通',slow,enrich=True,budget_seconds=.02)
    assert active==0 and finished<=3 and result['coverage']=='partial'
    task=asyncio.create_task(build_route_context(detail,'苏州','公共交通',slow,enrich=True))
    await asyncio.sleep(.01);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert active==0


@pytest.mark.asyncio
async def test_change_during_enrichment_is_rejected_before_model(case,monkeypatch):
    from app.api.routes import trip_draft
    client,draft,url=case;entered=asyncio.Event();resume=asyncio.Event()
    async def paused(*args,**kwargs):
        entered.set();await resume.wait()
        return dict(directed_edges=[],unknown_edges=[],lookup_count=1,coverage='partial')
    monkeypatch.setattr(trip_draft,'build_route_context',paused)
    model=AsyncMock();monkeypatch.setattr(trip_draft,'_invoke_llm_with_retry',model)
    task=asyncio.create_task(client.post(url+'/ai-rearrange',json={'hint':'少绕路'}))
    await asyncio.wait_for(entered.wait(),2)
    result=await client.post(url+'/recompute',json={'day_start_time':'10:15'})
    assert result.status_code==200,result.text
    saved=(await client.get('/api/trip/draft/'+draft)).json()['days_detail'][0]
    resume.set();response=await task
    assert response.status_code==409 and '未调用AI' in response.text
    model.assert_not_called()
    assert (await client.get('/api/trip/draft/'+draft)).json()['days_detail'][0]==saved
