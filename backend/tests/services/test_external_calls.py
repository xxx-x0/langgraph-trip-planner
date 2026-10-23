import asyncio
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.services.external_calls import (CallPolicy, ExternalServiceError, FailureKind,
    call_events, clear_external_state, decode_tool_result, invoke_external)
from app.services.mcp_gateway import MCPGateway
from app.services import llm_service
from app.config import get_settings


def test_traceback_redaction_covers_secrets_and_query_credentials(monkeypatch):
    from app.services.safe_errors import RedactingFormatter
    import sys
    monkeypatch.setattr(get_settings(),'amap_api_key','synthetic-private-value')
    try:raise RuntimeError('https://host/?key=synthetic-private-value Authorization: Bearer other-private-token')
    except RuntimeError:
        record=logging.LogRecord('test',logging.ERROR,__file__,1,'request failed',(),sys.exc_info())
    rendered=RedactingFormatter().format(record)
    assert 'synthetic-private-value' not in rendered and 'other-private-token' not in rendered
    assert '[REDACTED]' in rendered


@pytest.fixture(autouse=True)
def isolated_policy_state():
    clear_external_state()
    llm_service.reset_llm()
    yield
    clear_external_state()
    llm_service.reset_llm()


@pytest.mark.parametrize('wrap', [lambda d:d, lambda d:{'structuredContent':d,'content':[]},
    lambda d:[{'type':'text','text':__import__('json').dumps(d)}],
    lambda d:{'content':[{'type':'text','text':__import__('json').dumps(d)}]}])
def test_decode_preserves_candidate_facts(wrap):
    facts={'pois':[{'id':'real-id','location':'120.1,31.2','cost':'68','source':'nearby'}]}
    assert decode_tool_result(wrap(facts)) == facts


@pytest.mark.parametrize('payload,kind', [
    ({'isError':True,'content':[{'type':'text','text':'CUQPS_HAS_EXCEEDED_THE_LIMIT'}]},FailureKind.RATE_LIMIT),
    ({'status':'0','info':'INVALID_USER_KEY'},FailureKind.AUTH),
    ({'isError':True,'content':[{'type':'text','text':'bad request'}]},FailureKind.TOOL_ERROR),
    (None,FailureKind.INVALID_RESPONSE)])
def test_mcp_errors_do_not_look_like_empty_success(payload,kind):
    with pytest.raises(ExternalServiceError) as error:decode_tool_result(payload)
    assert error.value.kind==kind


@pytest.mark.asyncio
async def test_managed_tool_reconnects_with_fresh_handle_without_outer_retries():
    async def search(city: str):return {'status':'1','city':city}
    raw=StructuredTool.from_function(coroutine=search,name='maps_weather',description='weather')
    object.__setattr__(raw,'ainvoke',AsyncMock(side_effect=[ConnectionError('key=private-secret connection reset'),{'city':'苏州'}]))
    load=AsyncMock(return_value=[raw]);reset=AsyncMock()
    gateway=MCPGateway('amap',load,reset)
    tool=await gateway.tool('maps_weather')
    from app.agents.langgraph_agent.exceptions import _invoke_tool_with_retry
    assert await _invoke_tool_with_retry(tool,{'city':'苏州'},max_retries=3)=={'city':'苏州'}
    assert raw.ainvoke.await_count==2 and reset.await_count==1
    assert load.await_count==3  # list + both attempts, not a stale raw tool retry
    assert 'private-secret' not in str(call_events())


@pytest.mark.asyncio
async def test_rate_error_payload_retries_but_authentication_does_not():
    async def search(city: str):return {}
    raw=StructuredTool.from_function(coroutine=search,name='maps_weather',description='weather')
    object.__setattr__(raw,'ainvoke',AsyncMock(side_effect=[{'isError':True,'content':[{'type':'text','text':'CUQPS'}]}, {'status':'1','forecasts':[]}]))
    gateway=MCPGateway('amap',AsyncMock(return_value=[raw]),AsyncMock())
    assert (await gateway.call('maps_weather',{'city':'苏州'}))['status']=='1'
    assert raw.ainvoke.await_count==2
    object.__setattr__(raw,'ainvoke',AsyncMock(return_value={'status':'0','info':'INVALID_USER_KEY'}))
    with pytest.raises(ExternalServiceError):await gateway.call('maps_weather',{'city':'苏州'})
    assert raw.ainvoke.await_count==1


@pytest.mark.asyncio
async def test_total_deadline_includes_cold_initialization_and_cancels_it():
    cancelled=asyncio.Event()
    async def load():
        try:await asyncio.Event().wait()
        finally:cancelled.set()
    gateway=MCPGateway('amap',load,AsyncMock())
    start=time.monotonic()
    with pytest.raises(ExternalServiceError) as error:await gateway.call('maps_weather',{},timeout=.03)
    assert error.value.kind==FailureKind.TIMEOUT
    assert time.monotonic()-start<.2 and cancelled.is_set()


@pytest.mark.asyncio
async def test_queue_timeout_and_cancellation_release_capacity():
    entered=asyncio.Event();release=asyncio.Event()
    async def blocking():entered.set();await release.wait();return 'ok'
    first=asyncio.create_task(invoke_external('test','first',blocking,policy=CallPolicy(total_timeout=1)))
    await entered.wait()
    never=AsyncMock(return_value='never')
    with pytest.raises(ExternalServiceError):
        await invoke_external('test','queued',never,policy=CallPolicy(total_timeout=.02))
    never.assert_not_awaited()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):await first
    assert await invoke_external('test','after',AsyncMock(return_value='ready'))=='ready'


@pytest.mark.asyncio
async def test_backoff_cannot_restart_the_total_deadline():
    invoke=AsyncMock(side_effect=ConnectionError('reset'))
    with pytest.raises(ExternalServiceError):
        await invoke_external('test','backoff',invoke,policy=CallPolicy(total_timeout=.03,backoff=.2))
    assert invoke.await_count==1


@pytest.mark.asyncio
async def test_failed_and_mutated_results_are_not_reused_as_success():
    async def detail(id: str):return {}
    raw=StructuredTool.from_function(coroutine=detail,name='maps_search_detail',description='detail')
    object.__setattr__(raw,'ainvoke',AsyncMock(side_effect=[{'isError':True}, {'id':'A','location':'120,31','cost':'68'}]))
    gateway=MCPGateway('amap',AsyncMock(return_value=[raw]),AsyncMock())
    with pytest.raises(ExternalServiceError):await gateway.call(raw.name,{'id':'A'})
    successful=await gateway.call(raw.name,{'id':'A'});successful['cost']='broken'
    cached=await gateway.call(raw.name,{'id':'A'})
    assert cached['cost']=='68' and raw.ainvoke.await_count==2
    assert call_events()[-1]['outcome']=='cache_hit'


@pytest.mark.asyncio
async def test_errors_and_observations_never_contain_exception_secrets(caplog):
    invoke=AsyncMock(side_effect=ValueError('Authorization: Bearer private-token https://host/?key=private-key'))
    with caplog.at_level(logging.INFO),pytest.raises(ExternalServiceError) as error:
        await invoke_external('test','read',invoke)
    assert 'private-' not in str(error.value)+caplog.text+str(call_events())
    assert invoke.await_count==1


@pytest.mark.asyncio
async def test_auto_capability_probe_falls_back_once_and_remembers_result(monkeypatch):
    monkeypatch.setattr(get_settings(),'llm_structured_output_mode','auto')
    class Output(BaseModel):ok: bool
    structured=SimpleNamespace(ainvoke=AsyncMock(side_effect=ValueError('function_calling unsupported')))
    plain=SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content='{"ok":true}')),
                          with_structured_output=lambda *a,**kw:structured)
    assert (await llm_service.invoke_structured_or_json(plain,'probe',Output)).ok
    assert (await llm_service.invoke_structured_or_json(plain,'again',Output)).ok
    assert structured.ainvoke.await_count==1 and plain.ainvoke.await_count==2
    assert not llm_service.is_structured_output_supported()


@pytest.mark.asyncio
async def test_probe_timeout_is_not_misclassified_as_unsupported(monkeypatch):
    monkeypatch.setattr(get_settings(),'llm_structured_output_mode','auto')
    class Output(BaseModel):ok: bool
    async def hang(_):await asyncio.Event().wait()
    plain=SimpleNamespace(ainvoke=AsyncMock(),with_structured_output=lambda *a,**kw:SimpleNamespace(ainvoke=hang))
    with pytest.raises((ExternalServiceError,TimeoutError)):
        await llm_service.invoke_structured_or_json(plain,'probe',Output,timeout=.02)
    plain.ainvoke.assert_not_awaited()
    assert llm_service.is_structured_output_supported()
