"""Authorized v2.1 paired route-input experiments; no implicit paid calls."""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import time
import uuid

from . import conditional_live as common
from .budget import estimated_cost, prompt_bound
from .conditional_v21 import load_cases, profile_inputs, score
from .contracts import digest
from .dataset import load_case, read_json
from .experiment import atomic, sha, source_files, ROOT
from .prompt_variants import ablate, VERSION as ABLATION_VERSION
from .scorers import MissingEvidence, route_facts

VERSION = 'conditional-v21-live-v1'
ADAPTER_CHANGES = {'evals/worker.py','evals/conditional_live.py'}
MODEL_PROFILES = {'PS03','PS05','PS12'}
HOLIDAY_SOURCE = 'https://www.beijing.gov.cn/cs/gncs/zcwj/202603/t20260327_4568275.html'
NON_HOLIDAYS = {'2026-10-26'}


def slot_specs(quote):
    rows = {r['unit_id']:r for r in quote['rows']}
    return [dict(s,model_path=rows[s['unit_id']]['model_path'],bundle=rows[s['unit_id']]['bundle']) for s in quote['slots']]


def load_quote(path):
    q = read_json(path); raw = dict(q); wanted = raw.pop('estimate_sha256')
    if digest(raw) != wanted or q['schema'] != 'conditional-v21-budget-proposal-v1':
        raise ValueError('v2.1 estimate hash/schema mismatch')
    if q['model'] != common.MODEL or q['rates']['model'] != 'deepseek-flash' or q['rates']['currency'] != 'USD':
        raise ValueError('v2.1 quoted model/currency mismatch')
    rates = {**common.PEAK_RATES,'input_miss_off_peak_per_million':.15,
             'input_hit_off_peak_per_million':.003,'output_off_peak_per_million':.6}
    if any(q['rates'].get(k) != v for k,v in rates.items()):raise ValueError('quoted rates changed')
    cases = load_cases()
    if q['conditional_data_sha256'] != digest(cases):raise ValueError('v2.1 data/reference drift')
    expected_units = []
    for c in cases:
        for variant in (['route_enriched','route_ablated'] if c['id']=='PS12' else ['current']):
            expected_units.append(c['id'] if variant=='current' else c['id']+'_'+variant)
    if [r['unit_id'] for r in q['rows']] != expected_units:raise ValueError('quoted unit scope/order changed')
    for row in q['rows']:
        c = next(c for c in cases if c['id']==row['profile_id'])
        base,_,_,_ = load_case(c['source_id']); live = c['id'] in MODEL_PROFILES
        reps = 5 if c['id']=='PS12' else 1; attempts = (2 if c['id']=='PS12' else 1) if live else 0
        expected = dict(source_id=c['source_id'],source_family=c['source_family'],source_split=c['source_split'],
            data_origin=base.data_origin,case_version='2.1-draft-'+c['id'],input_sha256=digest(profile_inputs(c)),
            reference_status=c['annotation']['status'],reference_sha256=c['reference_sha256'],model_path=live,
            repetitions=reps,max_attempts_per_slot=attempts,max_requests=attempts*reps,
            nominal_requests=reps if live else 0,max_output_tokens=8192 if live else 0,
            bundle=f"input-bundles/{c['id']}.json")
        if any(row.get(k) != v for k,v in expected.items()):raise ValueError('quoted profile input/limits changed')
        variant = row['unit_id'].removeprefix('PS12_') if c['id']=='PS12' else 'current'
        if row['variant'] != variant:raise ValueError('quoted intervention changed')
        n = row['input_reservation_per_request']
        if type(n) is not int or n < 0 or (not live and n):raise ValueError('invalid input reservation')
        tokens = attempts*(n+row['max_output_tokens'])
        cost = estimated_cost(attempts*n,attempts*row['max_output_tokens'],q['rates'])
        if tokens != row['max_tokens_per_slot'] or not math.isclose(cost,row['max_cost_per_slot'],abs_tol=1e-10):
            raise ValueError('per-slot reservation changed')
    expected_slots = [dict(slot_id=r['unit_id']+'-1',unit_id=r['unit_id'],profile_id=r['profile_id'],
                           variant=r['variant'],repetition=1) for r in q['rows'] if r['profile_id']!='PS12']
    for rep in range(1,6):
        for variant in (['route_enriched','route_ablated'] if rep%2 else ['route_ablated','route_enriched']):
            unit='PS12_'+variant
            expected_slots.append(dict(slot_id=unit+f'-{rep}',unit_id=unit,profile_id='PS12',variant=variant,repetition=rep))
    total_tokens = sum(r['max_tokens_per_slot']*r['repetitions'] for r in q['rows'])
    cost = sum(r['max_cost_per_slot']*r['repetitions'] for r in q['rows'])
    if (q['slots'] != expected_slots or q['planned_slots'] != 21 or q['nominal_live_requests'] != 12
            or q['max_live_requests'] != 22 or q['reservation']['max_requests'] != 22
            or q['reservation']['total_tokens'] != total_tokens or total_tokens != 385862
            or not math.isclose(cost,q['reservation']['calculated_peak_cost_usd'],abs_tol=1e-10)
            or cost > q['reservation']['requested_budget_usd'] or q['reservation']['requested_budget_usd'] != .30
            or q['concurrency'] != 1 or not 0 < q['slot_seconds'] <= 120 or not 0 < q['wall_seconds'] <= 3600):
        raise ValueError('aggregate scope/budget changed')
    if q['prompt_intervention']['version'] != ABLATION_VERSION:raise ValueError('ablation version changed')
    return q


def validate_assets(q, base):
    for rel,want in q['assets'].items():
        if sha(common.inside(base,rel)) != want:raise ValueError('quoted asset changed')
    for row in q['rows']:
        c = next(c for c in load_cases() if c['id']==row['profile_id'])
        original,_,_,routes = load_case(c['source_id'])
        header = {k:original.model_dump(mode='json')[k] for k in
                  ['case_id','case_version','input_sha256','clock','data_origin','execution_mode']}
        header.update(case_version=row['case_version'],input_sha256=row['input_sha256'],
                      execution_mode='live_model_with_replay' if row['model_path'] else 'no_model')
        if read_json(base/row['bundle']) != dict(case=header,inputs=profile_inputs(c),routes=routes):
            raise ValueError('worker bundle does not match approved input')
        if row['model_path']:
            prompt = read_json(base/'prompts'/f"{row['unit_id']}.json")
            if digest(prompt) != row['prompt_sha256'] or prompt_bound(prompt) != row['input_reservation_per_request']:
                raise ValueError('quoted prompt changed')
    enriched = read_json(base/'prompts/PS12_route_enriched.json')
    control = read_json(base/'prompts/PS12_route_ablated.json')
    if ablate(enriched) != control:raise ValueError('control is not the approved single ablation')
    def body(source):
        node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='ablate')
        return ast.dump(node,include_attributes=False)
    if body((base/'scripts/prompt_ablation.py').read_text()) != body(Path(__file__).with_name('prompt_variants.py').read_text()):
        raise ValueError('ablation implementation changed since quote')


def prepare(directory, quote_file):
    directory=Path(directory).resolve();quote_file=Path(quote_file).resolve()
    if directory.exists() or directory.is_relative_to(ROOT):raise ValueError('choose a fresh outside directory')
    q=load_quote(quote_file);validate_assets(q,quote_file.parent)
    baseline=read_json(common.inside(quote_file.parent,q['source_manifest']))
    if digest(baseline['source_files']) != q['source_sha256'] or common.packages() != baseline['packages']:
        raise ValueError('approved source/runtime mismatch')
    for rel,want in baseline['source_files'].items():
        if rel not in ADAPTER_CHANGES and sha(ROOT/'backend'/rel) != want:
            raise ValueError('product/evaluator drift since approval: '+rel)
    directory.mkdir(parents=True,mode=0o700);(directory/'slots').mkdir()
    files={}
    for path in source_files():
        rel=str(path.relative_to(ROOT/'backend'));target=directory/'source'/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes());files[rel]=sha(target)
    for rel in q['assets']:
        target=common.inside(directory/'quoted',rel);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(common.inside(quote_file.parent,rel).read_bytes())
    atomic(directory/'estimate.json',q);atomic(directory/'approved-source-manifest.json',baseline)
    plan=dict(schema=VERSION,experiment_id='eval_v21_'+uuid.uuid4().hex,created_at=time.time(),
        estimate_sha256=q['estimate_sha256'],estimate_file_sha256=sha(directory/'estimate.json'),
        source_sha256=digest(files),source_files=files,packages=common.packages(),python=sys.version,
        approved_source_manifest_sha256=sha(directory/'approved-source-manifest.json'),
        locks=baseline['dependency_locks'],slots=slot_specs(q),model=q['model'],rates=q['rates'],limits=q['reservation'],
        concurrency=1,slot_seconds=q['slot_seconds'],wall_seconds=q['wall_seconds'],
        judge_enabled=False,cloud_uploads=False,formal_quality_score=None,
        billing_calendar=dict(verified_nonholiday_dates=sorted(NON_HOLIDAYS),source=HOLIDAY_SOURCE))
    plan['plan_sha256']=digest(plan);atomic(directory/'manifest.json',plan)
    atomic(directory/'ledger.json',dict(plan_sha256=plan['plan_sha256'],slots={},wall_seconds_spent=0))
    return plan


def verified(directory):
    directory=Path(directory).resolve();p=read_json(directory/'manifest.json');raw=dict(p);want=raw.pop('plan_sha256')
    if digest(raw) != want or p['schema'] != VERSION:raise ValueError('frozen v2.1 plan changed')
    if sha(directory/'estimate.json') != p['estimate_file_sha256']:raise ValueError('frozen estimate changed')
    q=load_quote(directory/'estimate.json');validate_assets(q,directory/'quoted')
    if (q['estimate_sha256'] != p['estimate_sha256'] or p['slots'] != slot_specs(q)
            or p['model'] != q['model'] or p['rates'] != q['rates'] or p['limits'] != q['reservation']
            or p['concurrency'] != 1 or p['slot_seconds'] != q['slot_seconds'] or p['wall_seconds'] != q['wall_seconds']
            or p['judge_enabled'] or p['cloud_uploads']):raise ValueError('execution boundary changed')
    if p['billing_calendar'] != dict(verified_nonholiday_dates=sorted(NON_HOLIDAYS),source=HOLIDAY_SOURCE):
        raise ValueError('billing calendar evidence changed')
    if common.packages() != p['packages'] or digest(p['source_files']) != p['source_sha256']:
        raise ValueError('runtime changed')
    for rel,want in p['source_files'].items():
        if sha(common.inside(directory/'source',rel)) != want or sha(ROOT/'backend'/rel) != want:
            raise ValueError('frozen/active source changed')
    for rel,want in p['locks'].items():
        if sha(ROOT/rel) != want:raise ValueError('dependency lock changed')
    if sha(directory/'approved-source-manifest.json') != p['approved_source_manifest_sha256']:
        raise ValueError('approved source manifest changed')
    return p,q


def execute(directory, **kwargs):
    p,q=verified(directory)
    return common.execute_frozen(directory,p,q,reporter=report,**kwargs)


def measured_cost(receipt,rates,non_holidays):
    u=receipt.get('usage')
    if not u:return None
    provider=receipt.get('provider_cache_tokens') or {};hit=(u.get('input_token_details') or {}).get('cache_read',provider.get('prompt_cache_hit_tokens'))
    if type(hit) is not int or not 0 <= hit <= u['input_tokens']:return None
    miss=u['input_tokens']-hit
    if provider.get('prompt_cache_hit_tokens',hit) != hit or provider.get('prompt_cache_miss_tokens',miss) != miss:return None
    def period(stamp):
        d=datetime.fromtimestamp(stamp,timezone.utc)
        if d.weekday() >= 5 or d.hour not in {1,2,3,6,7,8,9}:return 'off_peak'
        return 'peak' if d.date().isoformat() in non_holidays else None
    start,end=period(receipt['started_at']),period(receipt['finished_at'])
    if start is None or start != end:return None
    return (hit*rates[f'input_hit_{start}_per_million']+miss*rates[f'input_miss_{start}_per_million']
            +u['output_tokens']*rates[f'output_{start}_per_million'])/1000000


def route_metrics(inputs,routes,observation,checks):
    if observation.get('execution_status') != 'success' or not observation.get('final_output'):
        return dict(classification='rejected' if observation.get('execution_status') in {'rejected','conflict'} else 'execution_error')
    day=observation['final_output']
    try:
        total,errors=route_facts(day,routes);baseline,_=route_facts(inputs['day_detail'],routes)
        hard=[c for c in checks if c['layer']=='system' and c['rule'] in {
            'R-LOCK','R-REMOVED','R-MEAL','R-MANUAL','R-FACT','R-DURATION','R-REST','R-WINDOW'}]
        valid=(len(hard)==8 and all(c['status']=='PASS' for c in hard) and not errors)
        lookup={(e['from'],e['to']):e for e in routes['edges']}
        seconds=lambda detail:sum(lookup[s['from_name'],s['to_name']]['duration_seconds'] for s in detail['route_segments'])
        timeline=day['timeline_schedule'];end=max(r['end_minutes'] for r in timeline)
        return dict(classification='improved' if valid and total<baseline else 'not_improved' if valid else 'invalid_or_unverified_constraints',
            baseline_traffic_minutes=baseline,traffic_minutes=total,delta_minutes=baseline-total,
            baseline_seconds=seconds(inputs['day_detail']),traffic_seconds=seconds(day),
            hard_constraints_valid=valid,route_errors=errors,end_minutes=end,
            end_time=f'{end//60:02d}:{end%60:02d}',wait_minutes=sum(r['end_minutes']-r['start_minutes'] for r in timeline if r['kind']=='wait'),
            attraction_order=[a['name'] for a in day['attractions']],meal_names=[m['name'] for m in day['meals']])
    except (KeyError,TypeError,ValueError,MissingEvidence):return dict(classification='evidence_error')


def report(directory):
    directory=Path(directory).resolve();p,q=verified(directory);ledger=read_json(directory/'ledger.json')
    profiles={c['id']:c for c in load_cases()};results=[];receipts=[]
    for slot in p['slots']:
        entry=ledger['slots'].get(slot['slot_id'],dict(state='NOT_RUN'));origin=next(r for r in q['rows'] if r['unit_id']==slot['unit_id'])
        c=profiles[slot['profile_id']];work=directory/'slots'/slot['slot_id']
        row=dict(**slot,execution_state=entry['state'],reference_status=c['annotation']['status'],diagnostic_only=True,
            formal_checks=[],formal_quality_score=None,checks=[],source_id=c['source_id'],source_family=c['source_family'],
            source_split=c['source_split'],data_origin=origin['data_origin'],
            actual_live_model_requests=0 if not slot['model_path'] or entry['state']=='NOT_RUN' else None)
        if entry['state']=='COMPLETED':
            for name,want in entry['evidence'].items():
                if sha(common.inside(work,name)) != want:raise ValueError('completed evidence changed')
            obs=read_json(work/'observation.json');e=read_json(work/'engineering.json');bundle=read_json(directory/'quoted'/slot['bundle'])
            try:
                scored=score(c,obs,diagnostic=True);row['checks']=[dict(check,layer='system') for check in scored['checks']]
                if slot['model_path']:bundle['prompt']=read_json(directory/'quoted/prompts'/f"{slot['unit_id']}.json")
                row['checks']+=common.extra_checks(c,obs,bundle,slot['model_path'],scorer=score)
            except (KeyError,TypeError,ValueError,MissingEvidence):row['checks'].append(dict(rule='scoring_evidence',layer='engineering',status='ERROR'))
            actual=e['actual_live_model_requests'];r=e.get('model_receipts',[])
            good=(1<=actual<=origin['max_attempts_per_slot'] and len(r)==actual and e['model_substitute_calls']==0
                  and obs['provenance']=='live_model_with_replay') if slot['model_path'] else (
                      actual==e['model_substitute_calls']==0 and obs['provenance']=='no_model')
            row['checks'].append(dict(rule='expected_execution_transport',layer='engineering',status='PASS' if good else 'FAIL'))
            if slot['model_path']:
                bound=(len(e['captured_prompts'])==actual and all(digest(m)==origin['prompt_sha256'] for m in e['captured_prompts'])
                       and all(v['prompt_sha256']==origin['prompt_sha256'] for v in r))
                row['checks'].append(dict(rule='approved_prompt_variant',layer='engineering',status='PASS' if bound else 'FAIL'))
            receipts += [dict(v,slot_id=slot['slot_id'],unit_id=slot['unit_id'],variant=slot['variant']) for v in r]
            row.update(actual_live_model_requests=actual,usage=obs['usage'],raw_model=obs['raw_model'],
                operation_status=obs['execution_status'],model_status=obs['model_status'],outcome=obs['business_outcome'],
                evidence=f"slots/{slot['slot_id']}/observation.json",local_trace=f"slots/{slot['slot_id']}/traces/operations/{obs['trace_id']}.json" if obs.get('trace_id') else None,
                selected_ids=[v['candidate']['id'] for v in (obs['final_output'] or {}).get('recommendations',[])])
            if c['id']=='PS12':row['route_metrics']=route_metrics(bundle['inputs'],bundle['routes'],obs,row['checks'])
        else:row['checks']=[dict(rule='execution',layer='engineering',status='ERROR',actual=entry['state'])]
        results.append(row)
    usage={k:sum(r['usage'][k] for r in receipts) for k in ['input_tokens','output_tokens','total_tokens']} if receipts and all(r['usage'] for r in receipts) else None
    costs=[measured_cost(r,p['rates'],p['billing_calendar']['verified_nonholiday_dates']) for r in receipts]
    arms=[]
    for variant in ['route_enriched','route_ablated']:
        subset=[r for r in results if r['profile_id']=='PS12' and r['variant']==variant]
        arms.append(dict(variant=variant,planned=5,completed=sum(r['execution_state']=='COMPLETED' for r in subset),
            classifications=dict(Counter(r.get('route_metrics',{}).get('classification',r['execution_state'].lower()) for r in subset)),
            rows=[dict(slot_id=r['slot_id'],metrics=r.get('route_metrics'),operation_status=r.get('operation_status')) for r in subset]))
    result=dict(schema=VERSION,experiment_id=p['experiment_id'],plan_sha256=p['plan_sha256'],estimate_sha256=p['estimate_sha256'],
        model=p['model'],planned_slots=21,unique_profiles=12,conditions=13,source_fixtures=5,results=results,arms=arms,receipts=receipts,
        complete=all(r['execution_state']=='COMPLETED' for r in results),formal_quality_status='NOT_EVALUATED',formal_quality_score=None,
        diagnostic_counts=dict(Counter(c['status'] for r in results for c in r['checks'])),
        actual_live_model_requests=sum(r['actual_live_model_requests'] for r in results) if all(r['actual_live_model_requests'] is not None for r in results) else None,
        model_usage=usage,calculated_usage_cost_usd=sum(costs) if costs and all(v is not None for v in costs) else None,
        peak_all_miss_cost_upper_usd=sum(r['estimated_cost_upper'] for r in receipts) if receipts and all(r['estimated_cost_upper'] is not None for r in receipts) else None,
        cost_kind='response_usage_cache_verified_request_period_not_invoice',budget_usd=.30,judge_calls=0,cloud_uploads=0,
        billing_uncertain=ledger.get('billing_uncertain',False),budget_stopped=ledger.get('budget_stopped',False),
        limitations=['Pending references only diagnose; same itinerary repeated, not independent holdout.',
            'Intervention is the complete new route-input block, not one individual field.',
            'Frozen route/ticket facts; no new external fact checks or human acceptance.'])
    atomic(directory/'report.json',result)
    with (directory/'checks.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['slot','profile','variant','layer','rule','status','diagnostic_only','reference_status'])
        for row in results:
            for check in row['checks']:writer.writerow([row['slot_id'],row['profile_id'],row['variant'],check['layer'],check['rule'],check['status'],True,row['reference_status']])
    lines=['# Eval v2.1 路线输入对照诊断','',f"实验 `{p['experiment_id']}`。全部参考待审，正式质量成绩为空。",'',
        f"计划21槽；实际模型请求{result['actual_live_model_requests']}；usage {usage}；计价US${result['calculated_usage_cost_usd']}，非核销账单。",'',
        '| 组别与重复 | 终态 | 交通分钟 | 减少分钟 | 当天结束 | 结果 |','| --- | --- | ---: | ---: | --- | --- |']
    for row in results:
        if row['profile_id']!='PS12':continue
        m=row.get('route_metrics',{})
        lines.append(f"| {row['variant']} {row['repetition']} | {row['execution_state']} | {m.get('traffic_minutes','未知')} | {m.get('delta_minutes','未知')} | {m.get('end_time','未知')} | {m.get('classification','未运行')} |")
    lines+=['','每次原始建议、系统结果、失败和Trace见report.json；改善仅按冻结约束诊断，不代替人工/USER验收。']
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','run','report'])
    parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--estimate-file',type=Path)
    parser.add_argument('--approve-estimate');parser.add_argument('--budget-usd',type=float)
    parser.add_argument('--credentials-file',type=Path);parser.add_argument('--max-slots',type=int)
    args=parser.parse_args()
    if args.command=='prepare':
        if not args.estimate_file:parser.error('--estimate-file required')
        result=prepare(args.directory,args.estimate_file)
    elif args.command=='run':result=execute(args.directory,approve_estimate=args.approve_estimate,budget_usd=args.budget_usd,
                                          credentials_file=args.credentials_file,max_slots=args.max_slots)
    else:result=report(args.directory)
    print({k:result[k] for k in ['experiment_id','plan_sha256','complete','actual_live_model_requests'] if k in result})


if __name__=='__main__':main()
