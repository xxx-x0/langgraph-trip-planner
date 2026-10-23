"""Facts, legacy projections and late writers; all service doubles are explicitly test-only."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.api.routes import trip_draft
from app.database import init_db, async_session
from app.models.db_models import TripRecord
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton, DayDetail, TripPlan, DayPlan, WeatherInfo
from app.services import trip_draft_service, trip_history_service


@pytest_asyncio.fixture
async def case():
    await init_db()
    req = TripRequest(city='苏州', start_date='2026-10-15', end_date='2026-10-16',
                      travel_days=2, transportation='步行', accommodation='民宿')
    draft = await trip_draft_service.create_draft(user_id='ltp10-test',request=req,selected_attractions=[],
        macro_plan=MacroPlan(city=req.city,total_days=2,days=[
            DaySkeleton(day_index=i,date=d,attraction_names=['甲园','乙园','丙园'])
            for i,d in enumerate([req.start_date,req.end_date])]),
        clusters_data=[[{'name':n,'visit_minutes':60,'ticket_price':None} for n in ['甲园','乙园','丙园']]]*2,
        hotels_by_day=[[{'name':'住处','estimated_cost':200}]]*2,
        dining_pool=[{'main':[{'category':'main','name':'午饭馆','estimated_cost':40,'open_hours':'10:00-22:00'}]}]*2,
        weather_info=[{'date':req.start_date,'day_weather':'阴','night_weather':'雨','day_temp':24,'night_temp':19}])
    with patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            url=f'/api/trip/draft/{draft}/day/0'
            for i in range(2):
                r=await client.post(f'/api/trip/draft/{draft}/day/{i}/recompute',json={})
                assert r.status_code==200
            yield client,draft,url


def assert_current(detail):
    text=detail['description']
    assert detail['description_source']=='itinerary_facts_v1'
    names=[a['name'] for a in detail['attractions']]
    if names: assert names[0] in text
    for activity in detail['timeline_schedule']:
        assert f"{activity['start_time']}–{activity['end_time']} " not in text
    for name in detail['removed_attraction_names']:
        assert name not in text
    assert detail['pending_confirmations']
    assert '已预约成功' not in text
    assert '门票全部免费' not in text


@pytest.mark.asyncio
async def test_every_successful_edit_and_finalize_use_current_facts(case):
    client,draft,url=case
    for edit in [
        {'attractions_order':['丙园','乙园','甲园'],'day_start_time':'09:30'},
        {'removed_attraction_names':['丙园'],'locked_attraction_names':['乙园']},
        {'meals':[{'name':'午饭馆','category':'main','insert_after':'乙园'}]},
        {'day_start_time':'11:30'},
        {'removed_attraction_names':[]},
    ]:
        r=await client.post(url+'/recompute',json=edit)
        assert r.status_code==200,r.text
        assert_current(r.json()['day_detail'])
        assert (await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]==r.json()['day_detail']
    llm=SimpleNamespace(content=json.dumps({'attractions_order':['甲园','丙园','乙园'],'meals':[]}))
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=llm)):
        ai=await client.post(url+'/ai-rearrange',json={})
    assert ai.status_code==200
    assert_current(ai.json()['day_detail'])
    assert ai.json()['day_detail']['attractions'][0]['name']=='乙园'
    forced=await client.post(url+'/assemble?force=true',json={})
    assert forced.status_code==200
    assert_current(forced.json()['day_detail'])
    # No final manual refresh is needed. Finalize immediately after deleting an unlocked attraction.
    saved=(await client.post(url+'/recompute',json={'removed_attraction_names':['甲园']})).json()['day_detail']
    with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
        completed=await client.post(f'/api/trip/draft/{draft}/finalize')
    event=next(json.loads(x[6:]) for x in completed.text.splitlines() if x.startswith('data: ') and json.loads(x[6:])['type']=='complete')
    plan=event['trip_plan']
    assert plan['days'][0]['description']==saved['description']
    assert plan['narrative_source']=='itinerary_facts_v1'
    assert '需要1晚住宿' in plan['overall_suggestions']
    assert plan['budget']['total_hotels'] == 0
    assert '旧记录住宿报价条件未核对' in plan['overall_suggestions']
    assert '未知价格不代表免费' in plan['overall_suggestions']
    history=(await client.get(f"/api/trips/{event['trip_id']}")).json()['data']['plan']
    assert history==plan
    again=await client.post(f'/api/trip/draft/{draft}/finalize')
    repeated=next(json.loads(x[6:]) for x in again.text.splitlines() if x.startswith('data: ') and json.loads(x[6:])['type']=='complete')
    assert repeated==event


@pytest.mark.asyncio
async def test_legacy_draft_get_and_cached_assemble_suppress_stale_copy_without_writing(case):
    client,draft,url=case
    raw=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    raw.update(description='旧文：晴天08:00先游甲园，门票全部免费，已预约成功',description_source=None)
    await trip_draft_service.patch_day_detail(draft,0,DayDetail.model_validate(raw))
    before=(await trip_draft_service.get_draft(draft)).days_detail_json
    get=(await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][0]
    cached=(await client.post(url+'/assemble',json={})).json()['day_detail']
    assert get==cached
    assert_current(get)
    assert '白天阴 24°C' in '\n'.join(get['pending_confirmations'])
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==before


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['narrative','recompute','ai-rearrange','assemble?force=true'])
async def test_late_writer_cannot_overwrite_new_deletion_or_description(case,operation):
    client,draft,url=case
    entered,resume=asyncio.Event(),asyncio.Event()
    async def paused(*args,**kwargs):
        entered.set()
        await resume.wait()
        return '过期文案' if operation in ['narrative','assemble?force=true'] else []
    target='write_day_narrative_llm' if operation in ['narrative','assemble?force=true'] else 'compute_day_route'
    llm=SimpleNamespace(content=json.dumps({'attractions_order':['丙园','乙园','甲园']}))
    with patch.object(trip_draft,target,side_effect=paused),patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=llm)):
        task=asyncio.create_task(client.post(url+'/'+operation,json={}))
        await asyncio.wait_for(entered.wait(),2)
        # Restore only the paused test hook so the competing edit can complete.
        with patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[])):
            newer=await client.post(url+'/recompute',json={'removed_attraction_names':['甲园'],'day_start_time':'10:15'})
        assert newer.status_code==200
        snapshot=(await trip_draft_service.get_draft(draft)).days_detail_json
        resume.set()
        late=await task
    assert late.status_code==409
    assert '未保存' in late.json()['detail']
    assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot
    assert_current(newer.json()['day_detail'])


@pytest.mark.asyncio
async def test_editing_another_day_does_not_reject_current_day(case):
    client,draft,url=case
    entered,resume=asyncio.Event(),asyncio.Event()
    async def paused(*args,**kwargs):
        entered.set();await resume.wait();return 'ignored'
    with patch.object(trip_draft,'write_day_narrative_llm',side_effect=paused):
        task=asyncio.create_task(client.post(url+'/narrative',json={}))
        await asyncio.wait_for(entered.wait(),2)
        newer=await client.post(f'/api/trip/draft/{draft}/day/1/recompute',json={'day_start_time':'12:00'})
        resume.set();response=await task
    assert response.status_code==200
    assert (await client.get(f'/api/trip/draft/{draft}')).json()['days_detail'][1]==newer.json()['day_detail']


@pytest.mark.asyncio
async def test_legacy_history_view_retains_original_json_and_extra_fields(case):
    client,draft,_=case
    payload=(await client.get(f'/api/trip/draft/{draft}')).json()
    plan=TripPlan(city='苏州',start_date='2026-10-15',end_date='2026-10-16',overall_suggestions='旧文：两晚免费升级',
        days=[DayPlan(**{k:v for k,v in d.items() if k in DayPlan.model_fields},transportation='步行',accommodation='民宿') for d in payload['days_detail']])
    row=trip_history_service.build_trip_record(plan)
    raw=json.loads(row.plan_data)
    raw.update(trip_tagline='晴空万里，门票全免',overall_suggestions='两晚免费升级',weather_summary='晴')
    raw['days'][0].update(description='旧文：先游已删除景点',description_source=None)
    raw['legacy_extra']={'preserve':True}
    row.plan_data=json.dumps(raw,ensure_ascii=False)
    before=row.plan_data
    async with async_session() as session:
        session.add(row);await session.commit();trip_id=row.id
    view=(await client.get(f'/api/trips/{trip_id}')).json()['data']['plan']
    assert '旧文' not in view['days'][0]['description']
    assert view['legacy_extra']=={'preserve':True}
    assert '两晚免费升级' not in view['overall_suggestions']
    assert view['weather_summary']==''
    async with async_session() as session:
        assert (await session.get(TripRecord,trip_id)).plan_data==before
