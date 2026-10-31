"""Publish a sanitized, immutable P3 snapshot for the read-only P4 UI (no model calls)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from app.services.quality_reports import SCHEMA, clean, safe_text, summary


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def within(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('evidence outside experiment')
    return path


def build_snapshot(root, audit_path, annotations_path):
    root = Path(root).resolve()
    plan, report, ledger = (read(root/n) for n in ('manifest.json', 'report.json', 'ledger.json'))
    audit = read(Path(audit_path)) if audit_path else None
    annotations = read(Path(annotations_path)) if annotations_path else {}
    if not (plan['plan_sha256'] == report['plan_sha256'] == ledger['plan_sha256']):
        raise ValueError('report/plan mismatch')
    if annotations and annotations['plan_sha256'] != plan['plan_sha256']:
        raise ValueError('triage belongs to another plan')
    if audit and (audit['plan_sha256'] != plan['plan_sha256'] or audit['actual_live_requests'] != report['actual_live_model_requests']):
        raise ValueError('usage audit mismatch')
    for name, expected in plan['source_files'].items():
        if sha(within(root/'source', name)) != expected:
            raise ValueError('frozen source changed')
    reports = {r['slot_id']: r for r in report['results']}
    receipts = {}
    for request in (audit or {}).get('requests', []):
        receipts.setdefault(request['slot_id'], []).append(request)
    rows = []
    for slot in plan['slots']:
        sid = slot['slot_id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', sid):
            raise ValueError('unsafe slot identity')
        result = reports[sid]
        entry = ledger['slots'].get(sid, {'state': 'NOT_RUN'})
        case_path = within(root/'source/evals/datasets', 'cases/'+slot['case_id']+'.json')
        case = read(case_path)
        inp = read(within(case_path.parent.parent, case['input_path']))
        obs = {}
        eng = {}
        if entry['state'] == 'COMPLETED':
            op = within(root, f'slots/{sid}/observation.json')
            ep = within(root, f'slots/{sid}/engineering.json')
            if sha(op) != entry['observation_sha256'] or sha(ep) != entry['engineering_sha256']:
                raise ValueError('observation/engineering changed')
            obs = read(op)
            eng = read(ep)
            if obs['input_sha256'] != case['input_sha256'] or obs['run_id'] != sid:
                raise ValueError('observation identity mismatch')
        provenance = obs.get('provenance') or ('baseline' if slot['variant'] == 'baseline' else case['execution_mode'])
        checks = []
        # P4 never promotes unreviewed references, even if an input report incorrectly marks them formal.
        source_checks = result.get('diagnostic_checks', []) + result.get('formal_checks', [])
        for original in source_checks:
            c = {key: clean(original.get(key)) for key in ('rule_id', 'layer', 'status', 'score', 'expected', 'actual', 'reason', 'evaluator_version')}
            c['evidence_paths'] = [safe_text(p) for p in original.get('evidence_paths', [])]
            c['category'] = None
            c['triage_note'] = None
            if c['status'] in {'FAIL', 'ERROR'}:
                triage = next((a for a in annotations.get('findings', []) if a['case_id'] == case['case_id'] and c['rule_id'] in a['rules'] and slot['variant'] in a['variants']), None)
                c['category'] = ('fault_injection' if provenance == 'injected_failure' and not triage else triage['category'] if triage else 'evidence_gap' if c['status'] == 'ERROR' else 'unclassified')
                c['triage_note'] = safe_text(triage['note']) if triage else None
            checks.append(c)
        trace = obs.get('trace') or {}
        spans = [{key: clean(s.get(key)) for key in ('id', 'parent_id', 'name', 'run_type', 'start_time', 'end_time', 'status', 'milliseconds', 'facts')} for s in trace.get('spans', [])]
        for projected, original in zip(spans, trace.get('spans', [])):
            for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                number = original.get('facts', {}).get(key)
                if type(number) is int and number >= 0:
                    projected['facts'][key] = number
        # Usage has its own explicit projection; the broad fact sanitizer deliberately drops token-like keys.
        calls = receipts.get(sid, [])
        if audit and len(calls) != eng.get('actual_live_model_requests', 0):
            raise ValueError('slot request count mismatch')
        if audit and calls:
            if [c['provider_usage'] for c in calls] != [c['usage'] for c in eng['model_receipts']]:
                raise ValueError('provider usage changed')
        usage = obs.get('usage')
        usage = {k: usage.get(k) for k in ('input_tokens', 'output_tokens', 'total_tokens')} if usage else None
        categories = sorted({c['category'] for c in checks if c['category']} | ({'fault_injection'} if provenance == 'injected_failure' else set()))
        raw_trace = dict(operation_id=trace.get('operation_id'), session_alias=trace.get('session_alias'), spans=spans,
            status='local_only' if spans else 'missing', cloud_status='not_exported' if not plan['trace_export'] else 'unverified', langsmith_url=None)
        row = dict(run_id=sid, case_id=case['case_id'], title=safe_text(case['title']), variant=slot['variant'],
            repetition=slot['repetition'], target=case['target'], split=case['split'], data_origin=case['data_origin'],
            provenance=provenance, tool_mode=case['tool_mode'], input_sha256=case['input_sha256'],
            case_version=case['case_version'], reference_status=case['annotation']['status'], diagnostic_only=True,
            formal_quality_score=None, execution_state=entry['state'], operation_status=obs.get('execution_status'),
            business_outcome=obs.get('business_outcome'), started_at=spans[0]['start_time'] if spans else None,
            wall_seconds=obs.get('timings', {}).get('operation_wall_seconds'), usage=usage,
            actual_requests=len(calls) if audit else (read(root/f'slots/{sid}/engineering.json').get('actual_live_model_requests', 0) if obs else 0),
            cost_usd=sum(c['cost_from_usage_usd'] for c in calls) if calls and all(c.get('cost_from_usage_usd') is not None for c in calls) else (0 if provenance != 'live_model_with_replay' else None),
            peak_cost_usd=sum(c['peak_cache_miss_upper_usd'] for c in calls) if calls else None,
            categories=categories, checks=checks, trace_status=raw_trace['status'],
            detail=dict(inputs=clean(inp, facts=True), before=clean(obs.get('before_state'), facts=True),
                latest=clean(obs.get('latest_state'), facts=True), after=clean(obs.get('after_state'), facts=True),
                raw_model=clean(obs.get('raw_model'), facts=True), final_output=clean(obs.get('final_output'), facts=True),
                candidate_checks=clean(obs.get('candidate_checks'), facts=True), trace=raw_trace,
                sources=clean(case['sources']), annotation=clean(case['annotation']),
                http_status=obs.get('http_status'), checkpoint_statuses=clean(obs.get('checkpoint_statuses')),
                input_sha256=case['input_sha256'], reference_sha256=case['reference_sha256']))
        rows.append(row)
    if audit:
        if sum(r['actual_requests'] for r in rows) != audit['actual_live_requests']:
            raise ValueError('request count mismatch')
        if sum((r['usage'] or {}).get('total_tokens', 0) for r in rows if r['provenance'] == 'live_model_with_replay') != audit['usage']['total_tokens']:
            raise ValueError('usage mismatch')
    return dict(schema=SCHEMA, experiment_id=plan['experiment_id'], created_at=datetime.fromtimestamp(plan['created_at'], timezone.utc).isoformat(),
        published_at=datetime.now(timezone.utc).isoformat(), title='首期 30 例 · 真实模型诊断' if audit else '工程回放诊断',
        report_sha256=sha(root/'report.json'), ledger_sha256=sha(root/'ledger.json'),
        usage_audit_sha256=sha(Path(audit_path)) if audit_path else None,
        plan_sha256=plan['plan_sha256'], source_sha256=plan['source_sha256'], dataset_sha256=plan['dataset_sha256'],
        fixture_sha256=hashlib.sha256(json.dumps({k:v for k,v in plan['source_files'].items() if '/datasets/' in k},sort_keys=True).encode()).hexdigest(),
        evaluator_versions=sorted({c['evaluator_version'] for r in rows for c in r['checks'] if c['evaluator_version']}),
        case_versions=sorted({r['case_version'] for r in rows}), model=clean(plan['model']),
        formal_quality_status='NOT_EVALUATED', formal_quality_score=None,
        pricing=dict(invoice_verified=False, basis='实际 usage + 周末非峰时/缓存费率；未核对账单' if audit else '没有真实模型计费',
            source_url='https://api-docs.deepseek.com/quick_start/pricing/' if audit else None,
            checked_on=(audit or {}).get('pricing_checked_on'), budget_usd=plan.get('limits', {}).get('max_cost'),
            input_tokens=(audit or {}).get('usage', {}).get('input_tokens'), output_tokens=(audit or {}).get('usage', {}).get('output_tokens'),
            cache_read_tokens=(audit or {}).get('usage', {}).get('cache_read_tokens')),
        limitations=['30 份参考待人工确认；所有指标只作诊断，正式质量未评估。', '真实模型 + 冻结外部事实回放；未重新查票/地图/酒店核价。', 'dev/holdout 为场景分组，来源家族仍待复核，不代表独立泛化验证。', '本批次未上传 LangSmith；仅展示已采集的本地 Trace。'],
        runs=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--usage-audit', type=Path)
    parser.add_argument('--annotations', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document = build_snapshot(args.experiment, args.usage_audit, args.annotations)
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = args.output/(document['experiment_id']+'.json')
    # New imports are explicit. Never overwrite a previously published snapshot.
    with path.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    path.chmod(0o600)
    print(json.dumps({'published':str(path),'runs':len(document['runs']),'summary':summary(document['runs'])},ensure_ascii=False))


if __name__ == '__main__':
    main()
