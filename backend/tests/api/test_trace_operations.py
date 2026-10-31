"""Real API/SQLite paths; model, maps and export failures are explicitly injected."""
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from fastapi import HTTPException

from app.api.routes import trip_draft
from app.models.schemas import DayDetail
from app.services import observability as obs, trip_draft_service, multicity
from app.services.ticket_assistant import TicketRankingRequest, Ranking, rank_tickets
from tests.api.test_narrative_consistency import case
from tests.services.test_ticket_schedule import multi
from tests.services.test_observability import runtime, drain, documents, SECRET


def model_response():
    return AIMessage(content=json.dumps({'attractions_order':['丙园','乙园','甲园'], 'meals':[]}),
        usage_metadata={'input_tokens':17,'output_tokens':11,'total_tokens':28})


@pytest.mark.asyncio
async def test_rearrangement_on_off_and_cloud_failure_same_saved_facts(case, runtime, monkeypatch):
    client, draft, url = case
    saved = json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    off = obs.TraceRuntime(replace(runtime.config, enabled=False))
    failed = obs.TraceRuntime(replace(runtime.config, directory=runtime.config.directory/'failed'),
        lambda c:SimpleNamespace(send=lambda *a:(_ for _ in ()).throw(ConnectionError(SECRET)),close=lambda:None))
    results, persisted = [], []
    try:
        for current in (off, runtime, failed):
            monkeypatch.setattr(obs, '_runtime', current)
            await trip_draft_service.patch_day_detail(draft, 0, DayDetail.model_validate(saved))
            with patch.object(trip_draft,'get_llm',return_value=SimpleNamespace(ainvoke=AsyncMock(return_value=model_response()))):
                response = await client.post(url+'/ai-rearrange',json={'hint':SECRET})
            assert response.status_code == 200, response.text
            results.append(response.json())
            persisted.append((await trip_draft_service.get_draft(draft)).days_detail_json)
            await drain(current)
        assert results[0] == results[1] == results[2]
        assert persisted[0] == persisted[1] == persisted[2]
        assert failed.status()['export_failed'] == 1
        doc = documents(runtime)[0]
        assert doc['spans'][0]['facts']['persisted'] is True
        names = {s['name'] for s in doc['spans']}
        assert {'snapshot_read','model_call','constraint_repair','route_calculation','cas_save'} <= names
        assert sum(s['facts'].get('total_tokens',0) for s in doc['spans']) == 28
        serialized = json.dumps(doc,ensure_ascii=False)
        assert all(value not in serialized for value in (SECRET,draft,'甲园','午饭馆'))
    finally:
        failed.close(.5)


@pytest.mark.asyncio
async def test_invalid_model_response_is_rejected_without_saved_changes(case, runtime):
    client, draft, url = case
    saved = (await trip_draft_service.get_draft(draft)).days_detail_json
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=SimpleNamespace(content=SECRET))):
        response = await client.post(url+'/ai-rearrange',json={})
    assert response.status_code == 422
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == saved
    await drain(runtime)
    doc = documents(runtime)[0]
    assert doc['spans'][0]['status'] == 'rejected'
    assert doc['spans'][0]['facts']['persisted'] is False
    assert next(s for s in doc['spans'] if s['name']=='output_validation')['status'] == 'error'
    assert SECRET not in json.dumps(doc)


@pytest.mark.asyncio
async def test_api_cancellation_closes_trace_and_preserves_day(case, runtime):
    client, draft, url = case
    saved = (await trip_draft_service.get_draft(draft)).days_detail_json
    entered = asyncio.Event()
    async def paused(*args,**kwargs):
        entered.set()
        await asyncio.Event().wait()
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',side_effect=paused):
        task = asyncio.create_task(client.post(url+'/ai-rearrange',json={}))
        await asyncio.wait_for(entered.wait(),2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == saved
    await drain(runtime)
    doc = documents(runtime)[0]
    assert doc['spans'][0]['status'] == 'cancelled'
    assert next(s for s in doc['spans'] if s['name']=='model_suggestion')['status'] == 'cancelled'
    assert all(s['end_time'] for s in doc['spans'])


@pytest.mark.asyncio
async def test_cas_conflict_observed_without_overwriting_newer_day(case, runtime):
    client, draft, url = case
    entered, resume = asyncio.Event(), asyncio.Event()
    async def route(*args,**kwargs):
        entered.set()
        await resume.wait()
        return []
    with patch.object(trip_draft,'compute_day_route',side_effect=route),patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=model_response())):
        task = asyncio.create_task(client.post(url+'/ai-rearrange',json={}))
        await asyncio.wait_for(entered.wait(),2)
        with patch.object(trip_draft,'compute_day_route',new=AsyncMock(return_value=[])):
            newer = await client.post(url+'/recompute',json={'removed_attraction_names':['甲园'],'day_start_time':'10:15'})
        assert newer.status_code == 200
        saved = (await trip_draft_service.get_draft(draft)).days_detail_json
        resume.set()
        response = await task
    assert response.status_code == 409
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == saved
    await drain(runtime)
    doc = documents(runtime)[0]
    assert doc['spans'][0]['status'] == 'conflict'
    assert next(s for s in doc['spans'] if s['name']=='cas_save')['status'] == 'conflict'
    assert doc['spans'][0]['facts']['persisted'] is False


@pytest.mark.asyncio
async def test_saved_meal_recovery_is_distinct_from_model_success(case, runtime):
    client, draft, url = case
    original = json.loads((await trip_draft_service.get_draft(draft)).days_detail_json)[0]
    with patch.object(trip_draft,'get_llm'),patch.object(trip_draft,'_invoke_llm_with_retry',new=AsyncMock(return_value=model_response())),patch.object(trip_draft,'meal_plan_violations',side_effect=[['injected meal conflict'],[]]):
        response = await client.post(url+'/ai-rearrange',json={})
    assert response.status_code == 200
    assert [a['name'] for a in response.json()['day_detail']['attractions']] == [a['name'] for a in original['attractions']]
    await drain(runtime)
    doc = documents(runtime)[0]
    assert doc['spans'][0]['facts']['outcome'] == 'preserved_original'
    assert next(s for s in doc['spans'] if s['name']=='saved_schedule_recovery')['facts']['preserved_original'] is True


@pytest.mark.asyncio
async def test_ticket_snapshot_read_only_and_late_conflict_traced(multi, runtime, monkeypatch):
    doc, body = multi
    request = TicketRankingRequest.model_validate(body)
    with patch('app.services.ticket_assistant.get_llm'),patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(return_value=Ranking(ids=['late']))):
        expected = await rank_tickets(request)
        off = obs.TraceRuntime(replace(runtime.config,enabled=False))
        monkeypatch.setattr(obs,'_runtime',off)
        assert await rank_tickets(request) == expected
        monkeypatch.setattr(obs,'_runtime',runtime)
    assert await multicity.load(doc['id']) == doc
    async def mutate(*args,**kwargs):
        async def transform(d,session):
            d['plan']['budget'] = 9999
            return d
        await multicity.write(doc['id'],1,transform)
        return Ranking(ids=['late'])
    with patch('app.services.ticket_assistant.get_llm'),patch('app.services.ticket_assistant.invoke_structured_or_json',side_effect=mutate),pytest.raises(HTTPException) as error:
        await rank_tickets(request)
    assert error.value.status_code == 409
    assert (await multicity.load(doc['id']))['plan']['budget'] == 9999
    await drain(runtime)
    docs = documents(runtime)
    assert len(docs)==2 and len({d['session_alias'] for d in docs})==1
    assert {d['spans'][0]['status'] for d in docs} == {'success','conflict'}
    serialized = json.dumps(docs,ensure_ascii=False)
    assert all(value not in serialized for value in (doc['id'],'已锁公园','保留午餐'))
