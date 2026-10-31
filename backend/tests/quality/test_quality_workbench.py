"""Published snapshots and HTTP contracts; no application startup or business database."""
import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from app.api.routes.quality import router
from app.services import quality_reports as q


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('QUALITY_WORKBENCH_ENABLED', '1')
    monkeypatch.setenv('QUALITY_REPORT_DIR', str(tmp_path))
    row = dict(run_id='current_live-R02-1', case_id='R02', title='锁定第二景点', target='day_rearrangement',
        variant='current_live', repetition=1, split='dev', data_origin='synthetic', provenance='live_model_with_replay',
        input_sha256='input', case_version='v1', reference_status='pending_human', diagnostic_only=True, formal_quality_score=None,
        execution_state='COMPLETED', operation_status='success', business_outcome='adjusted', started_at='2026-10-24T13:18:00+00:00',
        wall_seconds=2, usage={'input_tokens':100,'output_tokens':20,'total_tokens':120}, actual_requests=1, cost_usd=.001, peak_cost_usd=.002,
        categories=['model_issue'], trace_status='local_only',
        checks=[dict(rule_id='R-INTENT',layer='model',status='FAIL',expected=['C','B','A'],actual=['A','B','C'],category='model_issue')],
        detail={'trace':{'status':'local_only','spans':[],'langsmith_url':None}})
    rows = []
    for i in range(1,4):
        r = copy.deepcopy(row); r['run_id']=f'current_live-R02-{i}'; r['repetition']=i; rows.append(r)
    baseline = copy.deepcopy(row); baseline.update(run_id='baseline-R02-1',variant='baseline',provenance='baseline',actual_requests=0,usage=None,cost_usd=0,categories=[])
    baseline['checks']=[dict(rule_id='R-INTENT',layer='model',status='NOT_APPLICABLE')]; rows.append(baseline)
    injected = copy.deepcopy(row); injected.update(run_id='current_live-T13-1',case_id='T13',provenance='injected_failure',actual_requests=0,usage=None,cost_usd=0,categories=['fault_injection'])
    injected['checks']=[dict(rule_id='T-VALID',layer='model',status='FAIL')]; rows.append(injected)
    doc = dict(schema=q.SCHEMA,experiment_id='eval_'+'a'*32,created_at='2026-10-24',published_at='2026-10-25',
        title='测试报告',dataset_sha256='dataset',evaluator_versions=['rules-v1.1'],fixture_sha256='fixture',runs=rows)
    path=tmp_path/(doc['experiment_id']+'.json'); path.write_text(json.dumps(doc))
    return doc, path


@pytest.fixture
def client():
    app=FastAPI();app.include_router(router,prefix='/api')
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')


@pytest.mark.asyncio
async def test_disabled_never_reads_reports(snapshot, client, monkeypatch):
    monkeypatch.setenv('QUALITY_WORKBENCH_ENABLED','0')
    monkeypatch.setattr(q,'snapshots',lambda: (_ for _ in ()).throw(AssertionError('must not read')))
    async with client:
        assert (await client.get('/api/quality/status')).json()['enabled'] is False
        assert (await client.get('/api/quality/runs',params={'experiment_id':snapshot[0]['experiment_id']})).status_code==403
        assert (await client.post('/api/quality/runs')).status_code==405


@pytest.mark.asyncio
async def test_filtered_summary_pagination_and_cursor_identity(snapshot, client):
    doc,_=snapshot
    params={'experiment_id':doc['experiment_id'],'variant':'current_live','category':'model_issue','limit':2}
    async with client:
        body=(await client.get('/api/quality/runs',params=params)).json()
        assert body['total']==3 and len(body['items'])==2
        assert body['summary']['real_requests']==3 and body['summary']['tokens']==360
        assert body['summary']['formal_quality_score'] is None and body['summary']['pending_cases']==1
        params['cursor']=body['next_cursor']
        second=(await client.get('/api/quality/runs',params=params)).json()
        assert len(second['items'])==1 and second['next_cursor'] is None
        params['category']='fault_injection'
        assert (await client.get('/api/quality/runs',params=params)).status_code==422


def test_injection_excluded_from_real_model_and_usage(snapshot):
    result=q.summary(snapshot[0]['runs'])
    assert result['real_requests']==3 and result['real_model_runs']==3
    assert result['metrics']['model_raw']['F']==3
    assert result['metrics']['injected_model']['F']==1
    assert result['cost_usd']==pytest.approx(.003)


def test_missing_usage_is_not_zero_cost(snapshot):
    row=copy.deepcopy(snapshot[0]['runs'][0]);row['usage']=None;row['cost_usd']=None
    result=q.summary([row])
    assert result['usage_known_runs']==0 and result['cost_known_runs']==0
    assert result['cost_usd'] is None and result['real_model_runs']==1


def test_comparison_pairs_identity_and_never_replicates_baseline(snapshot):
    doc,_=snapshot
    result=q.compare(doc,doc,'baseline','current_live')
    assert result['compatible'] and result['formal_delta'] is None
    assert result['comparable_pairs']==1 and result['missing_pairs']==3
    changed=copy.deepcopy(doc);changed['evaluator_versions']=['rules-v2']
    assert not q.compare(doc,changed,'baseline','current_live')['compatible']
    changed=copy.deepcopy(doc);changed['runs'][0]['input_sha256']='changed'
    assert q.compare(doc,changed,'baseline','current_live')['comparable_pairs']==0


@pytest.mark.asyncio
async def test_detail_export_not_found_and_no_mutations(snapshot, client):
    doc,path=snapshot;before=path.read_bytes()
    async with client:
        response=await client.get('/api/quality/runs/current_live-R02-1',params={'experiment_id':doc['experiment_id'],'download':'true'})
        assert response.status_code==200 and 'attachment' in response.headers['content-disposition']
        assert response.json()['formal_quality_score'] is None
        assert (await client.get('/api/quality/runs/unknown',params={'experiment_id':doc['experiment_id']})).status_code==404
        assert (await client.get('/api/quality/experiments/compare',params={'left':doc['experiment_id'],'right':doc['experiment_id'],'left_variant':'bogus'})).status_code==422
        assert (await client.post('/api/quality/experiments/'+doc['experiment_id']+'/export')).status_code==405
    assert path.read_bytes()==before


def test_missing_corrupt_and_symlink_files(tmp_path, monkeypatch):
    monkeypatch.setenv('QUALITY_REPORT_DIR',str(tmp_path))
    assert q.snapshots()==([],0)
    (tmp_path/'eval_broken.json').write_text('{')
    target=tmp_path/'other.json';target.write_text('{}');(tmp_path/'eval_link.json').symlink_to(target)
    assert q.snapshots()==([],2)


def test_redaction_and_fact_allowlist():
    secret='sk-abcdefghijklmno'
    value={'hint':f'联系 13812345678 somebody@example.com Bearer abcdef {secret} /Users/finn/private.txt',
        'api_key':secret,'user_id':'real-person','raw_prompt':'private','address':'私人地址','query':{'priority':'daytime'}}
    serialized=json.dumps(q.clean(value,facts=True),ensure_ascii=False)
    for s in (secret,'13812345678','somebody@example.com','real-person','private.txt','私人地址','abcdef'):
        assert s not in serialized
    assert 'daytime' in serialized


def test_error_and_na_denominators_and_date_filters(snapshot):
    doc,_=snapshot;row=copy.deepcopy(doc['runs'][0])
    row['checks']=[{'rule_id':'T-MARGIN','layer':'system','status':s} for s in ['PASS','FAIL','ERROR','NOT_EVALUATED','NOT_APPLICABLE']]
    count=q.summary([row])['diagnostic_counts']
    assert count=={'P':1,'F':1,'E':1,'U':1,'NA':1,'applicable':4}
    assert not q.select(doc,{'since':'2026-10-25'})
    assert len(q.select(doc,{'until':'2026-10-24','q':'R02'}))==4

@pytest.fixture
def frozen(tmp_path):
    from evals.workbench import sha
    root=tmp_path/'experiment';dataset=root/'source/evals/datasets';(dataset/'cases').mkdir(parents=True);(dataset/'inputs').mkdir()
    case=dict(case_id='T01',title='人工输入',input_path='inputs/T01.json',input_sha256='input',reference_sha256='reference',
        target='ticket_recommendation',split='dev',data_origin='synthetic',execution_mode='live_model_with_replay',
        case_version='v1',tool_mode='replay',sources=[{'origin':'synthetic'}],annotation={'status':'pending_human'})
    (dataset/'cases/T01.json').write_text(json.dumps(case))
    (dataset/'inputs/T01.json').write_text(json.dumps({'query':{'priority':'price'},'api_key':'sk-privateABC12345'}))
    work=root/'slots/current_live-T01-1';work.mkdir(parents=True)
    obs=dict(input_sha256='input',run_id=work.name,provenance='live_model_with_replay',execution_status='success',
        business_outcome='recommended',usage={'input_tokens':10,'output_tokens':5,'total_tokens':15},timings={'operation_wall_seconds':1},
        trace={'operation_id':'op','spans':[{'id':'op','parent_id':None,'name':'model_call','start_time':'2026-10-24T13:00:00Z','facts':{'total_tokens':15,'api_key':'sk-privateABC12345'}}]})
    (work/'observation.json').write_text(json.dumps(obs));(work/'engineering.json').write_text(json.dumps({'actual_live_model_requests':1}))
    slot=dict(slot_id=work.name,case_id='T01',variant='current_live',repetition=1)
    plan=dict(plan_sha256='plan',experiment_id='eval_'+'a'*32,source_files={str(p.relative_to(root/'source')):sha(p) for p in dataset.rglob('*.json')},
        slots=[slot],trace_export=False,created_at=1792846968,source_sha256='source',dataset_sha256='dataset',model={'name':'test'},limits={'max_cost':1})
    (root/'manifest.json').write_text(json.dumps(plan))
    report=dict(plan_sha256='plan',actual_live_model_requests=1,results=[{**slot,'diagnostic_checks':[],
        'formal_checks':[dict(rule_id='T-RANK',layer='model',status='PASS',evaluator_version='v1',actual=['A'],expected=['A'])]}])
    (root/'report.json').write_text(json.dumps(report))
    ledger=dict(plan_sha256='plan',slots={work.name:{'state':'COMPLETED','observation_sha256':sha(work/'observation.json'),'engineering_sha256':sha(work/'engineering.json')}})
    (root/'ledger.json').write_text(json.dumps(ledger))
    return root


def test_publish_demotes_pending_reference_and_strips_credentials(frozen):
    from evals.workbench import build_snapshot
    doc=build_snapshot(frozen,None,None)
    assert doc['formal_quality_score'] is None
    row=doc['runs'][0]
    assert row['diagnostic_only'] and row['checks'][0]['status']=='PASS'
    assert row['detail']['trace']['spans'][0]['facts']=={'total_tokens':15}
    assert 'sk-privateABC12345' not in json.dumps(doc)
    assert row['cost_usd'] is None


def test_publish_rejects_changed_evidence_and_foreign_triage(frozen, tmp_path):
    from evals.workbench import build_snapshot
    triage=tmp_path/'triage.json';triage.write_text(json.dumps({'plan_sha256':'different','findings':[]}))
    with pytest.raises(ValueError,match='another plan'):build_snapshot(frozen,None,triage)
    (frozen/'slots/current_live-T01-1/observation.json').write_text('{}')
    with pytest.raises(ValueError,match='changed'):build_snapshot(frozen,None,None)


def test_publish_rejects_changed_fixture_and_escaping_path(frozen):
    from evals.workbench import build_snapshot,within
    with pytest.raises(ValueError,match='outside'):within(frozen,'../secret')
    (frozen/'source/evals/datasets/inputs/T01.json').write_text('{}')
    with pytest.raises(ValueError,match='source changed'):build_snapshot(frozen,None,None)


def test_multicity_snapshot_facts_preserved_without_original_business_ids():
    source={'id':'mc_private_real_id','plan':{'transfers':[{'from_stop':'a','to_stop':'b','leg':{'station_buffer_minutes':45}}]},
        'snapshots':{'a':{'request':{'city':'苏州'},'days_detail':[{'locked_attraction_names':['留园'],'timeline_schedule':[]}]}}}
    projected=q.clean(source,facts=True)
    assert projected['id'].startswith('anon_')
    assert projected['plan']['transfers'][0]['leg']['station_buffer_minutes']==45
    assert projected['snapshots'][0]['snapshot']['days_detail'][0]['locked_attraction_names']==['留园']
    assert 'mc_private_real_id' not in json.dumps(projected)


def test_malformed_published_row_is_reported_invalid(snapshot):
    doc,path=snapshot
    doc['runs'][0]['checks'][0]['status']='UNKNOWN_PASS'
    path.write_text(json.dumps(doc));q._read_snapshot.cache_clear()
    assert q.snapshots()==([],1)
