"""Budget gates and transport simulations only; every subprocess denies networking."""
import copy
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from evals.budget import BudgetStop, CallBudget, estimated_cost, prompt_bound
from evals.conditional import load_cases, profile_inputs, score
from evals.contracts import digest
from evals.dataset import load_case, read_json
from evals.experiment import atomic, child_env, sha, source_files, ROOT
from evals import conditional_live as live


@pytest.fixture(scope='module')
def quote_file(tmp_path_factory):
    root=tmp_path_factory.mktemp('conditional-quote')
    files={}; rows=[]; slots=[]
    rates=dict(model='deepseek-flash',currency='USD',**live.PEAK_RATES,
               input_miss_off_peak_per_million=.15,input_hit_off_peak_per_million=.003,
               output_off_peak_per_million=.6)
    for c in load_cases():
        base,_,_,routes=load_case(c['source_id']); uses_model=c['id'] not in live.NO_MODEL
        inputs=profile_inputs(c); header={k:base.model_dump(mode='json')[k] for k in
            ('case_id','case_version','input_sha256','clock','data_origin','execution_mode')}
        header.update(case_version='2.0-draft-'+c['id'],input_sha256=digest(inputs),
                      execution_mode='live_model_with_replay' if uses_model else 'no_model')
        relative=f"input-bundles/{c['id']}.json"
        (root/'input-bundles').mkdir(exist_ok=True)
        atomic(root/relative,dict(case=header,inputs=inputs,routes=routes));files[relative]=sha(root/relative)
        prompt=[dict(role='human',content='{"candidates":[]}')]
        n=prompt_bound(prompt) if uses_model else 0
        if uses_model:
            path=root/f"evidence/prompts/{c['id']}.json";path.parent.mkdir(parents=True,exist_ok=True)
            atomic(path,prompt);files[str(path.relative_to(root))]=sha(path)
        reps=3 if uses_model else 1;attempts=(2 if c['source_id'].startswith('R') else 1) if uses_model else 0
        row=dict(profile_id=c['id'],source_id=c['source_id'],source_family=c['source_family'],
            source_split=c['source_split'],data_origin=base.data_origin,input_sha256=digest(inputs),
            reference_sha256=c['reference_sha256'],reference_status='pending_human',model_path=uses_model,
            repetitions=reps,max_attempts_per_slot=attempts,nominal_requests=reps if uses_model else 0,
            max_requests=reps*attempts,input_reservation_per_request=n,max_output_per_request=8192 if uses_model else 0,
            max_tokens_per_slot=attempts*(n+8192),max_cost_per_slot=estimated_cost(attempts*n,attempts*8192,rates),
            prompt_sha256=digest(prompt) if uses_model else None)
        rows.append(row)
        slots += [dict(slot_id=f"{c['id']}-{rep}",profile_id=c['id'],repetition=rep,model_path=uses_model,bundle=relative) for rep in range(1,reps+1)]
    source={str(p.relative_to(ROOT/'backend')):sha(p) for p in source_files()}
    baseline=dict(source_files=source,packages=live.packages());atomic(root/'baseline.json',baseline)
    q=dict(schema='conditional-live-budget-proposal-v1',model=live.MODEL,rates=rates,source_manifest='baseline.json',
        source_sha256=digest(source),conditional_data_sha256=digest(load_cases()),rows=rows,slots=slots,files=files,
        planned_slots=30,nominal_live_requests=27,max_live_requests=30,concurrency=1,slot_seconds=120,wall_seconds=3600,
        reservation=dict(max_requests=30,total_tokens=sum(r['max_tokens_per_slot']*r['repetitions'] for r in rows),
            calculated_peak_cost_usd=sum(r['max_cost_per_slot']*r['repetitions'] for r in rows),requested_budget_usd=.36))
    q['estimate_sha256']=digest(q);atomic(root/'quote.json',q)
    return root/'quote.json'


def prepared(tmp_path,quote_file):
    root=tmp_path/'experiment';live.prepare(root,quote_file);return root


def test_missing_approval_stops_before_credentials_and_dispatch(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file)
    def forbidden(*a,**kw):raise AssertionError('must fail before credentials/network')
    monkeypatch.setattr(live,'credentials',forbidden);monkeypatch.setattr(live.subprocess,'Popen',forbidden)
    for kwargs in [{},{'approve_estimate':'wrong','budget_usd':.36,'credentials_file':'missing'},
                   {'approve_estimate':read_json(quote_file)['estimate_sha256'],'budget_usd':.37,'credentials_file':'missing'}]:
        with pytest.raises(ValueError,match='locked'):live.execute(root,**kwargs)
    assert read_json(root/'ledger.json')['slots']=={}


@pytest.mark.parametrize('mutation', ['model','input','slots','money','rates'])
def test_rehashed_quote_drift_rejected_before_dispatch(tmp_path,quote_file,mutation):
    q=read_json(quote_file);q.pop('estimate_sha256')
    if mutation=='model':q['model']['name']='deepseek-v4-pro'
    elif mutation=='input':q['rows'][0]['input_sha256']='0'*64
    elif mutation=='slots':q['slots'].append(q['slots'][0])
    elif mutation=='money':q['reservation']['requested_budget_usd']=.37
    else:q['rates']['output_peak_per_million']=1.1
    q['estimate_sha256']=digest(q);path=tmp_path/'bad.json';atomic(path,q)
    with pytest.raises(ValueError):live.load_quote(path)


def test_source_and_runtime_tampering_rejected(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file)
    monkeypatch.setattr(live,'packages',lambda:{})
    with pytest.raises(ValueError,match='runtime changed'):live.verified(root)
    monkeypatch.undo()
    path=root/'source/app/services/ticket_assistant.py';path.write_text(path.read_text()+'\n# changed\n')
    with pytest.raises(ValueError,match='source changed'):live.verified(root)


def test_bundle_and_prompt_tampering_rejected(tmp_path,quote_file):
    root=prepared(tmp_path,quote_file)
    path=root/'quoted/evidence/prompts/PS01.json';path.write_text('[]')
    with pytest.raises(ValueError,match='asset changed'):live.verified(root)


@pytest.mark.parametrize('key,value',[('requests',30),('tokens',9999999),('cost',.36)])
def test_aggregate_budget_exhaustion_before_dispatch(quote_file,key,value):
    q=read_json(quote_file);prior=dict(requests=0,tokens=0,cost=0);prior[key]=value
    with pytest.raises(ValueError,match='before worker dispatch'):
        live.reserve_slot(dict(slots={'old':dict(reservation=prior)}),q['rows'][0],q['reservation'])


def test_unknown_usage_poisoned_even_with_another_attempt_remaining():
    limits=dict(max_requests=2,max_tokens=100000,max_cost=1,max_output_tokens=8192,rates=live.PEAK_RATES)
    b=CallBudget(limits);r=b.reserve([('human','hello')])
    with pytest.raises(BudgetStop):b.record(r,SimpleNamespace(usage_metadata=None))
    with pytest.raises(BudgetStop):b.reserve([('human','hello')])
    assert b.calls==1 and r['usage'] is None


def test_prompt_and_input_bounds_checked_before_transport():
    messages=[('human','approved')]
    limits=dict(max_requests=1,max_tokens=100000,max_cost=1,max_output_tokens=8192,
                rates=live.PEAK_RATES,prompt_sha256=digest([dict(role='human',content='approved')]),input_tokens_per_request=9999)
    b=CallBudget(limits)
    with pytest.raises(BudgetStop,match='prompt changed'):b.reserve([('human','different')])
    assert b.calls==0
    limits['input_tokens_per_request']=1;b=CallBudget(limits)
    with pytest.raises(BudgetStop,match='input reservation'):b.reserve(messages)
    assert b.calls==0


def test_incomplete_prior_request_prevents_second_attempt():
    b=CallBudget(dict(max_requests=2,max_tokens=100000,max_cost=1,max_output_tokens=8192,rates=live.PEAK_RATES))
    b.reserve([('human','first')])
    with pytest.raises(BudgetStop,match='unresolved'):b.reserve([('human','second')])
    assert b.calls==1


def test_interrupted_live_slot_cannot_resume(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file);ledger=read_json(root/'ledger.json')
    ledger['slots']['PS01-1']=dict(state='RUNNING',reservation=dict(requests=1,tokens=10000,cost=.01))
    atomic(root/'ledger.json',ledger)
    monkeypatch.setattr(live,'credentials',lambda *a:pytest.fail('credentials should not be read'))
    with pytest.raises(ValueError,match='unresolved'):
        live.execute(root,approve_estimate=read_json(quote_file)['estimate_sha256'],budget_usd=.36,credentials_file='missing')
    assert read_json(root/'ledger.json')['slots']['PS01-1']['state']=='INTERRUPTED'
    assert not (root/'slots/PS01-1').exists()


def test_fee_uses_measured_cache_and_explicit_request_period(quote_file):
    stamp=lambda t:datetime.fromisoformat(t).timestamp()
    receipt=dict(usage=dict(input_tokens=100,output_tokens=10,total_tokens=110,input_token_details=dict(cache_read=40)),
                 started_at=stamp('2026-10-26T04:30:00+00:00'),finished_at=stamp('2026-10-26T04:30:01+00:00'))
    rates=read_json(quote_file)['rates']
    assert live.measured_cost(receipt,rates)==pytest.approx((40*.003+60*.15+10*.6)/1000000)
    receipt['finished_at']=stamp('2026-10-26T06:00:01+00:00')
    assert live.measured_cost(receipt,rates) is None
    receipt['finished_at']=receipt['started_at'];receipt['usage']['input_token_details']['cache_read']=101
    assert live.measured_cost(receipt,rates) is None


@pytest.mark.parametrize('failure',['missing_usage','connection_error'])
def test_worker_uncertain_transport_has_one_attempt_and_no_network(tmp_path,quote_file,failure):
    q=read_json(quote_file);bundle=read_json(quote_file.parent/'input-bundles/PS12.json')
    row=next(r for r in q['rows'] if r['profile_id']=='PS12')
    # The synthetic quote prompt is replaced with this test's captured app prompt;
    # prompt binding is tested independently above. No live endpoint is enabled.
    limits=live.live_limits(row,q);limits.pop('prompt_sha256');limits.pop('input_tokens_per_request')
    limits.update(max_tokens=100000,max_cost=1)
    atomic(tmp_path/'job.json',dict(**bundle,live_limits=limits,variant='current_live',slot_id='simulation',experiment_id='test',repetition=1))
    code='''import asyncio,json
from pathlib import Path
from unittest.mock import patch
from langchain_core.messages import AIMessage
from evals.worker import guard,execute
root=Path.cwd();guard(root)  # DNS/sockets forbidden, including DeepSeek.
from app.services import llm_service
class Fake:
 async def ainvoke(self,messages):
  p=root/'attempts.json';n=json.loads(p.read_text()) if p.exists() else 0;p.write_text(json.dumps(n+1))
  if FAILURE=='connection_error':raise ConnectionError('synthetic unavailable')
  return AIMessage(content='{}')
with patch.object(llm_service,'get_llm',return_value=Fake()):
 asyncio.run(execute(json.loads((root/'job.json').read_text()),root))
'''.replace("FAILURE",repr(failure))
    env=child_env(tmp_path,ROOT/'backend');env['LLM_MODEL_NAME']='deepseek-flash'
    done=subprocess.run([sys.executable,'-B','-c',code],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=15)
    assert done.returncode==0,done.stderr
    assert read_json(tmp_path/'attempts.json')==1
    engineering=read_json(tmp_path/'engineering.json')
    assert engineering.get('budget_stop') or engineering.get('uncertain_usage')
    assert engineering['actual_live_model_requests']==1  # simulated transport, not a paid call


def test_model_failure_is_not_hidden_by_correct_final_fallback(tmp_path):
    profile=next(c for c in load_cases() if c['id']=='PS03');base,_,_,routes=load_case('T04')
    inputs=profile_inputs(profile);header={k:base.model_dump(mode='json')[k] for k in
        ('case_id','case_version','input_sha256','clock','data_origin','execution_mode')}
    header.update(case_version='2.0-draft-PS03',input_sha256=digest(inputs))
    atomic(tmp_path/'job.json',dict(case=header,inputs=inputs,routes=routes,variant='current_replay',slot_id='offline',experiment_id='test',repetition=1))
    done=subprocess.run([sys.executable,'-B','-m','evals.worker'],cwd=tmp_path,env=child_env(tmp_path,ROOT/'backend'),capture_output=True,text=True,timeout=15)
    assert done.returncode==0,done.stderr
    obs=read_json(tmp_path/'observation.json');obs['raw_model']={'ids':['SYN_T04_C','SYN_T04_A']}
    assert next(c for c in score(profile,obs,diagnostic=True)['checks'] if c['rule']=='conditional_rank')['status']=='PASS'
    prompt=read_json(tmp_path/'engineering.json')['captured_prompts'][0]
    checks=live.extra_checks(profile,obs,dict(inputs=inputs,prompt=prompt),True)
    assert next(c for c in checks if c['rule']=='conditional_rank' and c['layer']=='model')['status']=='FAIL'


def test_partial_report_keeps_all_slots_and_no_model_trace(tmp_path,quote_file):
    root=prepared(tmp_path,quote_file);plan=read_json(root/'manifest.json')
    before=live.report(root)
    assert before['actual_live_model_requests']==0 and before['planned_slots']==30 and not before['complete']
    assert all(r['formal_checks']==[] and r['formal_quality_score'] is None for r in before['results'])
    work=root/'slots/PS04-1';work.mkdir()
    bundle=read_json(root/'quoted/input-bundles/PS04.json')
    atomic(work/'job.json',dict(**bundle,variant='current_replay',slot_id='PS04-1',experiment_id=plan['experiment_id'],repetition=1))
    done=subprocess.run([sys.executable,'-B','-m','evals.worker'],cwd=work,env=child_env(work,root/'source'),capture_output=True,text=True,timeout=15)
    assert done.returncode==0,done.stderr
    ledger=read_json(root/'ledger.json');ledger['slots']['PS04-1']=dict(state='COMPLETED',reservation=dict(requests=0,tokens=0,cost=0),
        evidence={name:sha(work/name) for name in ['job.json','observation.json','engineering.json']})
    atomic(root/'ledger.json',ledger)
    report=live.report(root);row=next(r for r in report['results'] if r['slot_id']=='PS04-1')
    assert row['actual_live_model_requests']==0 and row['reference_status']=='pending_human'
    assert row['local_trace'] and (root/row['local_trace']).is_file()
    assert next(c for c in row['checks'] if c['rule']=='expected_execution_transport')['status']=='PASS'
    assert row['source_id']=='T04' and row['data_origin']=='synthetic'
    assert sum(r['execution_state']=='NOT_RUN' for r in report['results'])==29
    (work/'observation.json').write_text('{}')
    with pytest.raises(ValueError,match='evidence changed'):live.report(root)
