"""Conservative sync boundaries. All travel/quote facts are synthetic fixtures."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from tests.api.test_narrative_consistency import case
from tests.api.test_journey_comparison import candidate
from tests.api.test_late_departure_protection import seed,sparse
from app.models.schemas import TripRequest,DayDetail,DraftDayContext,Hotel
from app.services import trip_draft_service
from app.services.journey_comparison import synchronize_days
from app.services.journey_service import apply_context
from app.agents.langgraph_agent.assemble.schedule import schedule_day

async def snapshot(draft):
    record=await trip_draft_service.get_draft(draft)
    return record.request_json,record.days_detail_json,record.status,record.finalized_trip_id

@pytest.mark.asyncio
@pytest.mark.parametrize('preview_sync,confirm_sync',[(False,True),(True,False)])
async def test_sync_choice_is_bound_to_preview_token(case,preview_sync,confirm_sync):
    client,draft,_=case;url=f'/api/trip/draft/{draft}/journey';j=candidate()['journey']
    preview=await client.post(url,json={'journey':j,'synchronize':preview_sync})
    assert preview.status_code==200
    before=await snapshot(draft)
    response=await client.post(url,json={'journey':j,'synchronize':confirm_sync,'preview_token':preview.json()['preview_token']})
    assert response.status_code==409 and await snapshot(draft)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('racer',['day','finalize'])
async def test_atomic_cas_rejects_a_change_after_confirmation_read(case,racer):
    client,draft,day=case;url=f'/api/trip/draft/{draft}/journey';body={'journey':candidate()['journey'],'synchronize':True}
    preview=(await client.post(url,json=body)).json();entered,resume=asyncio.Event(),asyncio.Event()
    replace=trip_draft_service.replace_journey
    async def pause(*args,**kwargs):
        entered.set();await resume.wait();return await replace(*args,**kwargs)
    with patch.object(trip_draft_service,'replace_journey',side_effect=pause):
        pending=asyncio.create_task(client.post(url,json={**body,'preview_token':preview['preview_token']}))
        await asyncio.wait_for(entered.wait(),2)
        if racer=='day':
            changed=await client.post(day+'/recompute',json={'locked_attraction_names':['甲园'],'removed_attraction_names':['丙园']})
            assert changed.status_code==200
        else:
            with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
                finalized=await client.post(f'/api/trip/draft/{draft}/finalize')
            assert any(json.loads(l[6:]).get('type')=='complete' for l in finalized.text.splitlines() if l.startswith('data: ')), finalized.text
        before=await snapshot(draft);resume.set();response=await pending
    assert response.status_code==409 and await snapshot(draft)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('arrival,expect_conflict',[('09:00',False),('15:30',True)])
async def test_fixed_rest_and_saved_meal_identity_survive_sync(case,arrival,expect_conflict):
    client,draft,day=case
    before=await sparse(client,day)
    await seed(draft,rest=[{'id':'rest','date':'2026-10-15','start_time':'14:00','end_time':'16:00','label':'固定休息'}])
    response=await client.post(day+'/recompute',json={});assert response.status_code==200
    saved=response.json()['day_detail'];old=await snapshot(draft)
    j=candidate()['journey'];j['outbound']['arrival_time']='2026-10-15T'+arrival
    body={'journey':j,'synchronize':True};url=f'/api/trip/draft/{draft}/journey'
    data=(await client.post(url,json=body)).json();assert bool(data['impacts'][0]['conflicts'])==expect_conflict
    assert await snapshot(draft)==old
    response=await client.post(url,json={**body,'preview_token':data['preview_token']});assert response.status_code==200,response.text
    now=json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    for field in ['attractions','meals','locked_attraction_names','removed_attraction_names','timeline_order','rest_periods']:
        assert now[field]==saved[field],field
    if expect_conflict: assert now['timeline_schedule']==saved['timeline_schedule'] and now['day_start_time']==saved['day_start_time']
    else: assert [x for x in now['timeline_schedule'] if x['kind']=='rest']==[x for x in saved['timeline_schedule'] if x['kind']=='rest']


def pure(*,old_journey=None):
    req=TripRequest(city='苏州',start_date='2026-10-15',end_date='2026-10-16',travel_days=2,transportation='步行',accommodation='酒店',journey=old_journey)
    day=apply_context(DayDetail(day_index=0,date=req.start_date,day_start_time='08:00',hotel=Hotel(name='H'),timeline_order=[{'kind':'hotel','ref_name':'H','phase':'end'}]),req)
    schedule_day(day)
    ctx=DraftDayContext(day_index=0,date=req.start_date)
    return SimpleNamespace(request=req,days=[ctx],days_detail=[day])


def overnight_journey():
    j=candidate()['journey'];j['outbound'].update(departure_time='2026-10-15T23:00',arrival_time='2026-10-16T06:00')
    return j


def test_removing_overnight_journey_restores_date_based_lodging_nights():
    payload=pure(old_journey=overnight_journey());assert payload.days_detail[0].overnight_stay is False
    req=payload.request.model_copy(update={'journey':None})
    before=deepcopy(payload.days_detail[0].model_dump(mode='json'))
    details,impacts,budget=synchronize_days(payload,req)
    assert details[0].overnight_stay is True
    assert payload.days_detail[0].model_dump(mode='json')==before
    assert budget.total_hotels==0 and any('旧记录住宿报价条件未核对' in x for x in budget.unknown_cost_items)


def test_failed_sync_retains_times_but_does_not_keep_invalid_hotel_charge():
    payload=pure();original=payload.days_detail[0];original.timeline_schedule[-1]['cost']=100
    request=TripRequest.model_validate({**payload.request.model_dump(mode='json'),'journey':overnight_journey()})
    details,impacts,budget=synchronize_days(payload,request)
    assert impacts[0]['conflicts'] and not details[0].overnight_stay
    assert details[0].timeline_schedule[-1]['start_time']==original.timeline_schedule[-1]['start_time']
    assert details[0].timeline_schedule[-1]['cost'] is None
    assert original.timeline_schedule[-1]['cost']==100 and budget.total_hotels==0


def test_partial_skeleton_retains_null_day_and_marks_budget_incomplete():
    payload=pure();payload.days_detail=[None]
    details,impacts,budget=synchronize_days(payload,payload.request)
    assert details==[None] and len(impacts)==1 and not budget.is_complete
    assert any('尚未装配' in x for x in budget.unknown_cost_items)
