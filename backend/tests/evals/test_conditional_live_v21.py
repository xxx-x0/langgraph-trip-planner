"""Paired v2.1 execution tests; fixture workers and fake transports cannot network."""
import ast
import copy
from datetime import datetime
import inspect
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import sys

import pytest
from langchain_core.messages import HumanMessage,SystemMessage

from evals import conditional_live_v21 as live
from evals import prompt_variants
from evals.budget import BudgetStop,CallBudget,message_payload,prompt_bound,estimated_cost
from evals.conditional_v21 import replay,load_cases,profile_inputs
from evals.contracts import digest
from evals.dataset import read_json
from evals.experiment import atomic,child_env,sha,ROOT


@pytest.fixture(scope='module')
def quote_file(tmp_path_factory):
    root=tmp_path_factory.mktemp('v21-quote');replay(root/'preflight')
    manifest=read_json(root/'preflight/manifest.json')
    rates=dict(model='deepseek-flash',currency='USD',**live.common.PEAK_RATES,
        input_miss_off_peak_per_million=.15,input_hit_off_peak_per_million=.003,output_off_peak_per_million=.6)
    rows=[];assets={}
    for c in load_cases():
        work=root/'preflight'/c['id'];job=read_json(work/'job.json');e=read_json(work/'engineering.json')
        active=c['id'] in live.MODEL_PROFILES
        relative=f"input-bundles/{c['id']}.json";(root/'input-bundles').mkdir(exist_ok=True)
        atomic(root/relative,{k:job[k] for k in ['case','inputs','routes']});assets[relative]=sha(root/relative)
        for variant in (['route_enriched','route_ablated'] if c['id']=='PS12' else ['current']):
            unit=c['id'] if variant=='current' else c['id']+'_'+variant
            prompt=e['captured_prompts'][0] if active else None
            if c['id']=='PS12':
                # Synthetic legacy protocol fixture, not a new paid quote for current code.
                prompt=[dict(role='system',content='Offline legacy-budget fixture'),
                        dict(role='human',content='prefix\n'+prompt_variants.START+prompt_variants.END+'suffix\n')]
                prompt[-1]['content']+='y'*(6291-prompt_bound(prompt_variants.ablate(prompt)))
                prompt[-1]['content']=prompt[-1]['content'].replace(prompt_variants.START,
                    prompt_variants.START+'x'*(13682-prompt_bound(prompt)))
            if variant=='route_ablated':prompt=prompt_variants.ablate(prompt)
            n=prompt_bound(prompt) if prompt else 0;reps=5 if c['id']=='PS12' else 1
            attempts=(2 if c['id']=='PS12' else 1) if active else 0
            row=dict(unit_id=unit,profile_id=c['id'],variant=variant,source_id=c['source_id'],
                source_family=c['source_family'],source_split=c['source_split'],data_origin=job['case']['data_origin'],
                input_sha256=digest(profile_inputs(c)),case_version='2.1-draft-'+c['id'],reference_status='pending_human',
                reference_sha256=c['reference_sha256'],model_path=active,repetitions=reps,
                nominal_requests=reps if active else 0,max_attempts_per_slot=attempts,max_requests=attempts*reps,
                input_reservation_per_request=n,max_output_tokens=8192 if active else 0,
                max_tokens_per_slot=attempts*(n+8192),max_cost_per_slot=round(estimated_cost(attempts*n,attempts*8192,rates),10),
                prompt_sha256=digest(prompt) if prompt else None,bundle=relative)
            rows.append(row)
            if prompt:
                path=root/'prompts'/f'{unit}.json';path.parent.mkdir(exist_ok=True);atomic(path,prompt)
                assets[str(path.relative_to(root))]=sha(path)
    path=root/'scripts/prompt_ablation.py';path.parent.mkdir();path.write_text(inspect.getsource(prompt_variants.ablate))
    assets[str(path.relative_to(root))]=sha(path)
    slots=[dict(slot_id=r['unit_id']+'-1',unit_id=r['unit_id'],profile_id=r['profile_id'],variant='current',repetition=1)
           for r in rows if r['profile_id']!='PS12']
    for rep in range(1,6):
        for variant in (['route_enriched','route_ablated'] if rep%2 else ['route_ablated','route_enriched']):
            unit='PS12_'+variant;slots.append(dict(slot_id=unit+f'-{rep}',unit_id=unit,profile_id='PS12',variant=variant,repetition=rep))
    q=dict(schema='conditional-v21-budget-proposal-v1',model=live.common.MODEL,rates=rates,
        source_sha256=manifest['source_sha256'],source_manifest='preflight/manifest.json',
        conditional_data_sha256=digest(load_cases()),rows=rows,slots=slots,assets=assets,
        planned_slots=21,nominal_live_requests=12,max_live_requests=22,concurrency=1,slot_seconds=120,wall_seconds=3600,
        prompt_intervention=dict(version=prompt_variants.VERSION),
        reservation=dict(max_requests=22,total_tokens=sum(r['max_tokens_per_slot']*r['repetitions'] for r in rows),
            calculated_peak_cost_usd=round(sum(r['max_cost_per_slot']*r['repetitions'] for r in rows),10),requested_budget_usd=.30))
    q['estimate_sha256']=digest(q);atomic(root/'quote.json',q);return root/'quote.json'


def prepared(tmp_path,quote_file):
    root=tmp_path/'run';live.prepare(root,quote_file);return root


def test_authorization_and_wrong_budget_fail_before_credentials_and_dispatch(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file)
    def forbidden(*a,**kw):pytest.fail('must reject before credentials or dispatch')
    monkeypatch.setattr(live.common,'credentials',forbidden);monkeypatch.setattr(live.common.subprocess,'Popen',forbidden)
    for kwargs in [{},{'approve_estimate':'wrong','budget_usd':.30,'credentials_file':'missing'},
                   {'approve_estimate':read_json(quote_file)['estimate_sha256'],'budget_usd':.31,'credentials_file':'missing'}]:
        with pytest.raises(ValueError,match='locked'):live.execute(root,**kwargs)
    assert read_json(root/'ledger.json')['slots']=={}


@pytest.mark.parametrize('kind',['repetitions','order','model','money','variant','input'])
def test_rehashed_quote_drift_rejected(tmp_path,quote_file,kind):
    q=read_json(quote_file);q.pop('estimate_sha256')
    if kind=='repetitions':q['rows'][-1]['repetitions']=6
    elif kind=='order':q['slots'][-1],q['slots'][-2]=q['slots'][-2],q['slots'][-1]
    elif kind=='model':q['model']['name']='deepseek-v4-pro'
    elif kind=='money':q['reservation']['requested_budget_usd']=.31
    elif kind=='variant':q['rows'][-1]['variant']='route_enriched'
    else:q['rows'][0]['input_sha256']='0'*64
    q['estimate_sha256']=digest(q);path=tmp_path/'bad.json';atomic(path,q)
    with pytest.raises(ValueError):live.load_quote(path)


def test_frozen_assets_source_and_partial_denominator(tmp_path,quote_file):
    root=prepared(tmp_path,quote_file);report=live.report(root)
    assert len(report['results'])==21 and report['actual_live_model_requests']==0
    assert report['formal_quality_score'] is None and all(r['formal_checks']==[] for r in report['results'])
    assert all(arm['planned']==5 and arm['completed']==0 for arm in report['arms'])
    path=root/'quoted/prompts/PS12_route_ablated.json';path.write_text('[]')
    with pytest.raises(ValueError,match='asset changed'):live.verified(root)


def test_ablation_preserves_other_messages_and_binds_the_correct_budget(quote_file):
    q=read_json(quote_file);source=read_json(quote_file.parent/'prompts/PS12_route_enriched.json')
    control=read_json(quote_file.parent/'prompts/PS12_route_ablated.json');before=copy.deepcopy(source)
    messages=[SystemMessage(content=source[0]['content']),HumanMessage(content=source[1]['content'])]
    transformed=prompt_variants.for_variant(messages,'route_ablated')
    assert message_payload(transformed)==control and source==before
    assert messages[1].content==source[1]['content'] and transformed[0].content==messages[0].content
    row=next(r for r in q['rows'] if r['variant']=='route_ablated')
    b=CallBudget(live.common.live_limits(row,q))
    with pytest.raises(BudgetStop,match='prompt changed'):b.reserve(messages)
    assert b.calls==0
    b=CallBudget(live.common.live_limits(row,q));receipt=b.reserve(transformed)
    assert receipt['input_token_reservation']==6291 and b.calls==1


@pytest.mark.parametrize('body',['missing',prompt_variants.END+prompt_variants.START,
    prompt_variants.START+prompt_variants.START+prompt_variants.END])
def test_ablation_rejects_unknown_or_ambiguous_layout_before_dispatch(body):
    with pytest.raises(ValueError):prompt_variants.ablate([dict(role='human',content=body)])


@pytest.mark.parametrize('variant',['route_enriched','route_ablated'])
def test_guarded_worker_captures_exact_approved_variant_without_network(tmp_path,quote_file,variant):
    q=read_json(quote_file);row=next(r for r in q['rows'] if r['profile_id']=='PS12' and r['variant']==variant)
    bundle=read_json(quote_file.parent/row['bundle'])
    atomic(tmp_path/'job.json',dict(**bundle,variant='current_replay',eval_input_variant=variant,
        experiment_id='test-offline-only',slot_id=variant,repetition=1))
    done=subprocess.run([sys.executable,'-B','-m','evals.worker'],cwd=tmp_path,
        env=child_env(tmp_path,ROOT/'backend'),capture_output=True,text=True,timeout=20)
    assert done.returncode==0,done.stderr
    e=read_json(tmp_path/'engineering.json');obs=read_json(tmp_path/'observation.json')
    assert e['actual_live_model_requests']==0 and e['model_substitute_calls']==1
    current=read_json(quote_file.parent/'preflight/PS12/engineering.json')['captured_prompts'][0]
    if variant=='route_ablated':current=prompt_variants.ablate(current)
    assert e['captured_prompts'][0]==current
    # Changed production prompts cannot spend the old approval, even with its budget left.
    assert digest(current)!=row['prompt_sha256']
    budget=CallBudget(live.common.live_limits(row,q))
    with pytest.raises(BudgetStop,match='prompt changed'):budget.reserve(current)
    assert budget.calls==0
    expected_alias='anon_'+hmac.new(b'isolated-eval-local-alias-key-0001',
        json.dumps(e['captured_prompts'][0],ensure_ascii=False,sort_keys=True).encode(),hashlib.sha256).hexdigest()[:24]
    assert next(s for s in obs['trace']['spans'] if s['name']=='model_call')['facts']['prompt_alias']==expected_alias
    assert len(e['route_context_input']['directed_edges'])==23 and len(e['route_context_input']['unknown_edges'])==7
    assert obs['execution_status']=='success'


def test_zero_model_and_ledger_reservation_cannot_be_rewritten(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file);ledger=read_json(root/'ledger.json')
    ledger['slots']['PS03-1']=dict(state='COMPLETED',reservation=dict(requests=0,tokens=0,cost=0),evidence={})
    atomic(root/'ledger.json',ledger)
    monkeypatch.setattr(live.common,'credentials',lambda *a:pytest.fail('no credentials'))
    with pytest.raises(ValueError,match='reservation changed'):
        live.execute(root,approve_estimate=read_json(quote_file)['estimate_sha256'],budget_usd=.30,credentials_file='missing')


def test_unknown_prior_live_outcome_blocks_resume(tmp_path,quote_file,monkeypatch):
    root=prepared(tmp_path,quote_file);ledger=read_json(root/'ledger.json')
    ledger['slots']['PS12_route_enriched-1']=dict(state='RUNNING')
    atomic(root/'ledger.json',ledger)
    monkeypatch.setattr(live.common,'credentials',lambda *a:pytest.fail('no credentials'))
    with pytest.raises(ValueError,match='unresolved'):
        live.execute(root,approve_estimate=read_json(quote_file)['estimate_sha256'],budget_usd=.30,credentials_file='missing')
    assert read_json(root/'ledger.json')['slots']['PS12_route_enriched-1']['state']=='INTERRUPTED'


def test_peak_nonholiday_cache_cost_and_unknown_periods(quote_file):
    rates=read_json(quote_file)['rates'];stamp=lambda s:datetime.fromisoformat(s).timestamp()
    r=dict(usage=dict(input_tokens=100,output_tokens=10,total_tokens=110,input_token_details=dict(cache_read=40)),
        started_at=stamp('2026-10-26T06:30:00+00:00'),finished_at=stamp('2026-10-26T06:30:01+00:00'))
    assert live.measured_cost(r,rates,['2026-10-26'])==pytest.approx((40*.006+60*.3+10*1.2)/1000000)
    assert live.measured_cost(r,rates,[]) is None
    r['started_at']=stamp('2026-10-26T05:59:59+00:00')
    assert live.measured_cost(r,rates,['2026-10-26']) is None


def test_lower_route_time_with_constraint_failure_is_not_an_improvement(quote_file):
    q=read_json(quote_file);bundle=read_json(quote_file.parent/'input-bundles/PS12.json')
    day=copy.deepcopy(bundle['inputs']['day_detail'])
    for segment in day['route_segments']:segment['duration']='1分钟'
    checks=[dict(rule=r,layer='system',status='PASS') for r in
        ['R-LOCK','R-REMOVED','R-MEAL','R-MANUAL','R-FACT','R-DURATION','R-REST','R-WINDOW']]
    got=live.route_metrics(bundle['inputs'],bundle['routes'],dict(execution_status='success',final_output=day),checks)
    assert got['classification']=='invalid_or_unverified_constraints'
    assert got['route_errors'] and not got['hard_constraints_valid']
