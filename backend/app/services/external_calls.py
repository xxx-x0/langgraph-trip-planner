"""One retry owner for external reads; deadlines include queueing and recovery."""
import asyncio
import copy
import hashlib
import json
import logging
import time
import httpx
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable

from ..config import get_settings


class FailureKind(StrEnum):
    TIMEOUT = 'timeout'
    CONNECTION = 'connection'
    RATE_LIMIT = 'rate_limit'
    AUTH = 'authentication'
    INVALID_REQUEST = 'invalid_request'
    INVALID_RESPONSE = 'invalid_response'
    UNAVAILABLE = 'unavailable'
    TOOL_ERROR = 'tool_error'


class ExternalServiceError(RuntimeError):
    def __init__(self, provider: str, operation: str, kind: FailureKind):
        self.provider, self.operation, self.kind = provider, operation, kind
        self.retryable = kind in {FailureKind.TIMEOUT, FailureKind.CONNECTION,
                                  FailureKind.RATE_LIMIT, FailureKind.UNAVAILABLE}
        labels = {FailureKind.TIMEOUT: '超时', FailureKind.CONNECTION: '连接中断',
                  FailureKind.RATE_LIMIT: '请求受限', FailureKind.AUTH: '服务认证失败',
                  FailureKind.INVALID_REQUEST: '请求不受支持', FailureKind.INVALID_RESPONSE: '返回数据无效',
                  FailureKind.UNAVAILABLE: '暂不可用', FailureKind.TOOL_ERROR: '工具执行失败'}
        service = {'amap':'地图服务','llm':'模型服务','aigohotel':'酒店服务','bing':'搜索服务'}.get(provider, provider)
        step = {'generate':'生成内容','macro_planner':'按日编排','structured_output':'生成结构化内容',
                'maps_weather':'查询天气','maps_search_detail':'查询地点详情','SearchHotels':'查询酒店',
                'bing_search':'搜索网页','tools/list':'加载服务工具'}.get(operation, operation)
        super().__init__(f'{service}：{step}{labels[kind]}' + ('，可重试' if self.retryable else '，请检查服务配置或输入'))


def classify_error(error: Exception) -> FailureKind:
    if isinstance(error, ExternalServiceError):
        return error.kind
    if isinstance(error, BaseExceptionGroup):
        kinds = [classify_error(e) for e in error.exceptions if isinstance(e, Exception)]
        return next((kind for kind in kinds if kind != FailureKind.TOOL_ERROR), FailureKind.TOOL_ERROR)
    # Exception text is inspected only, never included in public errors or events.
    text = str(error).lower()
    status = getattr(error, 'status_code', None)
    if '当前输入可能包含不当内容' in text:
        return FailureKind.INVALID_REQUEST
    if status in {401, 403} or any(s in text for s in ['invalid_user_key', 'invalid api key', 'authentication', 'unauthorized', 'permission_denied']):
        return FailureKind.AUTH
    if status == 429 or any(s in text for s in ['429', 'cuqps', 'rate limit', 'too many requests', 'exceeded_the_limit']):
        return FailureKind.RATE_LIMIT
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or 'timeout' in text or 'timed out' in text:
        return FailureKind.TIMEOUT
    if status is not None and status >= 500:
        return FailureKind.UNAVAILABLE
    if status is not None and 400 <= status < 500:
        return FailureKind.INVALID_REQUEST
    if isinstance(error, (ValueError, TypeError, KeyError, NotImplementedError)):
        return FailureKind.INVALID_REQUEST
    if isinstance(error, (ConnectionError, OSError, httpx.NetworkError, httpx.RemoteProtocolError)) or any(s in text for s in ['connection', 'eof', 'broken pipe', 'closed', 'connect', 'sse', 'reset']):
        return FailureKind.CONNECTION
    if any(s in text for s in ['502', '503', '504', 'service unavailable']):
        return FailureKind.UNAVAILABLE
    return FailureKind.TOOL_ERROR


def decode_tool_result(value: Any, provider='mcp', operation='tool', depth=0) -> Any:
    """Unwrap MCP text/structured content without discarding service fields."""
    if depth > 12:
        raise ExternalServiceError(provider, operation, FailureKind.INVALID_RESPONSE)
    if hasattr(value, 'status') and value.status == 'error':
        raise ExternalServiceError(provider, operation, classify_error(RuntimeError(str(value.content))))
    if hasattr(value, 'model_dump'):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            if not value.strip():
                raise ExternalServiceError(provider, operation, FailureKind.INVALID_RESPONSE)
            return {'raw_result': value}
        return decode_tool_result(parsed, provider, operation, depth + 1)
    if isinstance(value, dict):
        if value.get('isError') or value.get('status') == 'error' or value.get('success') is False or value.get('status') in ('0', 0):
            raise ExternalServiceError(provider, operation, classify_error(RuntimeError(json.dumps(value, default=str))))
        if value.get('structuredContent') is not None:
            return decode_tool_result(value['structuredContent'], provider, operation, depth + 1)
        if 'content' in value and isinstance(value['content'], (list, str)):
            return decode_tool_result(value['content'], provider, operation, depth + 1)
        return value
    if isinstance(value, list):
        if value and all(isinstance(v, dict) and v.get('type') == 'text' for v in value):
            decoded = [decode_tool_result(v.get('text', ''), provider, operation, depth + 1) for v in value]
            return decoded[0] if len(decoded) == 1 else decoded
        return value
    raise ExternalServiceError(provider, operation, FailureKind.INVALID_RESPONSE)


@dataclass(frozen=True)
class CallPolicy:
    total_timeout: float = 30
    attempt_timeout: float = 20
    max_attempts: int = 2
    backoff: float = .25
    concurrency: int = 1


_deadline: ContextVar[float | None] = ContextVar('external_deadline', default=None)
_events = deque(maxlen=1000)
_gates: dict[tuple[Any, str, int], asyncio.Semaphore] = {}
_cache: OrderedDict = OrderedDict()


@asynccontextmanager
async def operation_deadline(seconds: float):
    deadline = min(time.monotonic() + seconds, _deadline.get() or float('inf'))
    token = _deadline.set(deadline)
    try:
        async with asyncio.timeout(max(0, deadline - time.monotonic())):
            yield
    finally:
        _deadline.reset(token)


def call_events() -> list[dict]:
    return list(_events)


def clear_external_state():
    _cache.clear()
    _gates.clear()
    _events.clear()


def _event(provider, operation, outcome, started, attempt=0):
    event = dict(provider=provider, operation=operation, outcome=outcome,
                 attempt=attempt, milliseconds=round((time.monotonic()-started)*1000))
    _events.append(event)
    logging.getLogger('app.external').info('external_call %s', json.dumps(event))


async def invoke_external(provider: str, operation: str, invoke: Callable[[], Awaitable[Any]], *,
                          policy: CallPolicy | None = None, recover=None,
                          arguments=None, cache_ttl: float = 0) -> Any:
    policy = policy or CallPolicy()
    started = time.monotonic()
    deadline = min(started + policy.total_timeout, _deadline.get() or float('inf'))
    # Arguments never enter logs or cache keys in plaintext. Cache only explicit read operations.
    key = (provider, operation, hashlib.sha256(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest())
    loop = asyncio.get_running_loop()
    gate = _gates.setdefault((loop, provider, policy.concurrency), asyncio.Semaphore(policy.concurrency))
    attempt = 0
    try:
        async with asyncio.timeout(max(0, deadline - time.monotonic())):
            async with gate:
                cached = _cache.get(key) if cache_ttl else None
                if cached and cached[0] > time.monotonic():
                    _event(provider, operation, 'cache_hit', started)
                    return copy.deepcopy(cached[1])
                for attempt in range(1, policy.max_attempts + 1):
                    try:
                        async with asyncio.timeout(min(policy.attempt_timeout, max(0, deadline-time.monotonic()))):
                            result = await invoke()
                        if cache_ttl:
                            _cache[key] = (time.monotonic()+cache_ttl, copy.deepcopy(result))
                            _cache.move_to_end(key)
                            while len(_cache) > 256:
                                _cache.popitem(last=False)
                        _event(provider, operation, 'success', started, attempt)
                        return result
                    except Exception as error:
                        kind = classify_error(error)
                        safe = ExternalServiceError(provider, operation, kind)
                        _event(provider, operation, kind.value, started, attempt)
                        if not safe.retryable or attempt == policy.max_attempts:
                            raise safe from None
                        if recover and kind in {FailureKind.CONNECTION, FailureKind.TIMEOUT}:
                            await recover()
                        await asyncio.sleep(policy.backoff * attempt)
    except asyncio.CancelledError:
        _event(provider, operation, 'cancelled', started, attempt)
        raise
    except TimeoutError:
        _event(provider, operation, 'deadline', started, attempt)
        raise ExternalServiceError(provider, operation, FailureKind.TIMEOUT) from None


async def invoke_llm(runnable, messages, *, max_attempts=2, timeout=None):
    settings = get_settings()
    total = min(timeout or settings.external_llm_timeout, settings.external_llm_timeout)
    return await invoke_external('llm', 'generate', lambda: runnable.ainvoke(messages),
        policy=CallPolicy(total_timeout=total, attempt_timeout=min(30, total),
                          max_attempts=min(max_attempts, 2), concurrency=2))
