import json
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient,ASGITransport
from sqlalchemy import select,func

from app.api.main import app
from app.api.routes import trip_draft
from app.database import init_db,async_session
from app.models.db_models import TripDraft,TripRecord
from app.models.schemas import TripRequest,MacroPlan,DaySkeleton,DayDetail,RouteSegment
from app.services import trip_draft_service
from app.services.external_calls import ExternalServiceError,FailureKind


@pytest_asyncio.fixture
async def saved_day(monkeypatch):
    await init_db();root=Path(__file__).parents[2]/'evals/datasets'
    data=json.loads((root/'inputs/R10.json').read_text());day=data['day_detail'];request=TripRequest.model_validate(data['request'])
    matrix={(e['from'],e['to']):e for e in json.loads((root/'routes/R10.json').read_text())['edges']}
    draft=await trip_draft_service.create_draft(user_id='route-quality-test',request=request,selected_attractions=[],
        macro_plan=MacroPlan(city=request.city,total_days=1,days=[DaySkeleton(day_index=0,date=day['date'],attraction_names=[a['name'] for a in day['attractions']])]),
        clusters_data=[[{**a,'visit_minutes':a['visit_duration'],**a['location']} for a in day['attractions']]],
        hotels_by_day=[[day['hotel']]],dining_pool=[{'main':data['dining_candidates']}],weather_info=[])
    await trip_draft_service.patch_day_detail(draft,0,DayDetail.model_validate(day))
    async def route(detail,*args):
        names=[x['ref_name'] for x in detail.timeline_order];out=[]
        for a,b in zip(names,names[1:]):
            e=matrix[a,b];out.append(RouteSegment(from_name=a,to_name=b,duration=f"{e['duration_minutes']}分钟",mode=e['mode'],is_estimated=False))
        return out
    monkeypatch.setattr(trip_draft,'compute_day_route',route)
    monkeypatch.setattr(trip_draft,'get_llm',lambda:None)
    response=dict(attractions_order=[a['name'] for a in day['attractions']],meals=trip_draft._saved_meals(DayDetail.model_validate(day)))
    model=AsyncMock(return_value=SimpleNamespace(content=json.dumps(response,ensure_ascii=False)))
    monkeypatch.setattr(trip_draft,'_invoke_llm_with_retry',model)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        yield client,draft,f'/api/trip/draft/{draft}/day/0',model


@pytest.mark.asyncio
async def test_route_goal_improves_neutral_model_and_survives_readback(saved_day):
    client,draft,url,model=saved_day
    result=await client.post(url+'/ai-rearrange',json={'hint':'希望少绕路，保留全部景点和现有餐厅'})
    assert result.status_code==200,result.text
    day=result.json()['day_detail'];assert day['route_comparison']['delta_minutes']==42
    assert day['route_comparison']['status']=='improved' and '减少42分钟' in day['description']
    reread=(await client.get('/api/trip/draft/'+draft)).json()['days_detail'][0]
    assert reread==day and model.await_count==1


@pytest.mark.asyncio
async def test_recompute_and_finalize_block_closing_without_writing(saved_day):
    client,draft,url,_=saved_day
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    result=await client.post(url+'/recompute',json={'day_start_time':'20:00'})
    assert result.status_code==409 and '开放时间' in result.text
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before
    # Seed an old invalid saved snapshot: finalize must refuse it without writing history.
    invalid=json.loads(before);invalid[0]['day_start_time']='20:00'
    async with async_session() as session:
        record=await session.get(TripDraft,draft);record.days_detail_json=json.dumps(invalid);await session.commit()
        count=(await session.scalar(select(func.count()).select_from(TripRecord)))
    invalid_json=(await trip_draft_service.get_draft(draft)).days_detail_json
    result=await client.post('/api/trip/draft/'+draft+'/finalize')
    assert '不在已知开放时间内' in result.text
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==invalid_json
    async with async_session() as session:assert await session.scalar(select(func.count()).select_from(TripRecord))==count


@pytest.mark.asyncio
async def test_ordinary_ai_closed_proposal_recovers_original(saved_day):
    client,draft,url,model=saved_day
    model.return_value=SimpleNamespace(content=json.dumps(dict(attractions_order=['七里山塘景区','留园','虎丘山风景区'],meals=[
        dict(category='main',name='山塘河宴·周公蟹·松鼠桂鱼(山塘街店)',insert_after='留园',preferred_slot='lunch'),
        dict(category='main',name='凝翠园饭店',insert_after='留园',preferred_slot='dinner')]),ensure_ascii=False))
    result=await client.post(url+'/ai-rearrange',json={})
    assert result.status_code==200,result.text
    day=result.json()['day_detail'];assert [a['name'] for a in day['attractions']]==['虎丘山风景区','留园','七里山塘景区']
    assert any('开放时间不兼容' in n for n in day['meal_adjustments'])


@pytest.mark.asyncio
async def test_final_route_failure_does_not_save_partial_optimization(saved_day,monkeypatch):
    client,draft,url,_=saved_day;before=(await trip_draft_service.get_draft(draft)).days_detail_json
    lookup=trip_draft.compute_day_route
    async def unavailable(detail,*args):
        if len(detail.timeline_order)>2:raise ExternalServiceError('amap','test_final_route_unavailable',FailureKind.UNAVAILABLE)
        return await lookup(detail,*args)
    monkeypatch.setattr(trip_draft,'compute_day_route',unavailable)
    result=await client.post(url+'/ai-rearrange',json={'hint':'少绕路'})
    assert result.status_code>=400
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
async def test_concurrent_edit_during_final_route_still_rejects_old_save(saved_day,monkeypatch):
    client,draft,url,_=saved_day;entered=asyncio.Event();resume=asyncio.Event();lookup=trip_draft.compute_day_route
    async def paused(detail,*args):
        if len(detail.timeline_order)>2:entered.set();await resume.wait()
        return await lookup(detail,*args)
    monkeypatch.setattr(trip_draft,'compute_day_route',paused)
    task=asyncio.create_task(client.post(url+'/ai-rearrange',json={'hint':'少绕路'}))
    await asyncio.wait_for(entered.wait(),2)
    async with async_session() as session:
        record=await session.get(TripDraft,draft);days=json.loads(record.days_detail_json)
        days[0]['locked_attraction_names']=['虎丘山风景区','留园'];record.days_detail_json=json.dumps(days);await session.commit()
    latest=(await trip_draft_service.get_draft(draft)).days_detail_json
    resume.set();result=await task
    assert result.status_code==409
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==latest


@pytest.mark.asyncio
async def test_comparison_and_deleted_state_survive_finalize_and_history(saved_day):
    client,draft,url,_=saved_day
    async with async_session() as session:
        record=await session.get(TripDraft,draft);days=json.loads(record.days_detail_json)
        days[0]['removed_attraction_names']=['不恢复的测试景点'];record.days_detail_json=json.dumps(days);await session.commit()
    edited=await client.post(url+'/ai-rearrange',json={'hint':'少绕路'})
    assert edited.status_code==200,edited.text
    day=edited.json()['day_detail'];assert day['route_comparison']['status']=='improved'
    final=await client.post('/api/trip/draft/'+draft+'/finalize')
    event=next(json.loads(s[6:]) for s in final.text.splitlines() if s.startswith('data: ') and json.loads(s[6:])['type']=='complete')
    saved=event['trip_plan']['days'][0]
    assert saved['route_comparison']==day['route_comparison'] and '减少42分钟' in saved['description']
    assert saved['removed_attraction_names']==['不恢复的测试景点']
    history=(await client.get('/api/trips/'+str(event['trip_id']))).json()['data']['plan']['days'][0]
    assert history['route_comparison']==saved['route_comparison'] and history['description']==saved['description']
