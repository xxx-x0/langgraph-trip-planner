import asyncio,json
from unittest.mock import patch,AsyncMock
import pytest
from tests.api.test_narrative_consistency import case
from app.api.routes import trip_draft
from app.services import trip_draft_service
from app.models.schemas import TripRequest


def journey():
 return {'origin_city':'上海','return_city':'上海','outbound':{'departure_station':'上海','arrival_station':'苏州','departure_time':'2026-10-15T08:00','arrival_time':'2026-10-15T16:00','passengers':1,'booking_status':'booked','price_source':'user_estimate','ticket_total':123.45,'extras_total':20}}

@pytest.mark.asyncio
async def test_preview_is_read_only_confirm_shows_conflict_and_old_write_is_rejected(case):
 client,draft,url=case;base=f'/api/trip/draft/{draft}'
 before=await trip_draft_service.get_draft(draft)
 preview=await client.post(base+'/journey',json={'journey':journey()})
 assert preview.status_code==200,preview.text
 data=preview.json();assert data['intercity_total']==143.45 and data['impacts'][0]['conflicts']
 assert (await trip_draft_service.get_draft(draft)).request_json==before.request_json
 save=await client.post(base+'/journey',json={'journey':journey(),'preview_token':data['preview_token']});assert save.status_code==200
 now=await trip_draft_service.get_draft(draft);assert now.days_detail_json==before.days_detail_json
 loaded=(await client.get(base)).json();assert '与抵离交通冲突' in loaded['days_detail'][0]['pending_confirmations'][0]
 assert loaded['days_detail'][0]['day_budget']['total_intercity']==143.45
 # stale day writer never erases new travel constraints
 from app.models.schemas import DayDetail
 with pytest.raises(trip_draft_service.DraftChangedDuringFinalize):
  await trip_draft_service.patch_day_detail(draft,0,DayDetail.model_validate(json.loads(before.days_detail_json)[0]),expected_day=json.loads(before.days_detail_json)[0],expected_request=before.request_json)
 with patch('app.agents.langgraph_agent.finalize.pipeline.compute_day_route',new=AsyncMock(return_value=[])):
  final=await client.post(base+'/finalize')
 assert '与交通或休息安排冲突' in final.text
 assert not any(json.loads(l[6:]).get('type')=='complete' for l in final.text.splitlines() if l.startswith('data: '))
 assert (await trip_draft_service.get_draft(draft)).status!='finalized'

@pytest.mark.asyncio
async def test_stale_preview_does_not_write_over_new_edit(case):
 client,draft,url=case;base=f'/api/trip/draft/{draft}'
 preview=(await client.post(base+'/journey',json={'journey':journey()})).json()
 assert (await client.post(url+'/recompute',json={'day_start_time':'09:00'})).status_code==200
 save=await client.post(base+'/journey',json={'journey':journey(),'preview_token':preview['preview_token']})
 assert save.status_code==409
 assert TripRequest.model_validate_json((await trip_draft_service.get_draft(draft)).request_json).journey is None

@pytest.mark.asyncio
async def test_missing_travel_is_provisional_and_bad_date_returns_422(case):
 client,draft,url=case
 raw=TripRequest.model_validate_json((await trip_draft_service.get_draft(draft)).request_json).model_dump(mode='json')
 check=await client.post('/api/trip/draft/journey-preview',json=raw)
 assert check.status_code==200 and check.json()['days'][0]['window']['provisional']
 bad=journey();bad['outbound']['arrival_time']='2026-10-17T08:00'
 response=await client.post(f'/api/trip/draft/{draft}/journey',json={'journey':bad})
 assert response.status_code==422

@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['recompute','finalize'])
async def test_inflight_result_cannot_overwrite_a_travel_change(case,operation):
 client,draft,url=case;base=f'/api/trip/draft/{draft}'
 entered,resume=asyncio.Event(),asyncio.Event()
 async def paused(*args,**kwargs):
  entered.set();await resume.wait();return []
 path='app.api.routes.trip_draft.compute_day_route' if operation=='recompute' else 'app.agents.langgraph_agent.finalize.pipeline.compute_day_route'
 with patch(path,side_effect=paused):
  task=asyncio.create_task(client.post(url+'/recompute',json={}) if operation=='recompute' else client.post(base+'/finalize'))
  await asyncio.wait_for(entered.wait(),2)
  data=(await client.post(base+'/journey',json={'journey':journey()})).json()
  saved=await client.post(base+'/journey',json={'journey':journey(),'preview_token':data['preview_token']});assert saved.status_code==200
  snapshot=(await trip_draft_service.get_draft(draft)).days_detail_json
  resume.set();result=await task
 assert result.status_code==409 if operation=='recompute' else '本次未保存' in result.text
 assert (await trip_draft_service.get_draft(draft)).days_detail_json==snapshot
 assert (await trip_draft_service.get_draft(draft)).status!='finalized'
