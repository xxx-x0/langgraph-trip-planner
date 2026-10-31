"""P3 executes real app paths in disposable processes, never live providers."""
import json
from types import SimpleNamespace
import pytest
from evals.budget import CallBudget,BudgetStop,RATES,estimated_cost
from evals.dataset import read_json
from evals.experiment import make_plan,execute_plan,export_report,verified_plan,atomic,child_env,lock
from evals.estimate import estimate

@pytest.fixture(scope='module')
def experiment(tmp_path_factory):
    root=tmp_path_factory.mktemp('eval-isolation')/'run'
    make_plan(root,case_ids=['T01','T07','T08','T09','T13','T14','T15','T16','T17','T18','R01','R07','R08','R10','R11','R12'],wall_seconds=180)
    return root,execute_plan(root)

@pytest.mark.parametrize('cid,outcome',[('T01','recommended'),('T07','empty_unavailable'),('T08','recommended'),('T09','recommended'),('T13','recommended'),('T14','empty_conflict'),('T15','fallback'),('T16','cancelled'),('T17','conflict'),('T18','recommended'),('R01','adjusted'),('R07','preserved_original'),('R08','rejected'),('R10','improved'),('R11','timeout'),('R12','conflict')])
def test_real_app_execution(experiment,cid,outcome):
    root,r=experiment;row=next(x for x in r['results'] if x['slot_id']==f'current_replay-{cid}-1')
    assert row['execution_state']=='COMPLETED' and row['business_outcome']==outcome
    assert row['actual_live_model_requests']==0
    assert (root/'slots'/row['slot_id']/'case.sqlite').exists()


def test_pending_references_never_formal_and_outputs_exported(experiment):
    root,r=experiment
    assert r['formal_quality_score'] is None and r['formal_quality_status']=='NOT_EVALUATED'
    assert all(x['diagnostic_only'] and x['formal_checks']==[] for x in r['results'])
    assert all(x['formal_counts']['scored_pass_rate'] is None for x in r['groups'])
    assert r['actual_live_model_requests']==0 and r['model_usage'] is None and r['model_cost'] is None
    assert (root/'checks.csv').exists() and (root/'report.md').exists()


def test_noop_does_not_count_as_intent_success(experiment):
    root,r=experiment
    for variant in ['baseline','current_replay']:
        row=next(x for x in r['results'] if x['slot_id']==variant+'-R01-1')
        assert next(c for c in row['diagnostic_checks'] if c['rule_id']=='R-INTENT' and c['layer']=='system')['status']=='FAIL'
    for row in r['results']:
        if row['variant']=='baseline':assert all(c['status']=='NOT_APPLICABLE' for c in row['diagnostic_checks'] if c['layer']=='model')


def test_independent_save_conflict_and_cancellation_evidence(experiment):
    root,r=experiment
    for cid in ['T13','T15','T16','T17','R07','R08','R11','R12']:
        row=next(x for x in r['results'] if x['slot_id']==f'current_replay-{cid}-1')
        assert next(c for c in row['diagnostic_checks'] if c['rule_id']=='S-PERSIST')['status']=='PASS'
    o=read_json(root/'slots/current_replay-T17-1/observation.json')
    assert o['checkpoint_statuses']=={'old_recommendation':409,'old_basis_preview':409}
    e=read_json(root/'slots/current_replay-R11-1/engineering.json')
    assert e['route_child_cancelled'] and e['requested_operation_deadline_seconds']==110


def test_resume_keeps_completed_evidence(experiment):
    root,r=experiment;p=root/'slots/current_replay-T01-1/observation.json';before=p.read_bytes()
    assert execute_plan(root)['planned_slots']==r['planned_slots'] and p.read_bytes()==before


@pytest.fixture(scope='module')
def model_experiment(tmp_path_factory):
    # v1's quote contract needs a captured model prompt. Numeric goals now skip it.
    root=tmp_path_factory.mktemp('eval-model-quote')/'run'
    make_plan(root,case_ids=['T09','R10'],wall_seconds=180)
    return root,execute_plan(root)


def test_cost_quote_uses_captured_prompts_and_retry_counts(model_experiment):
    root,_=model_experiment;q=estimate(root,repeats=3)
    assert q['calls_made']==0 and q['approved'] is False
    assert q['max_live_requests']>q['nominal_live_requests']==3*len(q['rows'])
    assert q['reservation']['max_cost']>=q['expected_cost_peak_usd_range'][1]


def test_env_rejects_inherited_secrets_database_and_sdk_tracing(tmp_path,monkeypatch):
    for k in ['DATABASE_URL','LLM_API_KEY','OPENAI_API_KEY','LANGSMITH_API_KEY','HTTP_PROXY','OBSERVABILITY_CONFIG_FILE']:monkeypatch.setenv(k,'PRIVATE_SENTINEL')
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    env=child_env(tmp_path,tmp_path/'source')
    assert 'PRIVATE_SENTINEL' not in json.dumps(env)
    assert env['LANGSMITH_TRACING']=='false' and env['DATABASE_URL'].endswith('/case.sqlite')


def test_partial_missing_slots_keep_denominator_then_resume(tmp_path):
    root=tmp_path/'partial';make_plan(root,case_ids=['T01','R01'],variants=['current_replay'])
    r=execute_plan(root,max_slots=1)
    assert [x['execution_state'] for x in r['results']]==['COMPLETED','NOT_RUN']
    assert r['results'][1]['counts']['E']>0 and r['results'][1]['counts']['coverage']==0
    assert execute_plan(root)['groups'][0]['completed']==2


def test_indeterminate_worker_not_automatically_retried(tmp_path):
    root=tmp_path/'interrupted';make_plan(root,case_ids=['T01'],variants=['current_replay'])
    l=read_json(root/'ledger.json');l['slots']['current_replay-T01-1']={'state':'RUNNING'};atomic(root/'ledger.json',l)
    assert execute_plan(root)['results'][0]['execution_state']=='INTERRUPTED'
    assert not(root/'slots/current_replay-T01-1').exists()


def test_cancellation_and_wall_limits(tmp_path):
    root=tmp_path/'cancel';make_plan(root,case_ids=['T01'],variants=['current_replay']);(root/'CANCEL').touch()
    assert execute_plan(root)['results'][0]['execution_state']=='NOT_RUN'
    root=tmp_path/'timeout';make_plan(root,case_ids=['T01'],variants=['current_replay'],slot_seconds=.001)
    r=execute_plan(root);assert r['results'][0]['execution_state']=='TIMEOUT' and r['results'][0]['counts']['E']>0


def test_tampered_source_and_duplicate_runner_rejected(tmp_path):
    root=tmp_path/'tamper';make_plan(root,case_ids=['T01'])
    p=root/'source/app/services/ticket_assistant.py';p.write_text(p.read_text()+'\n# drift\n')
    with pytest.raises(ValueError,match='frozen source changed'):verified_plan(root)
    with lock(tmp_path):
        with pytest.raises(ValueError,match='already running'):
            with lock(tmp_path):pass


def test_repeats_are_not_new_independent_cases(tmp_path):
    root=tmp_path/'repeats';p=make_plan(root,case_ids=['T01','T13','T07'],variants=['current_replay'],repeats=3)
    assert len(p['slots'])==5
    r=export_report(root);assert r['unique_cases']==3 and r['planned_slots']==5

@pytest.mark.parametrize('field,value',[('max_requests',0),('max_tokens',1),('max_cost',0)])
def test_pre_call_budget_guard(field,value):
    limits=dict(max_requests=2,max_tokens=100000,max_cost=1,max_output_tokens=8192,rates=RATES);limits[field]=value;b=CallBudget(limits)
    with pytest.raises(BudgetStop):b.reserve([('human','hello')])
    assert b.calls==0 and b.receipts==[]


def test_usage_is_provider_only_unknown_is_not_zero():
    limits=dict(max_requests=1,max_tokens=100000,max_cost=1,max_output_tokens=8192,rates=RATES)
    b=CallBudget(limits);r=b.reserve([('human','hello')])
    with pytest.raises(BudgetStop):b.record(r,SimpleNamespace(usage_metadata=None))
    assert r['usage'] is None and r['estimated_cost_upper'] is None
    with pytest.raises(BudgetStop):b.reserve([('human','second')])
    b=CallBudget(limits);r=b.reserve([('human','hello')]);b.record(r,SimpleNamespace(usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15}))
    assert r['estimated_cost_upper']==estimated_cost(10,5)


def test_live_cannot_start_without_matching_explicit_quote_approval(model_experiment,tmp_path):
    root,_=model_experiment;q=estimate(root,repeats=1);file=tmp_path/'quote.json';atomic(file,q)
    live=tmp_path/'live';make_plan(live,case_ids=q['case_ids'],variants=['current_live'],repeats=1,estimate_file=file)
    with pytest.raises(ValueError,match='locked'):execute_plan(live)
    with pytest.raises(ValueError,match='locked'):execute_plan(live,approve_estimate='wrong',credentials_file=tmp_path/'missing-secret')
    assert read_json(live/'ledger.json')['slots']=={}


def test_old_price_model_fault_is_explicitly_not_exercised(experiment):
    root,_=experiment
    evidence=read_json(root/'slots/current_replay-T13-1/engineering.json')
    observed=read_json(root/'slots/current_replay-T13-1/observation.json')
    assert evidence['injection_exercised'] is False
    assert evidence['model_substitute_calls']==evidence['actual_live_model_requests']==0
    assert observed['business_outcome']=='recommended' and observed['final_output']['ranked_by']=='metric'


def test_wait_interval_is_supported_but_cannot_overlap_activity():
    from evals.selftest import observation_vector
    from evals.scorers import window_violations
    bundle,obs=observation_vector('R01');day=obs.final_output;hard=bundle[2]['hard_constraints'];routes=bundle[3]
    end=day['timeline_schedule'][0]['start_minutes']
    day['timeline_schedule'].insert(0,dict(kind='wait',ref_name='等待',start_minutes=end,end_minutes=end,duration=0))
    assert 'unknown_timeline_kind' not in window_violations(day,hard,routes)
    day['timeline_schedule'][0]['end_minutes']+=10;day['timeline_schedule'][0]['duration']=10
    assert 'overlap_or_negative_duration' in window_violations(day,hard,routes)


def test_worker_denies_network_references_and_foreign_sqlite(tmp_path):
    import subprocess,sys
    env=child_env(tmp_path,__import__('evals').__path__[0].rsplit('/',1)[0])
    code='''from pathlib import Path
from evals.worker import guard
import socket,sqlite3
root=Path.cwd();guard(root)
blocked=0
for action in [lambda:socket.getaddrinfo('example.com',443),lambda:Path('references/secret.json').read_text(),lambda:sqlite3.connect(str(root/'foreign.sqlite'))]:
 try:action()
 except PermissionError:blocked+=1
assert blocked==3
'''
    p=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert not(tmp_path/'foreign.sqlite').exists()


def test_input_repair_is_only_a_time_text_projection():
    from evals.dataset import load_all
    def scan(v):
        if isinstance(v,dict):
            for row in v.get('timeline_schedule',[]):
                for n,t in [('start_minutes','start_time'),('end_minutes','end_time')]:
                    assert row[t]==f'{row[n]//60:02d}:{row[n]%60:02d}'
            for child in v.values():scan(child)
        elif isinstance(v,list):
            for child in v:scan(child)
    for c,i,*_ in load_all():
        assert c.case_version=='1.0.1-draft';scan(i)
