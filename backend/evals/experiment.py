"""Immutable plans, disposable workers, resumable local experiments. No implicit live calls."""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager

from .contracts import digest, Case
from .dataset import DATA, load_all, load_case, read_json
from .scorers import evaluate
from .reporting import counts
from .validation import validate

ROOT=Path(__file__).resolve().parents[2]
VERSION='runner-v1'


def atomic(path,value):
    data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(data);os.chmod(temp,0o600);temp.replace(path)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files():
    return sorted(p for d in ['backend/app','backend/evals'] for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in {'.py','.json'} and '__pycache__' not in p.parts)


def make_plan(output,*,case_ids=None,variants=('baseline','current_replay'),repeats=1,wall_seconds=1200,slot_seconds=120,estimate_file=None):
    output=Path(output).expanduser().resolve()
    if output.is_relative_to(ROOT) or output.exists():raise ValueError('choose a new directory outside the repository')
    if not 1<=repeats<=3 or not math.isfinite(wall_seconds+slot_seconds) or wall_seconds<=0 or slot_seconds<=0:raise ValueError('invalid execution limits')
    if not variants or len(set(variants))!=len(variants) or set(variants)-{'baseline','current_replay','current_live'}:raise ValueError('invalid variants')
    integrity=validate();bundles=load_all();known={c.case_id for c,*_ in bundles}
    if case_ids is not None and (not case_ids or len(set(case_ids))!=len(case_ids) or set(case_ids)-known):raise ValueError('invalid case selection')
    cases=[c for c,*_ in bundles if case_ids is None or c.case_id in case_ids]
    output.mkdir(parents=True,mode=0o700); (output/'source').mkdir();(output/'slots').mkdir()
    files={}
    for path in source_files():
        relative=path.relative_to(ROOT/'backend');dest=output/'source'/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes());files[str(relative)]=sha(dest)
    locks={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'backend/requirements.txt',ROOT/'backend/requirements.lock.txt',ROOT/'frontend/package-lock.json']}
    slots=[]
    for variant in variants:
        for c in cases:
            n=repeats if variant!='baseline' and c.execution_mode=='live_model_with_replay' else 1
            for repeat in range(1,n+1):
                slots.append(dict(slot_id=f'{variant}-{c.case_id}-{repeat}',case_id=c.case_id,variant=variant,repetition=repeat,
                    applicable=not(variant=='baseline' and c.execution_mode=='injected_failure')))
    plan=dict(schema='trip-experiment-v1',runner_version=VERSION,experiment_id='eval_'+uuid.uuid4().hex,created_at=time.time(),
        source_files=files,source_sha256=digest(files),dependency_locks=locks,
        packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},python=sys.version,
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        working_tree_snapshot=True,dataset_sha256=read_json(DATA/'manifest.json')['content_sha256'],
        slots=slots,concurrency=1,wall_seconds=wall_seconds,slot_seconds=slot_seconds,
        repeats=repeats,model=dict(name='deepseek-v4-pro',temperature=.2,thinking='disabled',structured_output='json_prompt',max_output_tokens=8192),
        judge=dict(enabled=False),trace_export=False,redaction_version='p1-whitelist-v1',integrity=integrity,
        live_authorization=None,limits=dict(max_model_requests=0,max_total_tokens=0,max_cost=None,currency=None))
    if 'current_live' in variants:
        if estimate_file is None:raise ValueError('live plan requires a pre-disclosed estimate file')
        quote=read_json(estimate_file);quoted=dict(quote);quote_hash=quoted.pop('estimate_sha256')
        if digest(quoted)!=quote_hash or quote['source_sha256']!=plan['source_sha256'] or quote['dataset_sha256']!=plan['dataset_sha256']:
            raise ValueError('estimate does not match frozen code/data')
        if set(quote['case_ids'])!={c.case_id for c in cases} or repeats!=quote['repeats'] or quote['model']!=plan['model']:raise ValueError('estimate scope/model mismatch')
        plan['estimate']=quote;plan['limits']=quote['reservation'];plan['live_authorization']='explicit_estimate_hash_required_at_run'
    plan['plan_sha256']=digest(plan);atomic(output/'manifest.json',plan)
    atomic(output/'ledger.json',dict(plan_sha256=plan['plan_sha256'],slots={},wall_seconds_spent=0,model_requests_reserved=0,tokens_reserved=0))
    return plan


def verified_plan(directory):
    directory=Path(directory).resolve();plan=read_json(directory/'manifest.json');check=dict(plan);expected=check.pop('plan_sha256')
    if digest(check)!=expected:raise ValueError('immutable plan changed')
    if plan['runner_version']!=VERSION:raise ValueError('runner version mismatch')
    for rel,want in plan['source_files'].items():
        p=(directory/'source'/rel).resolve()
        if not p.is_relative_to(directory/'source') or not p.is_file() or sha(p)!=want:raise ValueError('frozen source changed')
    for rel in ['evals/experiment.py','evals/contracts.py','evals/scorers.py','evals/reporting.py','evals/dataset.py','evals/budget.py']:
        if sha(ROOT/'backend'/rel)!=plan['source_files'].get(rel):raise ValueError('active runner/scorer changed; use frozen version or create a new experiment')
    current={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    if current!=plan['packages']:raise ValueError('runtime packages changed; create a new experiment')
    return plan


@contextmanager
def lock(directory):
    import fcntl
    with (directory/'runner.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('experiment already running') from None
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


def child_env(directory,source):
    # Explicit allowlist. Never inherit DATABASE_URL, proxy, SDK tracing or API credentials.
    env={k:os.environ[k] for k in ('PATH','HOME','LANG','LC_ALL','TMPDIR') if k in os.environ}
    env.update(PYTHONPATH=str(source),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='20261024',
        DATABASE_URL='sqlite+aiosqlite:///'+str(directory/'case.sqlite'),LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',OBSERVABILITY_ENABLED='false',OBSERVABILITY_EXPORT_ENABLED='false',
        LLM_STRUCTURED_OUTPUT_MODE='json_prompt',LLM_THINKING_MODE='disabled')
    return env


def execute_plan(directory,*,max_slots=None,approve_estimate=None,credentials_file=None):
    if max_slots is not None and max_slots<0:raise ValueError('max_slots must be nonnegative')
    directory=Path(directory).resolve();plan=verified_plan(directory)
    live_env={}
    if any(s['variant']=='current_live' for s in plan['slots']):
        quote=plan.get('estimate')
        if not quote or approve_estimate!=quote['estimate_sha256'] or credentials_file is None:
            raise ValueError('live execution locked: disclose estimate then explicitly approve its hash and supply credentials')
        from dotenv import dotenv_values
        from urllib.parse import urlparse
        values=dotenv_values(credentials_file)
        endpoint=values.get('LLM_BASE_URL') or values.get('OPENAI_BASE_URL')
        model=values.get('LLM_MODEL_NAME') or values.get('LLM_MODEL_ID') or values.get('OPENAI_MODEL')
        key=values.get('LLM_API_KEY') or values.get('OPENAI_API_KEY')
        url=urlparse(endpoint or '')
        if not key or model!=quote['model']['name'] or url.scheme!='https' or url.hostname!='api.deepseek.com' or url.username or url.password or url.query or url.port not in {None,443}:
            raise ValueError('credentials must match quoted direct DeepSeek endpoint and model')
        live_env=dict(LLM_API_KEY=key,LLM_BASE_URL=endpoint,LLM_MODEL_NAME=model)
    with lock(directory):
        ledger=read_json(directory/'ledger.json')
        if ledger['plan_sha256']!=plan['plan_sha256']:raise ValueError('ledger plan mismatch')
        # A process killed after dispatch has an indeterminate outcome; never silently call twice.
        for slot_id,entry in ledger['slots'].items():
            if entry['state']=='RUNNING':
                entry.update(state='INTERRUPTED',reason='previous_worker_outcome_unknown',wall_seconds=plan['slot_seconds'])
                if slot_id.startswith('current_live-'):ledger['billing_uncertain']=True
        ledger['wall_seconds_spent']=max(ledger['wall_seconds_spent'],sum(x.get('wall_seconds',0) for x in ledger['slots'].values()))
        atomic(directory/'ledger.json',ledger)
        if ledger.get('billing_uncertain'):raise ValueError('prior live billing is uncertain; reconcile before creating a new plan')
        start=time.monotonic();ran=0;stop=False
        old={}
        def halt(signum,frame):
            nonlocal stop
            stop=True
        for sig in (signal.SIGINT,signal.SIGTERM):old[sig]=signal.signal(sig,halt)
        try:
            for slot in plan['slots']:
                sid=slot['slot_id']
                if sid in ledger['slots']:continue
                if max_slots is not None and ran>=max_slots:break
                if stop or (directory/'CANCEL').exists():break
                remaining=plan['wall_seconds']-ledger['wall_seconds_spent']-(time.monotonic()-start)
                if remaining<=0:break
                if not slot['applicable']:
                    ledger['slots'][sid]=dict(state='NOT_APPLICABLE',reason='fault_injection_not_applicable_to_baseline');atomic(directory/'ledger.json',ledger);continue
                c,inp,_,routes=load_case(slot['case_id'],directory/'source/evals/datasets')
                work=directory/'slots'/sid;work.mkdir(mode=0o700)
                job=dict(slot,experiment_id=plan['experiment_id'],case=c.model_dump(mode='json'),inputs=inp,routes=routes)
                # Strip answer paths/hashes/status from worker contract; no reference can be opened.
                job['case']={k:job['case'][k] for k in ('case_id','case_version','input_sha256','clock','data_origin','execution_mode')}
                live_limits=None
                if slot['variant']=='current_live' and c.execution_mode=='live_model_with_replay':
                    row=next(r for r in plan['estimate']['rows'] if r['case_id']==c.case_id)
                    if ledger['model_requests_reserved']+row['max_attempts_per_run']>plan['limits']['max_model_requests'] or ledger['tokens_reserved']+row['max_tokens_per_run']>plan['limits']['max_total_tokens']:break
                    live_limits=dict(max_requests=row['max_attempts_per_run'],max_tokens=row['max_tokens_per_run'],max_cost=row['max_cost_per_run'],max_output_tokens=8192,rates=plan['estimate']['rates'])
                    job['live_limits']=live_limits
                    ledger['model_requests_reserved']+=live_limits['max_requests'];ledger['tokens_reserved']+=live_limits['max_tokens']
                    ledger['cost_reserved']=ledger.get('cost_reserved',0)+live_limits['max_cost']
                    if ledger['cost_reserved']>plan['limits']['max_cost']+1e-9:raise ValueError('aggregate monetary reservation exceeded')
                atomic(work/'job.json',job)
                ledger['slots'][sid]=dict(state='RUNNING',started_at=time.time());atomic(directory/'ledger.json',ledger)
                begin=time.monotonic();process=subprocess.Popen([sys.executable,'-m','evals.worker'],cwd=work,env={**child_env(work,directory/'source'),**(live_env if live_limits else {})},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                reason=None
                while process.poll() is None:
                    if stop or (directory/'CANCEL').exists():reason='cancelled_by_operator'
                    elif time.monotonic()-begin>=min(plan['slot_seconds'],remaining):reason='worker_wall_limit'
                    if reason:
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=2)
                        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                        break
                    time.sleep(.04)
                entry=ledger['slots'][sid]
                if reason:entry.update(state='CANCELLED' if reason.startswith('cancelled') else 'TIMEOUT',reason=reason)
                elif process.returncode or not(work/'observation.json').exists():entry.update(state='ERROR',reason='worker_failed')
                else:entry.update(state='COMPLETED',observation_sha256=sha(work/'observation.json'),engineering_sha256=sha(work/'engineering.json'))
                if live_limits:
                    receipts=read_json(work/'model-receipts.json') if (work/'model-receipts.json').exists() else []
                    if entry['state']!='COMPLETED' or any(r['usage'] is None for r in receipts):ledger['billing_uncertain']=True
                    if entry['state']=='COMPLETED' and read_json(work/'engineering.json').get('budget_stop'):ledger['billing_uncertain']=True
                entry.update(wall_seconds=time.monotonic()-begin,finished_at=time.time());ran+=1
                atomic(directory/'ledger.json',ledger)
                if reason=='cancelled_by_operator' or ledger.get('billing_uncertain'):break
        finally:
            ledger['wall_seconds_spent']+=time.monotonic()-start;atomic(directory/'ledger.json',ledger)
            for sig,handler in old.items():signal.signal(sig,handler)
        return export_report(directory)


def percentile(values,p):return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None


def export_report(directory):
    directory=Path(directory).resolve();plan=verified_plan(directory);ledger=read_json(directory/'ledger.json');results=[]
    for slot in plan['slots']:
        c,inp,ref,routes=load_case(slot['case_id'],directory/'source/evals/datasets');entry=ledger['slots'].get(slot['slot_id'],{'state':'NOT_RUN'})
        work=directory/'slots'/slot['slot_id'];report=None;error=None;observation={};engineering={}
        if entry['state']=='COMPLETED':
            if sha(work/'observation.json')!=entry['observation_sha256'] or sha(work/'engineering.json')!=entry['engineering_sha256']:raise ValueError('completed evidence changed')
            observation=read_json(work/'observation.json');engineering=read_json(work/'engineering.json');scoring_case=c.model_copy(deep=True)
            if slot['variant']=='baseline':
                for a in scoring_case.expected_assertions:
                    if a.layer=='model' or a.rule_id in {'S-TRACE','R-DISCLOSE'}:a.applicable=False;a.reason='baseline_has_no_model_or_model_trace'
            try:report=evaluate(scoring_case,inp,ref,routes,observation,allow_provisional=True)
            except (ValueError,TypeError,KeyError):error='observation_or_evaluator_error'
        if report is None:
            checks=[dict(rule_id=a.rule_id,layer=a.layer,status='NOT_APPLICABLE' if not a.applicable or not slot['applicable'] else 'ERROR',score=None,
                reason=error or entry['state'].lower(),evidence_paths=[],reference_status=c.annotation.status,provisional=c.annotation.status!='confirmed') for a in c.expected_assertions]
        else:checks=report['checks']
        # Entire pending-reference case is diagnostic, including reference-derived disclosures.
        official=c.annotation.status=='confirmed' and plan['integrity']['formal_ready'] and slot['variant']!='current_replay'
        result=dict(**slot,execution_state=entry['state'],reference_status=c.annotation.status,data_origin=c.data_origin,split=c.split,
            diagnostic_only=not official,formal_quality_eligible=official,formal_checks=checks if official else [],diagnostic_checks=checks,
            counts=counts(checks),wall_seconds=entry.get('wall_seconds'),evidence=f"slots/{slot['slot_id']}/observation.json" if report else None,
            business_outcome=observation.get('business_outcome') if report else None,
            operation_status=observation.get('execution_status'),operation_wall_seconds=observation.get('timings',{}).get('operation_wall_seconds'),
            actual_live_model_requests=engineering.get('actual_live_model_requests',0) if entry['state']=='COMPLETED' else None if slot['variant']=='current_live' else 0,
            usage=observation.get('usage'),cost=sum(x['estimated_cost_upper'] for x in engineering.get('model_receipts',[])) if engineering.get('model_receipts') and all(x['estimated_cost_upper'] is not None for x in engineering['model_receipts']) else None,
            cost_kind='peak_cache_miss_estimate_upper_not_invoice',model_substitute_calls=engineering.get('model_substitute_calls',0))
        results.append(result)
    groups=[]
    for variant in dict.fromkeys(s['variant'] for s in plan['slots']):
        subset=[r for r in results if r['variant']==variant];done=[r['operation_wall_seconds'] for r in subset if r['operation_status']=='success' and r['operation_wall_seconds'] is not None]
        groups.append(dict(variant=variant,planned=len(subset),completed=sum(r['execution_state']=='COMPLETED' for r in subset),
            diagnostic_counts=counts([c for r in subset for c in r['diagnostic_checks']]),formal_counts=counts([c for r in subset for c in r['formal_checks']]),
            wall_p50_seconds=percentile(done,.5),wall_p95_seconds=percentile(done,.95),p95_small_sample=len(done)<20))
    live=[r for r in results if r['variant']=='current_live' and r['actual_live_model_requests']!=0]
    measured_usage={k:sum(r['usage'][k] for r in live) for k in ('input_tokens','output_tokens','total_tokens')} if live and all(r['usage'] for r in live) else None
    measured_cost=sum(r['cost'] for r in live) if live and all(r['cost'] is not None for r in live) else None
    comparisons=[]
    from collections import defaultdict
    by_rule=defaultdict(lambda:defaultdict(list))
    for r in results:
        for check in r['diagnostic_checks']:
            key=(r['variant'],r['split'],r['data_origin'],check['rule_id'],check['layer'])
            by_rule[key][r['case_id']].append(check)
    for key,case_results in sorted(by_rule.items()):
        per_case={cid:counts(values) for cid,values in case_results.items()}
        rates=[c['scored_pass_rate'] for c in per_case.values() if c['scored_pass_rate'] is not None]
        comparisons.append(dict(zip(['variant','split','data_origin','rule_id','layer'],key),case_counts=per_case,
            independent_cases=len(per_case),scored_cases=len(rates),diagnostic_case_equal_pass_rate=sum(rates)/len(rates) if rates else None))
    report=dict(schema='trip-experiment-report-v1' ,experiment_id=plan['experiment_id'],plan_sha256=plan['plan_sha256'],
        formal_quality_status='NOT_EVALUATED' if not any(r['formal_quality_eligible'] for r in results) else 'AVAILABLE',
        formal_quality_score=None,actual_live_model_requests=sum(r['actual_live_model_requests'] for r in results) if all(r['actual_live_model_requests'] is not None for r in results) else None,model_usage=measured_usage,model_cost=measured_cost,judge_calls=0,cloud_uploads=0,
        reservations={k:v for k,v in ledger.items() if k in {'model_requests_reserved','tokens_reserved','cost_reserved','billing_uncertain'}},per_rule_case_equal=comparisons,
        planned_slots=len(results),unique_cases=len({r['case_id'] for r in results}),results=results,groups=groups,
        limitations=['Pending references are diagnostics only','Scenario split is not independent holdout','Replay-model outputs are substitutes, not model-quality evidence','Latency percentiles use successful operation wall time; process startup is recorded separately; failures/timeouts/cancellations retain their own duration'])
    atomic(directory/'report.json',report)
    import csv
    with (directory/'checks.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['slot_id','case_id','variant','split','data_origin','diagnostic_only','execution_state','rule','layer','status','score','reason'])
        for r in results:
            for c in r['diagnostic_checks']:
                writer.writerow([r[k] for k in ('slot_id','case_id','variant','split','data_origin','diagnostic_only','execution_state')]+[c.get(k) for k in ('rule_id','layer','status','score','reason')])
    lines=['# 隔离实验报告','',f"实验 `{plan['experiment_id']}`；计划 {len(results)} 个槽位 / {report['unique_cases']} 个独立案例。",'',
        '**正式质量成绩：未评估。待确认参考只用于诊断；模型替身不代表真实模型质量。**','',
        '| 方案 | 计划 | 完成 | 诊断 P/F/E/U/NA | 正式评分数 |','| --- | --- | --- | --- | --- |']
    for g in groups:
        n=g['diagnostic_counts'];lines.append(f"| {g['variant']} | {g['planned']} | {g['completed']} | {'/'.join(str(n[k]) for k in ['P','F','E','U','NA'])} | {g['formal_counts']['P']+g['formal_counts']['F']} |")
    lines+=['','## 逐案结果','','| 槽位 | 执行 / 业务结果 | 诊断失败或缺证据 | 证据 |','| --- | --- | --- | --- |']
    for r in results:
        bad=', '.join(c['rule_id']+'/'+c['layer']+':'+c['status'] for c in r['diagnostic_checks'] if c['status'] in {'FAIL','ERROR'}) or '—'
        evidence=f"[Observation]({r['evidence']})" if r['evidence'] else '未产生完整证据'
        lines.append(f"| {r['slot_id']} | {r['execution_state']} / {r['business_outcome'] or '—'} | {bad} | {evidence} |")
    lines+=['','失败与未运行保留分母；baseline 的故障注入槽位为 N/A。报告中的通过只能说明对应诊断检查，不表示建议质量验收。真实模型用量与费用未知时为 null，不填 0。']
    (directory/'report.md').write_text('\n'.join(lines)+'\n');return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','run','report']);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--cases',help='comma separated case IDs');p.add_argument('--variants',default='baseline,current_replay');p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--wall-seconds',type=float,default=1200);p.add_argument('--slot-seconds',type=float,default=120);p.add_argument('--max-slots',type=int);p.add_argument('--estimate-file',type=Path);p.add_argument('--approve-estimate');p.add_argument('--credentials-file',type=Path)
    a=p.parse_args()
    if a.command=='prepare':r=make_plan(a.directory,case_ids=a.cases.split(',') if a.cases else None,variants=a.variants.split(','),repeats=a.repeats,wall_seconds=a.wall_seconds,slot_seconds=a.slot_seconds,estimate_file=a.estimate_file)
    elif a.command=='run':r=execute_plan(a.directory,max_slots=a.max_slots,approve_estimate=a.approve_estimate,credentials_file=a.credentials_file)
    else:r=export_report(a.directory)
    print(json.dumps({k:r[k] for k in ['experiment_id','plan_sha256','planned_slots','formal_quality_status'] if k in r},ensure_ascii=False))


if __name__=='__main__':main()
