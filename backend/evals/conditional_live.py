"""Explicitly authorized v2 batches. No live request during prepare or report."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse
import uuid

from .budget import estimated_cost, prompt_bound
from .conditional import load_cases, profile_inputs, score
from .contracts import digest, Observation
from .dataset import load_case, read_json
from .experiment import atomic, child_env, lock, sha, source_files, ROOT
from .scorers import day_constraints, persistence, ticket_rule, trace_check, MissingEvidence

VERSION = 'conditional-live-v1'
ADAPTER_CHANGES = {'evals/budget.py', 'evals/worker.py'}
MODEL = dict(name='deepseek-flash', temperature=.2, thinking='disabled',
             structured_output='json_prompt', max_output_tokens=8192, sdk_retries=0)
NO_MODEL = {'PS04', 'PS09', 'PS10'}
PEAK_RATES = dict(input_miss_peak_per_million=.3, input_hit_peak_per_million=.006,
                  output_peak_per_million=1.2)


def packages():
    return {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}


def inside(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('asset outside frozen directory')
    return path


def load_quote(path):
    quote = read_json(path)
    original = dict(quote); expected = original.pop('estimate_sha256')
    if digest(original) != expected or quote['schema'] != 'conditional-live-budget-proposal-v1':
        raise ValueError('estimate hash/schema mismatch')
    if quote['model'] != MODEL or quote['rates']['model'] != MODEL['name']:
        raise ValueError('quoted model mismatch')
    if any(quote['rates'].get(k) != v for k, v in PEAK_RATES.items()):
        raise ValueError('quoted Flash rates mismatch')
    if (quote['rates']['currency'] != 'USD' or quote['rates']['input_miss_off_peak_per_million'] != .15
            or quote['rates']['input_hit_off_peak_per_million'] != .003
            or quote['rates']['output_off_peak_per_million'] != .6):
        raise ValueError('quoted rate/currency mismatch')
    if quote['conditional_data_sha256'] != digest(load_cases()):
        raise ValueError('conditional inputs or references changed')
    profiles = {c['id']: c for c in load_cases()}
    rows = quote['rows']
    if len(rows) != 12 or {r['profile_id'] for r in rows} != set(profiles):
        raise ValueError('quoted profile scope mismatch')
    expected_slots = []
    for row in rows:
        c = profiles[row['profile_id']]; live = c['id'] not in NO_MODEL
        repeats = 3 if live else 1
        attempts = (2 if c['source_id'].startswith('R') else 1) if live else 0
        if (row['source_id'] != c['source_id'] or row['input_sha256'] != digest(profile_inputs(c))
                or row['reference_sha256'] != c['reference_sha256']
                or row['reference_status'] != c['annotation']['status']
                or row['model_path'] != live or row['repetitions'] != repeats
                or row['max_attempts_per_slot'] != attempts
                or row['nominal_requests'] != (repeats if live else 0)
                or row['max_requests'] != repeats*attempts):
            raise ValueError('quoted profile inputs/limits mismatch')
        out = 8192 if live else 0
        if row['max_output_per_request'] != out:
            raise ValueError('quoted output limit mismatch')
        tokens = attempts*(row['input_reservation_per_request']+out)
        cost = estimated_cost(attempts*row['input_reservation_per_request'], attempts*out, quote['rates'])
        if row['max_tokens_per_slot'] != tokens or not math.isclose(row['max_cost_per_slot'], cost, abs_tol=1e-10):
            raise ValueError('quoted per-slot budget mismatch')
        for rep in range(1, repeats+1):
            expected_slots.append(dict(slot_id=f"{c['id']}-{rep}", profile_id=c['id'], repetition=rep,
                                       model_path=live, bundle=f"input-bundles/{c['id']}.json"))
    total_tokens = sum(r['max_tokens_per_slot']*r['repetitions'] for r in rows)
    total_cost = sum(r['max_cost_per_slot']*r['repetitions'] for r in rows)
    reserve = quote['reservation']
    if (quote['slots'] != expected_slots or len(expected_slots) != 30 or quote['planned_slots'] != 30
            or quote['nominal_live_requests'] != 27 or quote['max_live_requests'] != 30
            or reserve['max_requests'] != 30 or total_tokens != reserve['total_tokens']
            or not math.isclose(total_cost, reserve['calculated_peak_cost_usd'], abs_tol=1e-10)
            or total_cost > reserve['requested_budget_usd'] or reserve['requested_budget_usd'] > .36
            or quote['concurrency'] != 1 or quote['slot_seconds'] > 120 or quote['wall_seconds'] > 3600):
        raise ValueError('quoted aggregate scope/budget mismatch')
    return quote


def validate_assets(quote, base):
    for relative, expected in quote['files'].items():
        if sha(inside(base, relative)) != expected:
            raise ValueError('quoted asset changed')
    for row in quote['rows']:
        profile = next(c for c in load_cases() if c['id'] == row['profile_id'])
        bundle = read_json(base/f"input-bundles/{profile['id']}.json")
        case, _, _, routes = load_case(profile['source_id'])
        expected = {k: case.model_dump(mode='json')[k] for k in
                    ('case_id', 'case_version', 'input_sha256', 'clock', 'data_origin', 'execution_mode')}
        expected.update(case_version='2.0-draft-'+profile['id'], input_sha256=row['input_sha256'],
                        execution_mode='live_model_with_replay' if row['model_path'] else 'no_model')
        if bundle != dict(case=expected, inputs=profile_inputs(profile), routes=routes):
            raise ValueError('worker bundle differs from approved input')
        if row['model_path']:
            prompt = read_json(base/f"evidence/prompts/{profile['id']}.json")
            if digest(prompt) != row['prompt_sha256'] or prompt_bound(prompt) != row['input_reservation_per_request']:
                raise ValueError('quoted prompt changed')


def prepare(directory, quote_file):
    directory = Path(directory).resolve(); quote_file = Path(quote_file).resolve()
    if directory.exists() or directory.is_relative_to(ROOT):
        raise ValueError('choose a fresh directory outside repository')
    quote = load_quote(quote_file); validate_assets(quote, quote_file.parent)
    baseline = read_json(inside(quote_file.parent, quote['source_manifest']))
    if digest(baseline['source_files']) != quote['source_sha256'] or packages() != baseline['packages']:
        raise ValueError('approved source/runtime manifest mismatch')
    for relative, expected in baseline['source_files'].items():
        if relative not in ADAPTER_CHANGES and sha(ROOT/'backend'/relative) != expected:
            raise ValueError('product/evaluator source changed since quote: '+relative)
    directory.mkdir(parents=True, mode=0o700); (directory/'slots').mkdir()
    files = {}
    for path in source_files():
        relative = str(path.relative_to(ROOT/'backend')); target = directory/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        files[relative] = sha(target)
    for relative in quote['files']:
        target = inside(directory/'quoted', relative); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(inside(quote_file.parent, relative).read_bytes())
    atomic(directory/'estimate.json', quote)
    atomic(directory/'approved-source-manifest.json', baseline)
    plan = dict(schema=VERSION, experiment_id='eval_v2_'+uuid.uuid4().hex, created_at=time.time(),
        estimate_sha256=quote['estimate_sha256'], estimate_file_sha256=sha(directory/'estimate.json'),
        approved_source_manifest_sha256=sha(directory/'approved-source-manifest.json'),
        source_files=files, source_sha256=digest(files), packages=packages(), python=sys.version,
        locks={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'backend/requirements.txt',
            ROOT/'backend/requirements.lock.txt',ROOT/'frontend/package-lock.json']},
        slots=quote['slots'], model=quote['model'], rates=quote['rates'],
        limits=quote['reservation'], concurrency=1, slot_seconds=quote['slot_seconds'],
        wall_seconds=quote['wall_seconds'], judge_enabled=False, cloud_uploads=False,
        formal_quality_score=None, authorization_required=True)
    plan['plan_sha256'] = digest(plan); atomic(directory/'manifest.json', plan)
    atomic(directory/'ledger.json',dict(plan_sha256=plan['plan_sha256'],slots={},wall_seconds_spent=0))
    return plan


def verified(directory):
    directory = Path(directory).resolve(); plan = read_json(directory/'manifest.json')
    original = dict(plan); expected = original.pop('plan_sha256')
    if digest(original) != expected or plan['schema'] != VERSION:
        raise ValueError('frozen plan changed')
    if sha(directory/'estimate.json') != plan['estimate_file_sha256']:
        raise ValueError('frozen estimate changed')
    quote = load_quote(directory/'estimate.json'); validate_assets(quote, directory/'quoted')
    if quote['estimate_sha256'] != plan['estimate_sha256'] or plan['slots'] != quote['slots']:
        raise ValueError('plan differs from approved estimate')
    if plan['model'] != quote['model'] or plan['rates'] != quote['rates'] or plan['limits'] != quote['reservation']:
        raise ValueError('plan model/rate/budget changed')
    if (plan['concurrency'] != 1 or plan['slot_seconds'] != quote['slot_seconds']
            or plan['wall_seconds'] != quote['wall_seconds'] or plan['judge_enabled'] or plan['cloud_uploads']):
        raise ValueError('execution boundaries changed')
    if digest(plan['source_files']) != plan['source_sha256'] or packages() != plan['packages']:
        raise ValueError('runtime changed')
    for relative, expected in plan['source_files'].items():
        if sha(inside(directory/'source',relative)) != expected or sha(ROOT/'backend'/relative) != expected:
            raise ValueError('frozen/active source changed')
    for relative, expected in plan['locks'].items():
        if sha(ROOT/relative) != expected:
            raise ValueError('dependency lock changed')
    if sha(directory/'approved-source-manifest.json') != plan['approved_source_manifest_sha256']:
        raise ValueError('approved source manifest changed')
    return plan, quote


def credentials(path, model):
    from dotenv import dotenv_values
    values = dotenv_values(path)
    endpoint = values.get('LLM_BASE_URL') or values.get('OPENAI_BASE_URL')
    name = values.get('LLM_MODEL_NAME') or values.get('LLM_MODEL_ID') or values.get('OPENAI_MODEL')
    key = values.get('LLM_API_KEY') or values.get('OPENAI_API_KEY')
    url = urlparse(endpoint or '')
    if (not key or name != model['name'] or url.scheme != 'https' or url.hostname != 'api.deepseek.com'
            or url.username or url.password or url.query or url.fragment or url.port not in {None,443}
            or url.path not in {'','/','/v1','/v1/'}):
        raise ValueError('credentials must match quoted direct DeepSeek Flash endpoint/model')
    return dict(LLM_API_KEY=key,LLM_BASE_URL=endpoint,LLM_MODEL_NAME=name)


def reserve_slot(ledger, row, limits):
    previous = [x['reservation'] for x in ledger['slots'].values()]
    reservation = dict(requests=row['max_attempts_per_slot'], tokens=row['max_tokens_per_slot'],
                       cost=row['max_cost_per_slot'])
    if (sum(r['requests'] for r in previous)+reservation['requests'] > limits['max_requests']
            or sum(r['tokens'] for r in previous)+reservation['tokens'] > limits['total_tokens']
            or sum(r['cost'] for r in previous)+reservation['cost'] > limits['requested_budget_usd']+1e-10):
        raise ValueError('aggregate budget exhausted before worker dispatch')
    return reservation


def live_limits(row, quote):
    return dict(max_requests=row['max_attempts_per_slot'],max_tokens=row['max_tokens_per_slot'],
        max_cost=row['max_cost_per_slot'],max_output_tokens=row.get('max_output_per_request',row.get('max_output_tokens')),
        rates=quote['rates'],model=quote['model']['name'],prompt_sha256=row['prompt_sha256'],
        input_tokens_per_request=row['input_reservation_per_request'])


def execute(directory, *, approve_estimate=None, budget_usd=None, credentials_file=None, max_slots=None):
    directory = Path(directory).resolve(); plan, quote = verified(directory)
    return execute_frozen(directory,plan,quote,reporter=report,approve_estimate=approve_estimate,
                          budget_usd=budget_usd,credentials_file=credentials_file,max_slots=max_slots)


def execute_frozen(directory, plan, quote, *, reporter, approve_estimate=None, budget_usd=None,
                   credentials_file=None, max_slots=None):
    """Common dispatcher; callers must validate/freeze their versioned plan first."""
    directory = Path(directory).resolve()
    if (approve_estimate != plan['estimate_sha256'] or budget_usd != quote['reservation']['requested_budget_usd']
            or credentials_file is None):
        raise ValueError('live execution locked: explicit estimate hash and approved budget required')
    if max_slots is not None and (type(max_slots) is not int or max_slots < 0):
        raise ValueError('invalid slot limit')
    with lock(directory):
        ledger = read_json(directory/'ledger.json')
        if ledger['plan_sha256'] != plan['plan_sha256'] or set(ledger['slots'])-{s['slot_id'] for s in plan['slots']}:
            raise ValueError('ledger does not belong to frozen plan')
        for sid, entry in ledger['slots'].items():
            slot = next(s for s in plan['slots'] if s['slot_id'] == sid)
            if entry['state'] == 'RUNNING':
                entry.update(state='INTERRUPTED',reason='prior_worker_outcome_unknown')
                if slot['model_path']:ledger['billing_uncertain'] = True
        atomic(directory/'ledger.json',ledger)
        if ledger.get('billing_uncertain') or ledger.get('budget_stopped'):
            raise ValueError('prior billing/budget unresolved; automatic continuation forbidden')
        # Verify completed evidence before reading credentials or dispatching another slot.
        for sid, entry in ledger['slots'].items():
            slot=next(s for s in plan['slots'] if s['slot_id']==sid)
            key=slot.get('unit_id',slot['profile_id'])
            row=next(r for r in quote['rows'] if r.get('unit_id',r['profile_id'])==key)
            expected=dict(requests=row['max_attempts_per_slot'],tokens=row['max_tokens_per_slot'],cost=row['max_cost_per_slot'])
            if entry.get('reservation') != expected:raise ValueError('ledger reservation changed; no refunds or budget rewrites')
            for name, expected in entry.get('evidence',{}).items():
                if sha(directory/'slots'/sid/name) != expected:
                    raise ValueError('completed evidence changed')
        secret_env = credentials(credentials_file, quote['model'])
        atomic(directory/'authorization.json',dict(estimate_sha256=approve_estimate,budget_usd=budget_usd,
            authorized_at=time.time(),basis='explicit_user_authorization',model=quote['model']['name']))
        start = time.monotonic(); ran = 0; stopped = False; old_handlers = {}
        def halt(signum,frame):
            nonlocal stopped
            stopped = True
        for sig in (signal.SIGINT,signal.SIGTERM):old_handlers[sig] = signal.signal(sig,halt)
        try:
            for slot in plan['slots']:
                sid = slot['slot_id']
                if sid in ledger['slots']:continue
                if max_slots is not None and ran >= max_slots:break
                if stopped or (directory/'CANCEL').exists():break
                remaining = plan['wall_seconds']-ledger['wall_seconds_spent']-(time.monotonic()-start)
                if remaining <= 0:break
                key = slot.get('unit_id',slot['profile_id'])
                row = next(r for r in quote['rows'] if r.get('unit_id',r['profile_id']) == key)
                reservation = reserve_slot(ledger,row,plan['limits'])
                bundle_path = directory/'quoted'/slot['bundle']
                if sha(bundle_path) != (quote.get('files') or quote['assets'])[slot['bundle']]:
                    raise ValueError('worker input changed before dispatch')
                bundle = read_json(bundle_path)
                work = directory/'slots'/sid; work.mkdir(mode=0o700)
                job = dict(**bundle,variant='current_live' if slot['model_path'] else 'current_replay',
                           slot_id=sid,experiment_id=plan['experiment_id'],repetition=slot['repetition'])
                if 'unit_id' in slot:job['eval_input_variant'] = slot['variant']
                if slot['model_path']:job['live_limits'] = live_limits(row,quote)
                atomic(work/'job.json',job)
                entry = dict(state='RUNNING',reservation=reservation,started_at=time.time())
                ledger['slots'][sid] = entry; atomic(directory/'ledger.json',ledger)
                begin = time.monotonic(); reason = None
                env = child_env(work,directory/'source')
                if slot['model_path']:env.update(secret_env)
                with (work/'worker.log').open('w') as log:
                    process = subprocess.Popen([sys.executable,'-m','evals.worker'],cwd=work,env=env,
                                               stdout=log,stderr=log,start_new_session=True)
                    while process.poll() is None:
                        if stopped or (directory/'CANCEL').exists():reason = 'cancelled_by_operator'
                        elif time.monotonic()-begin >= min(plan['slot_seconds'],remaining):reason = 'worker_wall_limit'
                        if reason:
                            os.killpg(process.pid,signal.SIGTERM)
                            try:process.wait(timeout=2)
                            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                            break
                        time.sleep(.04)
                if reason:entry.update(state='CANCELLED' if reason.startswith('cancelled') else 'TIMEOUT',reason=reason)
                elif process.returncode or not (work/'observation.json').exists() or not (work/'engineering.json').exists():
                    entry.update(state='ERROR',reason='worker_failed')
                else:
                    entry.update(state='COMPLETED',evidence={name:sha(work/name) for name in
                        ('observation.json','engineering.json','job.json')})
                    for artifact in [work/'case.sqlite',*(work/'traces/operations').glob('*.json')]:
                        if artifact.is_file():entry['evidence'][str(artifact.relative_to(work))] = sha(artifact)
                    engineering = read_json(work/'engineering.json')
                    if engineering.get('budget_stop'):ledger['budget_stopped'] = True
                    if engineering.get('uncertain_usage'):ledger['billing_uncertain'] = True
                if slot['model_path']:
                    receipts = read_json(work/'model-receipts.json') if (work/'model-receipts.json').exists() else []
                    if entry['state'] != 'COMPLETED' or not receipts or any(r['usage'] is None for r in receipts):
                        ledger['billing_uncertain'] = True
                    if (work/'model-receipts.json').exists():
                        entry.setdefault('evidence',{})['model-receipts.json'] = sha(work/'model-receipts.json')
                entry.update(wall_seconds=time.monotonic()-begin,finished_at=time.time()); ran += 1
                atomic(directory/'ledger.json',ledger)
                print(f"{sid}: {entry['state']}",flush=True)
                if reason or ledger.get('billing_uncertain') or ledger.get('budget_stopped'):break
        finally:
            ledger['wall_seconds_spent'] += time.monotonic()-start
            atomic(directory/'ledger.json',ledger)
            for sig,handler in old_handlers.items():signal.signal(sig,handler)
        return reporter(directory)


def measured_cost(receipt, rates):
    usage = receipt.get('usage')
    if not usage:return None
    details = usage.get('input_token_details') or {}
    provider = receipt.get('provider_cache_tokens') or {}
    hit = details.get('cache_read',provider.get('prompt_cache_hit_tokens'))
    if type(hit) is not int or not 0 <= hit <= usage['input_tokens']:return None
    if provider.get('prompt_cache_hit_tokens',hit) != hit:return None
    miss = usage['input_tokens']-hit
    if provider.get('prompt_cache_miss_tokens',miss) != miss:return None
    def period(timestamp):
        now = datetime.fromtimestamp(timestamp,timezone.utc)
        # Holiday status is irrelevant outside the normal peak windows.
        return 'off_peak' if now.weekday() >= 5 or now.hour not in {1,2,3,6,7,8,9} else 'holiday_status_required'
    if period(receipt['started_at']) != 'off_peak' or period(receipt['finished_at']) != 'off_peak':return None
    return (hit*rates['input_hit_off_peak_per_million'] + miss*rates['input_miss_off_peak_per_million']
            + usage['output_tokens']*rates['output_off_peak_per_million'])/1_000_000


def extra_checks(profile, observation, bundle, model_path, *, scorer=score, reference_override=None):
    """Keep raw model diagnostics separate from repaired/fallback system outputs."""
    checks = []
    def add(rule,layer,status,actual=None,expected=None):
        checks.append(dict(rule=rule,layer=layer,status=status,actual=actual,expected=expected))
    obs = Observation.model_validate(observation)
    inputs = bundle['inputs']; _, _, reference, routes = load_case(profile['source_id'])
    if reference_override is not None:reference=reference_override
    def independent(rule,layer,fn):
        try:
            ok,expected,actual,_ = fn()
            add(rule,layer,'PASS' if ok else 'FAIL',actual,expected)
        except (ValueError,KeyError,TypeError,RuntimeError,MissingEvidence):add(rule,layer,'ERROR')
    independent('S-TRACE','observability',lambda:trace_check(obs))
    if inputs.get('saved_state') or 'day_detail' in inputs:
        independent('S-PERSIST','system',lambda:persistence(inputs,reference,obs))
    if profile['source_id'].startswith('R'):
        for rule in ['R-LOCK','R-REMOVED','R-MEAL','R-MANUAL','R-FACT','R-DURATION','R-REST','R-WINDOW','R-DISCLOSE']:
            independent(rule,'system',lambda rule=rule:day_constraints(rule,'system',inputs,reference,obs,routes))
        if model_path:
            for rule in ['R-LOCK','R-REMOVED','R-MEAL','R-INTENT']:
                independent(rule,'model',lambda rule=rule:day_constraints(rule,'model',inputs,reference,obs,routes))
    else:
        independent('T-FACT','system',lambda:ticket_rule('T-FACT','system',inputs,reference,obs))
        if model_path:
            raw = observation.get('raw_model') or {}; ids = raw.get('ids')
            prompts = bundle.get('prompt') or []
            allowed = {c['id'] for c in json.loads(prompts[-1]['content'])['candidates']} if prompts else set()
            valid = (isinstance(ids,list) and 1 <= len(ids) <= 3 and all(isinstance(i,str) for i in ids)
                     and len(set(ids)) == len(ids) and set(ids) <= allowed)
            add('T-VALID','model','PASS' if valid else 'FAIL',ids,sorted(allowed))
            if valid:
                projected = copy.deepcopy(observation)
                source = {c['id']:c for c in inputs['candidates']}
                projected['final_output'] = dict(recommendations=[dict(candidate=source[i]) for i in ids])
                projected['execution_status'] = 'success'
                model_score = scorer(profile,projected,diagnostic=True)
                for check in model_score['checks']:
                    if check['rule'] in {'eligible_recommendations','conditional_rank','declared_order'}:
                        checks.append(dict(check,layer='model'))
        else:
            add('no_model_call','system','PASS' if obs.actual_model_calls == 0 else 'FAIL',obs.actual_model_calls,0)
    return checks


def report(directory):
    directory = Path(directory).resolve(); plan,quote = verified(directory)
    ledger = read_json(directory/'ledger.json'); results = []; all_receipts = []
    profiles = {c['id']:c for c in load_cases()}
    for slot in plan['slots']:
        entry = ledger['slots'].get(slot['slot_id'],{'state':'NOT_RUN'})
        profile = profiles[slot['profile_id']]; work = directory/'slots'/slot['slot_id']
        origin = next(r for r in quote['rows'] if r['profile_id']==slot['profile_id'])
        row = dict(**slot,source_id=profile['source_id'],source_family=origin['source_family'],
                   source_split=origin['source_split'],data_origin=origin['data_origin'],
                   execution_state=entry['state'],reference_status=profile['annotation']['status'],
                   diagnostic_only=True,formal_checks=[],formal_quality_score=None,checks=[],
                   actual_live_model_requests=0 if not slot['model_path'] or entry['state']=='NOT_RUN' else None)
        if entry['state'] == 'COMPLETED':
            for name,expected in entry['evidence'].items():
                if sha(work/name) != expected:raise ValueError('completed evidence changed')
            obs = read_json(work/'observation.json'); engineering = read_json(work/'engineering.json')
            try:
                scored = score(profile,obs,diagnostic=True)
                row['checks'] = [dict(c,layer='system') for c in scored['checks']]
                bundle = read_json(directory/'quoted'/slot['bundle'])
                if slot['model_path']:bundle['prompt'] = read_json(directory/'quoted/evidence/prompts'/f"{profile['id']}.json")
                row['checks'] += extra_checks(profile,obs,bundle,slot['model_path'])
            except (ValueError,KeyError,TypeError,RuntimeError,MissingEvidence):
                row['checks'].append(dict(rule='evidence_or_scoring',layer='engineering',status='ERROR'))
            receipts = engineering.get('model_receipts',[])
            expected_transport = (engineering['actual_live_model_requests'] >= 1
                                  and engineering['model_substitute_calls'] == 0
                                  and obs['provenance'] == 'live_model_with_replay') if slot['model_path'] else (
                                      engineering['actual_live_model_requests'] == engineering['model_substitute_calls'] == 0
                                      and obs['provenance'] == 'no_model')
            row['checks'].append(dict(rule='expected_execution_transport',layer='engineering',
                                      status='PASS' if expected_transport else 'FAIL'))
            all_receipts += [dict(r,slot_id=slot['slot_id']) for r in receipts]
            row.update(actual_live_model_requests=engineering['actual_live_model_requests'],usage=obs['usage'],
                operation_status=obs['execution_status'],model_status=obs['model_status'],
                outcome=obs['business_outcome'],raw_model=obs['raw_model'],
                final_selected_ids=[r['candidate']['id'] for r in obs['final_output'].get('recommendations',[])] if obs['final_output'] and not profile['source_id'].startswith('R') else None,
                evidence=f"slots/{slot['slot_id']}/observation.json",trace_id=obs.get('trace_id'),
                local_trace=f"slots/{slot['slot_id']}/traces/operations/{obs['trace_id']}.json" if obs.get('trace_id') else None)
        else:
            row['checks'] = [dict(rule='execution',layer='engineering',status='ERROR',actual=entry['state'])]
        results.append(row)
    from collections import Counter
    counts = dict(Counter(c['status'] for r in results for c in r['checks']))
    usage = {k:sum(r['usage'][k] for r in all_receipts) for k in ('input_tokens','output_tokens','total_tokens')} if all_receipts and all(r['usage'] for r in all_receipts) else None
    cost_values = [measured_cost(r,plan['rates']) for r in all_receipts]
    complete = len(results) == sum(r['execution_state'] == 'COMPLETED' for r in results)
    result = dict(schema=VERSION,experiment_id=plan['experiment_id'],plan_sha256=plan['plan_sha256'],
        estimate_sha256=plan['estimate_sha256'],model=plan['model'],planned_slots=30,
        unique_profiles=12,source_fixtures=5,complete=complete,formal_quality_status='NOT_EVALUATED',
        formal_quality_score=None,diagnostic_counts=counts,results=results,receipts=all_receipts,
        actual_live_model_requests=sum(r['actual_live_model_requests'] for r in results) if all(r['actual_live_model_requests'] is not None for r in results) else None,
        model_usage=usage,calculated_usage_cost_usd=sum(cost_values) if cost_values and all(c is not None for c in cost_values) else None,
        peak_all_miss_cost_upper_usd=sum(r['estimated_cost_upper'] for r in all_receipts) if all_receipts and all(r['estimated_cost_upper'] is not None for r in all_receipts) else None,
        cost_kind='response_usage_cache_and_non_peak_request_interval_not_invoice',
        requested_budget_usd=plan['limits']['requested_budget_usd'],judge_calls=0,cloud_uploads=0,
        billing_uncertain=ledger.get('billing_uncertain',False),budget_stopped=ledger.get('budget_stopped',False),
        limitations=['All references pending human; no formal quality score.',
            '12 variants from 5 already-seen fixtures; repetitions are not independent samples.',
            'P3 used Pro; this Flash run cannot isolate code improvement.',
            'Frozen maps/tickets, local traces; no new provider fact checks or human acceptance.'])
    atomic(directory/'report.json',result)
    with (directory/'checks.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['slot','profile','layer','rule','status'])
        for row in results:
            for check in row['checks']:writer.writerow([row['slot_id'],row['profile_id'],check['layer'],check['rule'],check['status']])
    lines=['# Eval v2 真实模型诊断报告','',f"实验 `{plan['experiment_id']}`。正式质量成绩：NOT_EVALUATED，参考全部待人工确认。",'',
        f"计划30槽 / 12条件化场景 / 5基础材料；真实请求 {result['actual_live_model_requests']}，judge 0，云上传0。",'',
        f"usage：{usage}；用量与缓存/请求时段计价 US${result['calculated_usage_cost_usd']}（非核销账单）；峰时全未命中 US${result['peak_all_miss_cost_upper_usd']}。",'',
        '| 槽位 | 执行状态 | 模型/系统失败或缺证据 | 证据 |','| --- | --- | --- | --- |']
    for row in results:
        bad=[c['layer']+':'+c['rule']+'='+c['status'] for c in row['checks'] if c['status'] in {'FAIL','ERROR'}]
        lines.append(f"| {row['slot_id']} | {row['execution_state']} | {', '.join(bad) or '无'} | {row.get('evidence','未运行')} |")
    lines += ['','所有检查计数均为诊断，不是独立样本通过率；模型、系统回退和证据问题分层保留。']
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','run','report'])
    parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--estimate-file',type=Path)
    parser.add_argument('--approve-estimate');parser.add_argument('--budget-usd',type=float)
    parser.add_argument('--credentials-file',type=Path);parser.add_argument('--max-slots',type=int)
    args=parser.parse_args()
    if args.command == 'prepare':
        if args.estimate_file is None:parser.error('--estimate-file required')
        result=prepare(args.directory,args.estimate_file)
    elif args.command == 'run':
        result=execute(args.directory,approve_estimate=args.approve_estimate,budget_usd=args.budget_usd,
                       credentials_file=args.credentials_file,max_slots=args.max_slots)
    else:result=report(args.directory)
    print({k:result[k] for k in ['experiment_id','plan_sha256','planned_slots','actual_live_model_requests','complete'] if k in result})


if __name__ == '__main__':main()
