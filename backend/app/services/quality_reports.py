"""Read-only presentation of explicitly published eval snapshots. No DB or SDK clients."""
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re

SCHEMA = 'quality-workbench-v1'
CATEGORIES = {
    'model_issue': '模型意图/偏好问题（待人审）',
    'reference_dispute': '参考口径分歧',
    'evidence_gap': '证据缺项',
    'fault_injection': '故障注入',
    'unclassified': '待分类诊断',
}
STATUS_KEYS = {'PASS': 'P', 'FAIL': 'F', 'ERROR': 'E', 'NOT_EVALUATED': 'U', 'NOT_APPLICABLE': 'NA'}
QUALITY_RULES = {'T-RANK', 'R-INTENT', 'R-ROUTE', 'J-INTENT', 'J-TRADEOFF'}
# Only fixture facts useful for review. No raw prompt, credentials, identity, address or URL fields.
FACT_KEYS = set('query mode direction from_place to_place date passengers priority candidates id service from_station to_station departure arrival seat fare_per_person availability source request city start_date end_date travel_days transportation companions count type journey origin_city return_city outbound inbound departure_time arrival_time transfer_before_minutes station_buffer_minutes transfer_after_minutes baggage_minutes lodging_buffer_minutes ticket_total price_source context kind revision day_index hint day_detail days_detail cities selected_edge_index locked_attraction_names removed_attraction_names rest_periods start_minutes end_minutes start_time end_time duration name attractions visit_duration ticket_price open_hours meals category schedule_mode preferred_slot estimated_cost avg_cost timeline_order timeline_schedule ref_name phase hotel route_segments from_name to_name distance is_estimated day_start_time recommendation reasons ranked_by recommendations candidate leg message read_count eligible_count excluded_count checked_schedule fit_count excluded candidate_id eligible margins tight ids attractions_order insert_after meal_adjustments reason kept removed changed final_minutes delta_minutes baseline_minutes must_improve violations matched_permutation eligible_ids false_accepts false_rejects precision recall model_order final_order latest_hash before_hash after_hash persisted checkpoint_statuses'.split())
FACT_KEYS |= set('saved_state plan snapshots stops transfers from_stop to_stop stop_id origin destination timezone default_day_start_time label departure_station arrival_station departure_timezone arrival_timezone service_number seat_class currency extras_total connections booking_status quoted_at'.split())
SENSITIVE_KEY = re.compile(r'key|secret|password|authorization|cookie|email|phone|token|user_id|draft_id|path|url', re.I)


def safe_text(value):
    text = str(value)
    text = re.sub(r'(?i)(?:sk-|lsv2_)[a-z0-9_-]{8,}', '[REDACTED]', text)
    text = re.sub(r'(?i)\bBearer\s+\S+', '[REDACTED]', text)
    text = re.sub(r'(?i)(api[_ -]?key|password|secret|authorization)\s*[:=]\s*[^\s,;]+', r'\1=[REDACTED]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', '[EMAIL]', text)
    text = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '[PHONE]', text)
    text = re.sub(r'https?://[^\s<>"\']+', '[URL]', text)
    text = re.sub(r'(?:/Users/|/home/|/tmp/|[A-Z]:\\)[^\s"\']*', '[LOCAL_PATH]', text)
    return text[:12000]


def clean(value, *, facts=False, depth=0):
    if depth > 20:
        return '[DEPTH_LIMIT]'
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, list):
        return [clean(v, facts=facts, depth=depth+1) for v in value[:500]]
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if (facts and k not in FACT_KEYS) or SENSITIVE_KEY.search(k):
                continue
            if facts and k == 'snapshots' and isinstance(v, dict):
                result[k] = [{'stop_id': safe_text(key), 'snapshot': clean(item, facts=True, depth=depth+1)} for key, item in v.items()]
            elif k == 'id' and isinstance(v, str) and (v.startswith(('mc_', 'eval_')) or re.fullmatch(r'[a-f0-9-]{32,36}', v)):
                result[k] = 'anon_' + hashlib.sha256(v.encode()).hexdigest()[:24]
            else:
                result[safe_text(k)] = clean(v, facts=facts, depth=depth+1)
        return result
    return None


def tally(checks):
    counter = Counter(c['status'] for c in checks)
    result = {short: counter[long] for long, short in STATUS_KEYS.items()}
    result['applicable'] = sum(result[k] for k in ('P', 'F', 'E', 'U'))
    return result


def metric_groups(rows):
    groups = {key: [] for key in ('system_constraints', 'model_raw', 'task_quality', 'observability', 'injected_model')}
    for row in rows:
        for check in row['checks']:
            if check['layer'] == 'model':
                if row['provenance'] == 'live_model_with_replay':
                    groups['model_raw'].append(check)
                elif row['provenance'] == 'injected_failure':
                    groups['injected_model'].append(check)
            elif check['rule_id'] in QUALITY_RULES:
                groups['task_quality'].append(check)
            elif check['layer'] == 'observability':
                groups['observability'].append(check)
            else:
                groups['system_constraints'].append(check)
    return {key: tally(value) for key, value in groups.items()}


def summary(rows):
    completed = [r for r in rows if r['execution_state'] == 'COMPLETED']
    live = [r for r in rows if r['provenance'] == 'live_model_with_replay']
    checks = [c for r in rows for c in r['checks']]
    outcomes = [c for c in checks if c['rule_id'] == 'T-OUTCOME' and c['layer'] == 'system']
    # Operation time, not process startup; retain timeout/cancel in rows, not success percentiles.
    walls = sorted(r['wall_seconds'] for r in completed if r['operation_status'] == 'success' and r['wall_seconds'] is not None)
    percentile = lambda p: walls[max(0, math.ceil(len(walls)*p)-1)] if walls else None
    usage_rows = [r for r in live if r['usage'] is not None]
    costs = [r['cost_usd'] for r in live if r['cost_usd'] is not None]
    categories = {key: sum(key in r['categories'] for r in rows) for key in CATEGORIES}
    return dict(planned=len(rows), completed=len(completed), unique_cases=len({r['case_id'] for r in rows}),
        not_applicable=sum(r['execution_state'] == 'NOT_APPLICABLE' for r in rows),
        incomplete=sum(r['execution_state'] not in {'COMPLETED', 'NOT_APPLICABLE'} for r in rows),
        real_requests=sum(r['actual_requests'] for r in rows), real_model_runs=len(live),
        technical_errors=sum(r['operation_status'] in {'error', 'timeout'} for r in completed),
        fallback=sum(r['business_outcome'] == 'fallback' for r in completed),
        outcome_pass=sum(c['status'] == 'PASS' for c in outcomes), outcome_applicable=sum(c['status'] != 'NOT_APPLICABLE' for c in outcomes),
        outcome_scope='T-OUTCOME 票务诊断；每日需求另见 R-INTENT',
        finding_runs=sum(any(c['status'] in {'FAIL', 'ERROR'} for c in r['checks']) for r in rows),
        finding_cases=len({r['case_id'] for r in rows if any(c['status'] in {'FAIL', 'ERROR'} for c in r['checks'])}),
        injected_runs=sum(r['provenance'] == 'injected_failure' for r in rows), categories=categories,
        tokens=sum(r['usage']['total_tokens'] for r in usage_rows), usage_known_runs=len(usage_rows),
        cost_usd=sum(costs) if costs or not live else None, cost_known_runs=len(costs),
        peak_cost_usd=(sum(r['peak_cost_usd'] for r in live if r['peak_cost_usd'] is not None) if any(r['peak_cost_usd'] is not None for r in live) else None if live else 0),
        wall_p50=percentile(.5), wall_p95=percentile(.95), wall_count=len(walls), p95_small_sample=len(walls)<20,
        diagnostic_counts=tally(checks), metrics=metric_groups(rows), formal_quality_score=None,
        formal_quality_status='NOT_EVALUATED', pending_cases=len({r['case_id'] for r in rows if r['reference_status'] != 'confirmed'}))


def enabled():
    return os.environ.get('QUALITY_WORKBENCH_ENABLED', '').lower() in {'1', 'true', 'yes'}


def directory():
    return Path(os.environ.get('QUALITY_REPORT_DIR') or Path.home()/'.local/share/langgraph-trip-planner/quality-workbench').expanduser()


@lru_cache(maxsize=8)
def _read_snapshot(path, mtime, size):
    if size > 30*1024*1024:
        raise ValueError('oversized snapshot')
    obj = json.loads(Path(path).read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite value')))
    if obj.get('schema') != SCHEMA or not isinstance(obj.get('runs'), list):
        raise ValueError('invalid snapshot')
    if not re.fullmatch(r'eval_[a-f0-9]{32}', obj.get('experiment_id', '')):
        raise ValueError('invalid experiment identity')
    for key in ('created_at', 'published_at', 'dataset_sha256', 'evaluator_versions', 'fixture_sha256'):
        if key not in obj:
            raise ValueError('missing snapshot metadata')
    for row in obj['runs']:
        required = {'run_id', 'case_id', 'variant', 'repetition', 'input_sha256', 'checks', 'detail', 'execution_state', 'provenance', 'categories', 'reference_status', 'actual_requests', 'usage', 'cost_usd', 'peak_cost_usd', 'operation_status', 'business_outcome', 'wall_seconds', 'started_at'}
        if not isinstance(row, dict) or not required <= row.keys():
            raise ValueError('incomplete row')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', row['run_id']) or not isinstance(row['checks'], list) or not isinstance(row['detail'], dict):
            raise ValueError('invalid row')
        for check in row['checks']:
            if check.get('status') not in STATUS_KEYS or not check.get('rule_id') or check.get('layer') not in {'model', 'system', 'observability', 'judge'}:
                raise ValueError('invalid check')
    if len({r['run_id'] for r in obj['runs']}) != len(obj['runs']):
        raise ValueError('duplicate run identity')
    return obj


def snapshots():
    """Bounded published files only; no arbitrary path query or original evidence serving."""
    records, invalid = [], 0
    root = directory().resolve()
    if not root.is_dir():
        return [], 0
    for path in sorted(root.glob('eval_*.json'))[:20]:
        if path.is_symlink() or path.resolve().parent != root:
            invalid += 1
            continue
        try:
            stat = path.stat()
            records.append(_read_snapshot(str(path), stat.st_mtime_ns, stat.st_size))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            invalid += 1
    return sorted(records, key=lambda d: d['created_at'], reverse=True), invalid


def select(snapshot, filters):
    result = snapshot['runs']
    for field in ('variant', 'target', 'split', 'data_origin', 'provenance', 'operation_status', 'business_outcome'):
        if filters.get(field):
            result = [r for r in result if r.get(field) == filters[field]]
    if filters.get('category'):
        result = [r for r in result if filters['category'] in r['categories']]
    if filters.get('findings'):
        result = [r for r in result if any(c['status'] in {'FAIL', 'ERROR'} for c in r['checks'])]
    if filters.get('q'):
        q = filters['q'].casefold()
        result = [r for r in result if q in (r['case_id']+' '+r['title']+' '+r['run_id']).casefold()]
    for field, op in [('since', lambda a, b: a >= b), ('until', lambda a, b: a <= b)]:
        if filters.get(field):
            result = [r for r in result if r['started_at'] and op(r['started_at'][:10], filters[field])]
    return result


def row_public(row):
    return {k: v for k, v in row.items() if k not in {'detail', 'checks'}} | {'counts': tally(row['checks'])}


def compare(left, right, left_variant, right_variant, filters=None):
    signature = ('dataset_sha256', 'evaluator_versions', 'fixture_sha256')
    compatible = all(left[k] == right[k] for k in signature)
    lrows = select(left, {**(filters or {}), 'variant': left_variant})
    rrows = select(right, {**(filters or {}), 'variant': right_variant})
    lmap = {(r['case_id'], r['repetition']): r for r in lrows}
    rmap = {(r['case_id'], r['repetition']): r for r in rrows}
    pairs = []
    for identity in sorted(lmap.keys() | rmap.keys()):
        a, b = lmap.get(identity), rmap.get(identity)
        comparable = bool(compatible and a and b and a['input_sha256'] == b['input_sha256'] and a['execution_state'] == b['execution_state'] == 'COMPLETED')
        changes = []
        if comparable:
            ac = {(c['rule_id'], c['layer']): c for c in a['checks']}
            bc = {(c['rule_id'], c['layer']): c for c in b['checks']}
            for key in sorted(ac.keys() | bc.keys()):
                x, y = ac.get(key, {}).get('status'), bc.get(key, {}).get('status')
                kind = 'unknown'
                if x in {'PASS', 'FAIL'} and y in {'PASS', 'FAIL'}:
                    kind = 'unchanged' if x == y else 'improved' if y == 'PASS' else 'regressed'
                changes.append(dict(rule_id=key[0], layer=key[1], left=x, right=y, change=kind))
        pairs.append(dict(case_id=identity[0], repetition=identity[1], left=a['run_id'] if a else None,
            right=b['run_id'] if b else None, comparable=comparable, changes=changes,
            reason=None if comparable else '版本/输入不同、缺配对或该槽未完成/不适用'))
    return dict(compatible=compatible, diagnostic_only=True, formal_delta=None,
        pairing='case_id + repetition + input_sha256；基线第 1 次不复制成 3 次',
        left_experiment=left['experiment_id'], right_experiment=right['experiment_id'],
        left_summary=summary(lrows), right_summary=summary(rrows), pairs=pairs,
        comparable_pairs=sum(p['comparable'] for p in pairs),
        missing_pairs=sum(p['left'] is None or p['right'] is None for p in pairs))
