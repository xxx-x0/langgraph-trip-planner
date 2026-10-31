"""Opt-in, fail-open tracing for two business operations.

Only fixed enums, bounded numbers and HMAC aliases cross this boundary. Raw model
messages, exceptions and business objects never enter the queue or LangSmith.
The worker owns all disk/network I/O; SDK automatic tracing is disabled in scope.
"""
import asyncio
import hashlib
import hmac
import json
import math
import os
import queue
import re
import secrets
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from langsmith import tracing_context

_NAMES = frozenset('ticket_recommendation day_rearrangement snapshot_read eligibility metric_selection route_context model_selection output_validation rule_fallback snapshot_recheck response model_suggestion constraint_repair route_calculation schedule_validation saved_schedule_recovery fact_projection cas_save model_call external_queue external_attempt external_reconnect external_backoff external_result'.split())
_ENUMS = frozenset('success error cancelled timeout conflict rejected fallback empty preserved_original adjusted ai rules train flight balanced price time daytime available unknown unavailable waitlist main breakfast lunch dinner snack dessert cafe late_night auto manual llm amap aigohotel bing open_meteo unsplash other cache_hit connection rate_limit authentication invalid_request invalid_response tool_error deadline start end'.split())
_OPERATIONS = frozenset('generate maps_direction_walking maps_direction_transit_integrated maps_direction_driving maps_direction_bicycling maps_search_detail maps_text_search maps_around_search maps_geo maps_weather'.split())
_ENUMS = _ENUMS | _OPERATIONS
_ENUMS = _ENUMS | {'metric','preferences','schedule','mixed','availability','empty_preferences','empty_mixed_constraints'}
_ENUMS = _ENUMS | {'improved','unchanged','not_comparable'}
_NAMES = _NAMES | {'route_comparison'}
_KEYS = frozenset('ticket_input query preferences accepted_seats daytime_hard candidates id mode priority passengers departure arrival fare availability selected_ids candidate_count eligible_count excluded_count result_count checked_schedule model_valid fallback preserved_original adjustment_count locks_changed day_index hint_present hint_omitted day_before day_after proposed_order proposed_meals corrected_order attractions meals order locked removed duration slot schedule_mode start end route_count estimated_count problem_count persisted provider attempt outcome milliseconds input_tokens output_tokens total_tokens usage_known status_code count truncated snapshot_alias revision model_alias'.split())
_KEYS = _KEYS | {'external_operation', 'prompt_alias', 'empty_reason', 'route_input_count', 'route_unknown_count', 'lookup_count', 'route_input_complete'}
_KEYS = _KEYS | {'route_goal_status','traffic_before_minutes','traffic_after_minutes','traffic_delta_minutes','route_search_count','route_search_truncated'}
_current: ContextVar = ContextVar('quality_span', default=None)
_runtime = None
_runtime_lock = threading.Lock()


def _safe(value, depth=0):
    if depth > 7:
        return None
    if value is None or type(value) is bool:
        return value
    if type(value) in (int, float):
        return value if math.isfinite(value) and abs(value) <= 10**12 else None
    if isinstance(value, str):
        return value if value in _ENUMS or re.fullmatch(r'anon_[a-f0-9]{24}', value) else None
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth+1) for v in value[:100]]
    if isinstance(value, dict):
        return {k: _safe(v, depth+1) for k, v in value.items() if k in _KEYS}
    return None


@dataclass(frozen=True)
class TraceConfig:
    enabled: bool = False
    export_enabled: bool = False
    directory: Path = field(default_factory=lambda: Path.home()/'.local/share/langgraph-trip-planner/observability')
    api_key: str = field(default='', repr=False)
    endpoint: str = 'https://api.smith.langchain.com'
    workspace: str = ''
    project: str = 'trip-planner-dev'
    environment: str = 'dev'
    execution_mode: str = 'live'
    data_origin: str = 'unclassified'
    identity_key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    identity_scope: str = 'process'
    queue_limit: int = 1000
    span_limit: int = 128
    retention_days: int = 30
    max_bytes: int = 200*1024*1024

    @classmethod
    def environment(cls):
        # A dedicated file is explicit opt-in; backend/.env and the P0 file are never edited.
        from dotenv import dotenv_values
        path = os.environ.get('OBSERVABILITY_CONFIG_FILE')
        values = {**(dotenv_values(path) if path else {}), **os.environ}
        yes = lambda key: str(values.get(key, '')).lower() in {'1', 'true', 'yes'}
        key = values.get('OBSERVABILITY_HASH_KEY', '')
        return cls(enabled=yes('OBSERVABILITY_ENABLED'), export_enabled=yes('OBSERVABILITY_EXPORT_ENABLED'),
                   directory=Path(values.get('OBSERVABILITY_DIR') or cls().directory).expanduser(),
                   api_key=values.get('LANGSMITH_API_KEY', ''),
                   endpoint=values.get('LANGSMITH_ENDPOINT') or 'https://api.smith.langchain.com',
                   workspace=values.get('LANGSMITH_WORKSPACE_ID', ''),
                   project=values.get('LANGSMITH_PROJECT') or 'trip-planner-dev',
                   environment=values.get('OBSERVABILITY_ENVIRONMENT') if values.get('OBSERVABILITY_ENVIRONMENT') in {'dev','demo','eval'} else 'dev',
                   identity_key=key.encode() if len(key) >= 32 else secrets.token_bytes(32),
                   identity_scope='configured' if len(key) >= 32 else 'process')


class LangSmithExporter:
    """A synchronous client used exclusively by one bounded daemon worker."""
    def __init__(self, config):
        from urllib.parse import urlparse
        from urllib3.util.retry import Retry
        from langsmith import Client
        import requests
        endpoint = urlparse(config.endpoint)
        allowed = {'api.smith.langchain.com', 'eu.api.smith.langchain.com', 'aws.api.smith.langchain.com'}
        if endpoint.scheme != 'https' or endpoint.hostname not in allowed or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in {'', '/'}:
            raise ValueError('invalid_trace_endpoint')
        if not config.api_key:
            raise ValueError('missing_trace_credentials')
        class SingleAttemptClient(Client):
            def request_with_retries(self, *args, **kwargs):
                kwargs['stop_after_attempt'] = 1
                return super().request_with_retries(*args, **kwargs)
        class SameOriginSession(requests.Session):
            def send(self, request, **kwargs):
                if urlparse(request.url).netloc != endpoint.netloc:
                    raise ValueError('trace_destination_changed')
                # Redirects must not send credentials to a different origin.
                kwargs['allow_redirects'] = False
                response = super().send(request, **kwargs)
                if 300 <= response.status_code < 400:
                    raise ValueError('trace_redirect_rejected')
                return response
        self.client = SingleAttemptClient(api_url=config.endpoint, api_key=config.api_key,
            workspace_id=config.workspace or None, session=SameOriginSession(), retry_config=Retry(total=0),
            timeout_ms=(250, 750), auto_batch_tracing=False, omit_traced_runtime_info=True,
            disable_prompt_cache=True, tracing_sampling_rate=1.0, tracing_mode='langsmith')
        self.project = config.project

    def send(self, document, stopping):
        sent = 0
        for row in document['spans']:
            if stopping():
                raise ExportFailure(sent)
            kwargs = dict(id=row['id'], trace_id=document['operation_id'], parent_run_id=row['parent_id'],
                          dotted_order=row['dotted_order'], start_time=row['start_time'], end_time=row['end_time'],
                          outputs={'facts': row['facts']}, error=None if row['status']=='success' else row['status'],
                          extra={'metadata': {'operation_id': document['operation_id'],
                              'session_alias': document['session_alias'], 'schema_version': 'trace-v1',
                              'privacy_version': 'allowlist-v1', 'technical_status': row['status'],
                              'environment': document.get('environment', 'dev'),
                              'execution_mode': document.get('execution_mode', 'unclassified'),
                              'data_origin': document.get('data_origin', 'unclassified'),
                              'input_omitted': True, 'identity_scope': document['identity_scope']}},
                          tags=['trace-v1', 'allowlist-v1'])
            if row['run_type']=='llm' and row['facts'].get('usage_known'):
                # Client.create_run's **kwargs accepts arbitrary fields; token usage must
                # live in metadata (RunTree.set contract), not a top-level ignored field.
                kwargs['extra']['metadata']['usage_metadata'] = {
                    k:row['facts'][k] for k in ('input_tokens','output_tokens','total_tokens')}
            try:
                self.client.create_run(row['name'], {}, row['run_type'], project_name=self.project, **kwargs)
            except Exception:
                raise ExportFailure(sent) from None
            sent += 1
        return sent

    def close(self):
        self.client.close(timeout=0)


class ExportFailure(Exception):
    def __init__(self, sent):
        super().__init__('trace_export_failed')
        self.sent = sent


class TraceRuntime:
    def __init__(self, config, exporter_factory=LangSmithExporter):
        self.config, self.exporter_factory = config, exporter_factory
        self.queue = queue.Queue(maxsize=max(1, config.queue_limit))
        self.lock = threading.Lock()
        self.stats = dict(accepted=0, exported=0, export_failed=0, partial_exports=0, local_failed=0,
                          dropped_operations=0, dropped_spans=0, instrumentation_errors=0,
                          pending_spans=0, shutdown_pending=0)
        self.closed = False
        self.deadline = float('inf')
        self.worker = None
        if config.enabled:
            self.worker = threading.Thread(target=self._work, name='trip-trace-export', daemon=True)
            self.worker.start()

    def count(self, name, amount=1):
        with self.lock:
            self.stats[name] += amount

    def alias(self, value):
        if value is None:
            return None
        return 'anon_'+hmac.new(self.config.identity_key, str(value).encode(), hashlib.sha256).hexdigest()[:24]

    def status(self):
        with self.lock:
            return {**self.stats, 'enabled': self.config.enabled and not self.closed,
                    'export_enabled': self.config.export_enabled, 'identity_scope': self.config.identity_scope}

    def submit(self, document):
        count = len(document['spans'])
        with self.lock:
            if self.closed or count+self.stats['pending_spans'] > self.config.queue_limit:
                self.stats['dropped_operations'] += 1
                self.stats['dropped_spans'] += count
                return
            self.stats['pending_spans'] += count
            try:
                self.queue.put_nowait(document)
                self.stats['accepted'] += 1
            except queue.Full:
                self.stats['pending_spans'] -= count
                self.stats['dropped_operations'] += 1
                self.stats['dropped_spans'] += count

    def _persist(self, document):
        folder = self.config.directory/'operations'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        filename = folder/(document['operation_id']+'.json')
        temporary = folder/(document['operation_id']+'.tmp')
        content = json.dumps(document, ensure_ascii=False, allow_nan=False).encode()
        fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, filename)
        # This directory contains only disposable operation indices, never pinned experiments.
        files = sorted(folder.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
        total, cutoff = 0, time.time()-self.config.retention_days*86400
        for path in files:
            stat = path.stat()
            total += stat.st_size
            if stat.st_mtime < cutoff or total > self.config.max_bytes:
                path.unlink()

    def _save(self, document):
        try:
            self._persist(document)
        except Exception:
            self.count('local_failed')

    def _work(self):
        exporter = None
        try:
            while not self.closed or not self.queue.empty():
                try:
                    document = self.queue.get(timeout=.05)
                except queue.Empty:
                    continue
                try:
                    document['export_status'] = 'pending' if self.config.export_enabled else 'disabled'
                    self._save(document)
                    if self.config.export_enabled:
                        try:
                            if time.monotonic() >= self.deadline:
                                raise RuntimeError('trace_shutdown_deadline')
                            if exporter is None:
                                exporter = self.exporter_factory(self.config)
                            document['exported_spans'] = exporter.send(document, lambda:time.monotonic()>=self.deadline)
                            document['export_status'] = 'exported'
                            self.count('exported')
                        except Exception as exc:
                            # Never serialize SDK errors: they may contain credentials or URLs.
                            document['exported_spans'] = exc.sent if isinstance(exc, ExportFailure) else 0
                            document['export_status'] = 'partial' if document['exported_spans'] else 'export_failed'
                            if document['exported_spans']:
                                self.count('partial_exports')
                            self.count('export_failed')
                        self._save(document)
                except Exception:
                    self.count('instrumentation_errors')
                finally:
                    self.count('pending_spans', -len(document['spans']))
                    self.queue.task_done()
        finally:
            if exporter is not None:
                try:
                    exporter.close()
                except Exception:
                    pass

    def close(self, timeout=2):
        self.closed = True
        self.deadline = time.monotonic()+max(0, min(timeout, 2))
        if self.worker:
            self.worker.join(max(0, self.deadline-time.monotonic()))
            if self.worker.is_alive():
                with self.lock:
                    self.stats['shutdown_pending'] = self.stats['pending_spans']
        return self.status()


def get_runtime():
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                try:
                    _runtime = TraceRuntime(TraceConfig.environment())
                except Exception:
                    _runtime = TraceRuntime(TraceConfig())
    return _runtime


def close_observability(timeout=2):
    if _runtime is not None:
        return _runtime.close(timeout)
    return {'enabled': False}


class Span:
    def __init__(self, runtime, name, parent=None, run_type='chain'):
        self.runtime, self.parent = runtime, parent
        self.root = parent.root if parent else self
        self.id = str(uuid4())
        now = datetime.now(timezone.utc)
        component = now.strftime('%Y%m%dT%H%M%S%fZ')+self.id
        self.row = dict(id=self.id, parent_id=parent.id if parent else None, name=name,
                        run_type=run_type, dotted_order=(parent.row['dotted_order']+'.' if parent else '')+component,
                        start_time=now.isoformat(), end_time=None, status='success', facts={})
        self.started = time.monotonic()
        if parent is None:
            self.rows, self.session, self.finished = [], None, False
        self.root.rows.append(self.row)

    def set(self, **facts):
        try:
            self.row['facts'].update(_safe(facts))
        except Exception:
            self.runtime.count('instrumentation_errors')

    def finish(self, error=None):
        self.row['end_time'] = datetime.now(timezone.utc).isoformat()
        self.row['milliseconds'] = round((time.monotonic()-self.started)*1000, 3)
        if error is not None:
            status = getattr(error, 'status_code', None)
            self.row['status'] = ('cancelled' if isinstance(error, asyncio.CancelledError) else
                'conflict' if status==409 else 'rejected' if status in {400,404,422} else
                'timeout' if isinstance(error, TimeoutError) or getattr(error, 'kind', None)=='timeout' else 'error')
            if type(status) is int:
                self.set(status_code=status)


class _NoSpan:
    def set(self, **facts):
        pass
_NO_SPAN = _NoSpan()


@contextmanager
def span(name, *, run_type='chain'):
    parent = _current.get()
    active, token = None, None
    try:
        if parent and not parent.root.finished and name in _NAMES:
            if len(parent.root.rows) < parent.runtime.config.span_limit:
                active = Span(parent.runtime, name, parent, run_type)
                token = _current.set(active)
            else:
                parent.runtime.count('dropped_spans')
                parent.root.set(truncated=True)
    except Exception:
        active = None
    error = None
    try:
        yield active or _NO_SPAN
    except BaseException as exc:
        error = exc
        raise
    finally:
        if active:
            try:
                active.finish(error)
            except Exception:
                pass
        if token is not None:
            _current.reset(token)


def record(**facts):
    active = _current.get()
    if active:
        active.set(**facts)


def associate(identifier, *, revision=None, basis=None):
    try:
        active = _current.get()
        if active:
            active.root.session = active.runtime.alias(identifier)
            active.root.set(revision=revision, snapshot_alias=active.runtime.alias(basis))
    except Exception:
        pass


def alias(value):
    try:
        active = _current.get()
        return active.runtime.alias(value) if active else None
    except Exception:
        return None


def traced_operation(name):
    if name not in _NAMES:
        raise ValueError('unknown_operation')
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            runtime, root, token = None, None, None
            try:
                runtime = get_runtime()
                if runtime.config.enabled and not runtime.closed:
                    root = Span(runtime, name)
                    token = _current.set(root)
            except Exception:
                pass
            error = None
            try:
                # Explicitly suppress ambient SDK auto-tracing even when our switch is off.
                with tracing_context(enabled=False, parent=False):
                    return await function(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                if root:
                    try:
                        root.finish(error)
                        root.finished = True
                        for row in root.rows:
                            if row['end_time'] is None:
                                row.update(end_time=root.row['end_time'], status='cancelled')
                        document = dict(schema_version='trace-v1', privacy_version='allowlist-v1',
                            operation_id=root.id, session_alias=root.session, identity_scope=runtime.config.identity_scope,
                            environment=runtime.config.environment if runtime.config.environment in {'dev','demo','eval'} else 'dev',
                            execution_mode=runtime.config.execution_mode if runtime.config.execution_mode in {'live','synthetic','replay','injected_failure','live_model_with_replay','live_model_with_synthetic_tools'} else 'unclassified',
                            data_origin=runtime.config.data_origin if runtime.config.data_origin in {'synthetic','historical_capture','mixed'} else 'unclassified',
                            spans=root.rows, raw_text_omitted=True, exported_spans=0)
                        # Snapshot before dispatch: a late child cannot mutate a queued operation.
                        runtime.submit(json.loads(json.dumps(document, allow_nan=False)))
                    except Exception:
                        try:
                            runtime.count('instrumentation_errors')
                        except Exception:
                            pass
                if token is not None:
                    _current.reset(token)
        return wrapped
    return decorate


def ticket_facts(request):
    if _current.get() is None:
        return None
    try:
        def minutes(value):
            d = datetime.fromisoformat(value)
            return d.toordinal()*1440+d.hour*60+d.minute
        return dict(query=dict(mode=request.query.mode, priority=request.query.priority, passengers=request.query.passengers,
                preferences=dict(accepted_seats=[alias(x) for x in request.query.preferences.accepted_seats],
                    fare=request.query.preferences.max_reference_fare_per_person,
                    start=int(request.query.preferences.departure_after[:2])*60+int(request.query.preferences.departure_after[3:]),
                    end=int(request.query.preferences.arrival_before[:2])*60+int(request.query.preferences.arrival_before[3:]),
                    daytime_hard=request.query.preferences.daytime_hard)),
            candidates=[dict(id=alias(c.id), mode=c.mode, departure=minutes(c.departure), arrival=minutes(c.arrival),
                fare=c.fare_per_person, availability=c.availability) for c in request.candidates[:80]])
    except Exception:
        return None


def day_facts(detail):
    if _current.get() is None or detail is None:
        return None
    try:
        return dict(attractions=[dict(id=alias(a.name), duration=a.visit_duration) for a in detail.attractions],
            meals=[dict(id=alias(m.name), slot=m.type, schedule_mode=m.schedule_mode) for m in detail.meals],
            order=[alias(x.get('ref_name')) for x in detail.timeline_order],
            locked=[alias(n) for n in detail.locked_attraction_names], removed=[alias(n) for n in detail.removed_attraction_names],
            route_count=len(detail.route_segments), estimated_count=sum(bool(r.is_estimated) for r in detail.route_segments))
    except Exception:
        return None


def model_usage(result):
    try:
        usage = getattr(result, 'usage_metadata', None)
        if not isinstance(usage, dict):
            record(usage_known=False)
            return
        values = {k: usage.get(k) for k in ('input_tokens','output_tokens','total_tokens')}
        if all(type(v) is int and 0<=v<=10**9 for v in values.values()):
            record(usage_known=True, **values)
        else:
            record(usage_known=False)
    except Exception:
        pass


def model_identity(runnable, messages):
    """Fingerprint only: neither runtime configuration nor message text is retained."""
    if _current.get() is None:
        return
    try:
        record(model_alias=alias(getattr(runnable, 'model_name', None)),
               prompt_alias=alias(str(messages)))
    except Exception:
        pass
