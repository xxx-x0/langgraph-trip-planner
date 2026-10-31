"""Trace privacy and isolation, using fake business services and bounded exporters."""
import asyncio
import copy
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage

from app.services import observability as obs
from app.services.external_calls import invoke_external, invoke_llm, CallPolicy, ExternalServiceError, clear_external_state
from app.services.ticket_assistant import TicketRankingRequest, Ranking, rank_tickets

SECRET = 'synthetic-credential-DO-NOT-EXPORT-13812345678-person@example.test'


class RecordingExporter:
    def __init__(self, config):
        self.documents = []
    def send(self, document, stopping):
        self.documents.append(copy.deepcopy(document))
        return len(document['spans'])
    def close(self):
        pass


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    exporter = RecordingExporter(None)
    value = obs.TraceRuntime(obs.TraceConfig(enabled=True, export_enabled=True, directory=tmp_path,
        identity_key=b'unit-test-identity-key-only-00000000'), lambda c:exporter)
    value.test_exporter = exporter
    monkeypatch.setattr(obs, '_runtime', value)
    yield value
    value.close(.5)
    clear_external_state()


async def drain(runtime):
    for _ in range(300):
        if runtime.status()['pending_spans']==0:
            return
        await asyncio.sleep(.01)
    raise AssertionError('worker failed to drain')


def documents(runtime):
    return [json.loads(p.read_text()) for p in (runtime.config.directory/'operations').glob('*.json')]


def ticket_request():
    return TicketRankingRequest.model_validate(dict(query=dict(priority='balanced',mode='train', from_place=SECRET,to_place='B',date='2026-11-01',passengers=1),
        candidates=[dict(id='candidate_1',mode='train',service=SECRET[:60],from_station=SECRET,to_station='B',departure='2026-11-01T15:48',arrival='2026-11-01T17:17',seat=SECRET[:80],fare_per_person=None,availability='unknown',source='12306')]))


@pytest.mark.asyncio
async def test_concurrent_operations_have_closed_non_crossing_parent_trees(runtime):
    @obs.traced_operation('ticket_recommendation')
    async def operation(identifier):
        obs.associate(identifier, basis=SECRET)
        with obs.span('model_selection'):
            await asyncio.sleep(.001)
            with obs.span('output_validation'):
                obs.record(selected_ids=[obs.alias(identifier)], hint_present=True)
        return identifier
    assert await asyncio.gather(*(operation(str(i)) for i in range(8)))==list(map(str,range(8)))
    await drain(runtime)
    docs=documents(runtime);assert len(docs)==8
    assert len({d['session_alias'] for d in docs})==8
    all_ids=set()
    for d in docs:
        ids={r['id'] for r in d['spans']};assert not all_ids&ids;all_ids|=ids
        assert len(ids)==3 and d['spans'][0]['id']==d['operation_id']
        for row in d['spans']:
            assert row['end_time'] and row['status']=='success'
            assert row['parent_id'] is None or row['parent_id'] in ids
    assert SECRET not in json.dumps(docs)


@pytest.mark.asyncio
@pytest.mark.parametrize('error,status',[(asyncio.CancelledError(),'cancelled'),(TimeoutError(SECRET),'timeout'),(HTTPException(409,SECRET),'conflict'),(HTTPException(422,SECRET),'rejected'),(ValueError(SECRET),'error')])
async def test_errors_preserve_original_semantics_without_exporting_messages(runtime,error,status):
    @obs.traced_operation('day_rearrangement')
    async def operation():
        with obs.span('cas_save'):
            raise error
    with pytest.raises(type(error)) as caught:await operation()
    assert caught.value is error
    await drain(runtime)
    doc=documents(runtime)[0]
    assert all(r['status']==status for r in doc['spans'])
    assert SECRET not in json.dumps(doc)


@pytest.mark.asyncio
async def test_disabled_switch_overrides_ambient_sdk_tracing(tmp_path,monkeypatch):
    from langsmith import traceable
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    runtime=obs.TraceRuntime(obs.TraceConfig(enabled=False,export_enabled=True,directory=tmp_path),lambda c:pytest.fail('exporter constructed'))
    monkeypatch.setattr(obs,'_runtime',runtime)
    import requests
    monkeypatch.setattr(requests.Session,'send',lambda *a,**k:pytest.fail('network while disabled'))
    @traceable
    async def auto_child(value):return value
    @obs.traced_operation('ticket_recommendation')
    async def operation():
        with obs.span('model_call'):
            return await auto_child(SECRET)
    assert await operation()==SECRET
    assert runtime.worker is None and runtime.status()['accepted']==0 and not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_ticket_fallback_and_empty_outcomes_are_not_model_success(runtime):
    with patch('app.services.ticket_assistant.get_llm',side_effect=ValueError(SECRET)):
        result=await rank_tickets(ticket_request())
    assert result['ranked_by']=='rules'
    request=ticket_request();request.candidates[0].availability='waitlist'
    with patch('app.services.ticket_assistant.get_llm',side_effect=AssertionError('must not call')):
        result=await rank_tickets(request)
    assert result['recommendations']==[]
    await drain(runtime)
    docs=documents(runtime)
    assert {d['spans'][0]['facts']['outcome'] for d in docs}=={'fallback','empty'}
    assert SECRET not in json.dumps(docs)
    assert 'candidate_1' not in json.dumps(docs)


@pytest.mark.asyncio
async def test_ticket_invalid_model_selection_has_separate_failed_validation(runtime):
    with patch('app.services.ticket_assistant.get_llm',return_value=object()),patch('app.services.ticket_assistant.invoke_structured_or_json',new=AsyncMock(return_value=Ranking(ids=[SECRET]))):
        result=await rank_tickets(ticket_request())
    await drain(runtime);doc=documents(runtime)[0]
    assert result['ranked_by']=='rules' and doc['spans'][0]['status']=='success'
    assert next(s for s in doc['spans'] if s['name']=='output_validation')['facts']['model_valid'] is False
    assert SECRET not in json.dumps(doc)


@pytest.mark.asyncio
async def test_actual_model_attempt_has_usage_once_and_no_prompt_response(runtime):
    runnable=SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=SECRET,usage_metadata={'input_tokens':7,'output_tokens':5,'total_tokens':12})))
    @obs.traced_operation('ticket_recommendation')
    async def operation():
        with obs.span('model_selection'):
            return await invoke_llm(runnable,[('human',SECRET)],max_attempts=1)
    assert (await operation()).content==SECRET
    await drain(runtime);doc=documents(runtime)[0]
    used=[s for s in doc['spans'] if s['facts'].get('usage_known')]
    assert len(used)==1 and used[0]['run_type']=='llm'
    assert used[0]['facts']['total_tokens']==12
    assert SECRET not in json.dumps(doc)


@pytest.mark.asyncio
async def test_retries_queue_reconnect_backoff_cache_and_timeout_are_visible(runtime):
    call=AsyncMock(side_effect=[ConnectionError(SECRET),{'ok':True}]);recover=AsyncMock()
    @obs.traced_operation('day_rearrangement')
    async def operation():
        policy=CallPolicy(max_attempts=2,backoff=.001,total_timeout=1,attempt_timeout=.2)
        a=await invoke_external('amap','maps_direction_walking',call,policy=policy,recover=recover,arguments={'secret':SECRET},cache_ttl=20)
        b=await invoke_external('amap','maps_direction_walking',call,policy=policy,arguments={'secret':SECRET},cache_ttl=20)
        return a,b
    assert await operation()==({'ok':True},{'ok':True})
    assert call.await_count==2 and recover.await_count==1
    @obs.traced_operation('day_rearrangement')
    async def timeout():
        return await invoke_external('amap','maps_direction_walking',lambda:asyncio.sleep(.1),policy=CallPolicy(max_attempts=1,total_timeout=.01,attempt_timeout=.01))
    with pytest.raises(ExternalServiceError):await timeout()
    await drain(runtime);docs=documents(runtime)
    trace=next(d for d in docs if d['spans'][0]['status']=='success')
    names=[s['name'] for s in trace['spans']]
    assert names.count('external_attempt')==2
    assert 'external_queue' in names and 'external_backoff' in names and 'external_reconnect' in names
    assert any(s['facts'].get('outcome')=='cache_hit' for s in trace['spans'])
    assert any(d['spans'][0]['status']=='timeout' for d in docs)
    assert SECRET not in json.dumps(docs)


@pytest.mark.asyncio
async def test_export_failure_and_disk_failure_do_not_change_business_result(runtime,monkeypatch):
    runtime.exporter_factory=lambda c:SimpleNamespace(send=lambda *a:(_ for _ in ()).throw(ConnectionError(SECRET)),close=lambda:None)
    monkeypatch.setattr(runtime,'_persist',lambda d:(_ for _ in ()).throw(OSError(SECRET)))
    @obs.traced_operation('ticket_recommendation')
    async def operation():return {'original':SECRET}
    assert await operation()=={'original':SECRET}
    await drain(runtime)
    assert runtime.status()['export_failed']==1 and runtime.status()['local_failed']==2


@pytest.mark.asyncio
async def test_submission_failure_is_fail_open(runtime,monkeypatch):
    monkeypatch.setattr(runtime,'submit',lambda d:(_ for _ in ()).throw(RuntimeError(SECRET)))
    @obs.traced_operation('ticket_recommendation')
    async def operation():return 42
    assert await operation()==42
    assert runtime.status()['instrumentation_errors']==1


@pytest.mark.asyncio
async def test_queue_and_span_caps_nonblocking_shutdown(tmp_path,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    class SlowExporter(RecordingExporter):
        def send(self,document,stopping):entered.set();release.wait(5);return len(document['spans'])
    runtime=obs.TraceRuntime(obs.TraceConfig(enabled=True,export_enabled=True,directory=tmp_path,queue_limit=4,span_limit=3),SlowExporter)
    monkeypatch.setattr(obs,'_runtime',runtime)
    @obs.traced_operation('ticket_recommendation')
    async def operation():
        for _ in range(5):
            with obs.span('eligibility'):pass
        return 'business_result'
    assert await operation()=='business_result'
    await asyncio.to_thread(entered.wait,.5)
    start=time.monotonic()
    assert await operation()=='business_result'
    assert time.monotonic()-start<.1
    stats=runtime.close(.05)
    assert time.monotonic()-start<.3
    assert stats['dropped_operations']==1 and stats['dropped_spans']>=3 and stats['shutdown_pending']==3
    release.set();await asyncio.to_thread(runtime.worker.join,.5)
    assert documents(runtime)[0]['spans'][0]['facts']['truncated'] is True


@pytest.mark.asyncio
async def test_local_only_switch_never_constructs_cloud_client(tmp_path,monkeypatch):
    runtime=obs.TraceRuntime(obs.TraceConfig(enabled=True,export_enabled=False,directory=tmp_path),lambda c:pytest.fail('cloud client'))
    monkeypatch.setattr(obs,'_runtime',runtime)
    @obs.traced_operation('ticket_recommendation')
    async def operation():return True
    assert await operation();await drain(runtime);runtime.close(.2)
    assert documents(runtime)[0]['export_status']=='disabled'


def test_config_is_opt_in_and_does_not_expose_secrets(monkeypatch,tmp_path):
    config=tmp_path/'trace.env';config.write_text('LANGSMITH_API_KEY='+SECRET+'\nOBSERVABILITY_ENABLED=false\n')
    monkeypatch.setenv('OBSERVABILITY_CONFIG_FILE',str(config));monkeypatch.delenv('OBSERVABILITY_ENABLED',raising=False)
    value=obs.TraceConfig.environment();assert value.enabled is False and value.api_key==SECRET
    assert SECRET not in repr(value)
    monkeypatch.setenv('OBSERVABILITY_ENABLED','true');assert obs.TraceConfig.environment().enabled


def test_sdk_transport_payload_and_single_attempt_failure(tmp_path,monkeypatch):
    import requests
    captured=[]
    def send(session,request,**kwargs):
        captured.append(json.loads(request.body))
        response=requests.Response();response.status_code=200;response._content=b'{}';response.request=request
        return response
    monkeypatch.setattr(requests.Session,'send',send)
    config=obs.TraceConfig(enabled=True,export_enabled=True,directory=tmp_path,api_key='synthetic-api-key',project='p1-unit')
    exporter=obs.LangSmithExporter(config)
    root=obs.Span(obs.TraceRuntime(obs.TraceConfig()),'ticket_recommendation')
    root.set(hint=SECRET,query={'unknown':SECRET,'mode':SECRET},selected_ids=['raw-id',root.runtime.alias(SECRET)])
    root.finish(ValueError(SECRET))
    doc=dict(operation_id=root.id,session_alias=root.runtime.alias(SECRET),identity_scope='process',spans=root.rows)
    assert exporter.send(doc,lambda:False)==1
    payload=json.dumps(captured)
    assert SECRET not in payload and 'raw-id' not in payload
    assert captured[0]['inputs']=={} and captured[0]['error']=='error'
    assert 'runtime' not in captured[0]['extra']
    root.row['run_type']='llm'
    root.set(usage_known=True,input_tokens=7,output_tokens=5,total_tokens=12)
    assert exporter.send(doc,lambda:False)==1
    assert captured[-1]['extra']['metadata']['usage_metadata']=={'input_tokens':7,'output_tokens':5,'total_tokens':12}
    assert 'usage_metadata' not in captured[-1]
    calls=[]
    def fail(*a,**k):calls.append(1);raise requests.ConnectionError(SECRET)
    monkeypatch.setattr(requests.Session,'send',fail)
    with pytest.raises(obs.ExportFailure):exporter.send(doc,lambda:False)
    assert len(calls)==1
    exporter.close()


@pytest.mark.parametrize('endpoint',['http://api.smith.langchain.com','https://api.smith.langchain.com.attacker.test','https://user:pass@api.smith.langchain.com','https://api.smith.langchain.com/?token=secret'])
def test_exporter_rejects_other_origins(endpoint):
    with pytest.raises(ValueError):obs.LangSmithExporter(obs.TraceConfig(endpoint=endpoint,api_key=SECRET))


@pytest.mark.asyncio
async def test_partial_upload_is_visible_and_not_retried(runtime):
    calls=[]
    def partial(document,stopping):
        calls.append(1)
        raise obs.ExportFailure(1)
    runtime.exporter_factory=lambda c:SimpleNamespace(send=partial,close=lambda:None)
    @obs.traced_operation('ticket_recommendation')
    async def operation():
        with obs.span('eligibility'):pass
        return True
    assert await operation()
    await drain(runtime)
    assert calls==[1]
    assert runtime.status()['partial_exports']==1
    doc=documents(runtime)[0]
    assert doc['export_status']=='partial' and doc['exported_spans']==1


def test_retention_only_prunes_operation_indices_and_files_are_private(tmp_path):
    import os
    runtime=obs.TraceRuntime(obs.TraceConfig(directory=tmp_path,max_bytes=1000))
    folder=tmp_path/'operations';folder.mkdir()
    expired=folder/'old.json';expired.write_text('{}')
    old=time.time()-31*86400;os.utime(expired,(old,old))
    experiment=tmp_path/'experiments';experiment.mkdir()
    fixed=experiment/'fixed.json';fixed.write_text('keep');os.utime(fixed,(old,old))
    runtime._persist({'operation_id':'first','facts':'x'*800})
    runtime._persist({'operation_id':'second','facts':'x'*800})
    assert [p.name for p in folder.glob('*.json')]==['second.json']
    assert fixed.read_text()=='keep'
    assert (folder/'second.json').stat().st_mode&0o777==0o600


def test_sdk_redirect_is_failed_without_following_it(monkeypatch):
    import requests
    calls=[]
    def redirect(session,request,**kwargs):
        calls.append(kwargs['allow_redirects'])
        response=requests.Response();response.status_code=307
        response.headers['Location']='https://other.example.test/runs'
        return response
    monkeypatch.setattr(requests.Session,'send',redirect)
    exporter=obs.LangSmithExporter(obs.TraceConfig(api_key=SECRET))
    root=obs.Span(obs.TraceRuntime(obs.TraceConfig()),'ticket_recommendation');root.finish()
    doc=dict(operation_id=root.id,session_alias=None,identity_scope='process',spans=root.rows)
    with pytest.raises(obs.ExportFailure):exporter.send(doc,lambda:False)
    assert calls==[False]
    exporter.close()
