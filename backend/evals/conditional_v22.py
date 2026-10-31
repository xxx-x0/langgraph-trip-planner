"""New offline observations for route repair. No live-model or judge command."""
import argparse
import copy
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

from .conditional import profile_inputs
from .conditional_v21 import score as score_v21
from .contracts import digest,Observation
from .dataset import read_json,load_case
from .experiment import source_files,sha,atomic,ROOT
from .scorers import day_constraints,MissingEvidence

VERSION='conditional-v2.2'
DATA=Path(__file__).with_name('conditional_cases_v22.json')


def load_cases():
    data=read_json(DATA);cases=data['cases']
    if data['schema']!=VERSION or digest(cases)!=data['content_sha256']:raise ValueError('v2.2 dataset hash mismatch')
    if len(cases)!=12 or {c['id'] for c in cases}!={f'PS{i:02}' for i in range(1,13)}:raise ValueError('12 distinct profiles required')
    for c in cases:
        base,inputs,_,_=load_case(c['source_id'])
        if (c['version']!='2.2-draft' or c['source_input_sha256']!=digest(inputs) or c['reference_sha256']!=digest(c['reference'])
                or c['source_family']!=base.family):raise ValueError('v2.2 source/reference drift')
        if c['id']=='PS12':
            contract=c['reference']['route_contract']
            if contract['default_end_minutes']!=1440 or contract['dinner_start_range']!=[1050,1380]:raise ValueError('route contract drift')
    return cases


def route_reference(case):
    """New reference projection; never edits old references or invokes production code."""
    _,inputs,reference,_=load_case(case['source_id']);reference=copy.deepcopy(reference)
    contract=case['reference']['route_contract']
    window=inputs['day_detail'].get('travel_window') or {}
    reference['hard_constraints']['end_latest']=window.get('end_minutes',contract['default_end_minutes'])
    reference['hard_constraints']['dinner_start_range']=contract['dinner_start_range']
    return reference


def score(case,observation,*,diagnostic=False):
    if (observation.get('case_version')!='2.2-draft-'+case['id'] or observation.get('input_sha256')!=digest(profile_inputs(case))):
        raise ValueError('v2.2 needs new bound observations; old paid outputs cannot be rescored')
    if digest(case['reference'])!=case['reference_sha256']:raise ValueError('reference drift')
    if not case['source_id'].startswith('R'):
        compatible=copy.deepcopy(observation);compatible['case_version']='2.1-draft-'+case['id']
        result=score_v21(case,compatible,diagnostic=diagnostic);result.update(schema=VERSION,evaluator_version=VERSION);return result
    checks=[]
    if case['annotation']['status']!='confirmed' and not diagnostic:checks=[dict(rule='reference',status='NOT_EVALUATED')]
    elif observation.get('execution_status')!='success' or not observation.get('final_output'):
        checks=[dict(rule='execution',status='ERROR',actual=observation.get('execution_status'))]
    else:
        _,inputs,_,routes=load_case(case['source_id'])
        try:
            ok,expected,actual,_=day_constraints('R-ROUTE','system',inputs,route_reference(case),Observation.model_validate(observation),routes)
            checks=[dict(rule='route_goal',status='PASS' if ok else 'FAIL',actual=actual,expected=expected)]
        except (ValueError,KeyError,TypeError,MissingEvidence):checks=[dict(rule='route_goal',status='ERROR')]
    return dict(schema=VERSION,evaluator_version=VERSION,profile_id=case['id'],source_id=case['source_id'],
        reference_status=case['annotation']['status'],diagnostic_only=True,formal_quality_score=None,
        provenance=observation.get('provenance'),checks=checks)


def replay(directory):
    directory=Path(directory).resolve()
    if directory.exists() or directory.is_relative_to(ROOT):raise ValueError('use a fresh outside directory')
    cases=load_cases();directory.mkdir(parents=True,mode=0o700);files={}
    for path in source_files():
        rel=path.relative_to(ROOT/'backend');target=directory/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes());files[str(rel)]=sha(path)
    atomic(directory/'manifest.json',dict(schema=VERSION,mode='offline_only',source_sha256=digest(files),source_files=files,
        dataset_sha256=digest(cases),planned_profiles=[c['id'] for c in cases],
        packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        dependency_locks={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'backend/requirements.txt',ROOT/'backend/requirements.lock.txt',ROOT/'frontend/package-lock.json']},
        real_model_requests=0,judge_calls=0))
    results=[]
    for c in cases:
        base,_,_,routes=load_case(c['source_id']);inputs=profile_inputs(c);model_path=c['id'] in {'PS03','PS05','PS12'}
        header={k:base.model_dump(mode='json')[k] for k in ['case_id','case_version','input_sha256','clock','data_origin','execution_mode']}
        header.update(case_version='2.2-draft-'+c['id'],input_sha256=digest(inputs),execution_mode='live_model_with_replay' if model_path else 'no_model')
        work=directory/c['id'];work.mkdir();atomic(work/'job.json',dict(case=header,inputs=inputs,routes=routes,variant='current_replay',
            slot_id=c['id']+'-offline-v22',experiment_id=directory.name,repetition=1))
        env={k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','TMPDIR','LANG'}}
        env.update(DATABASE_URL='sqlite+aiosqlite:///'+str(work/'case.sqlite'),PYTHONPATH=str(directory/'source'),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        obs=dict(execution_status='worker_error',case_version=header['case_version'],input_sha256=header['input_sha256'],provenance='replay_model')
        try:
            with (work/'worker.log').open('w') as log:
                done=subprocess.run([sys.executable,'-B','-m','evals.worker'],cwd=work,env=env,stdout=log,stderr=log,timeout=120)
            if done.returncode==0:obs=read_json(work/'observation.json')
        except subprocess.TimeoutExpired:obs['execution_status']='worker_timeout'
        try:
            row=score(c,obs,diagnostic=True);row['checks']=[dict(check,layer='system') for check in row['checks']]
            engineering=read_json(work/'engineering.json')
            from .conditional_live import extra_checks
            row['checks']+=extra_checks(c,obs,dict(inputs=inputs,prompt=engineering['captured_prompts'][0] if engineering['captured_prompts'] else []),model_path,
                scorer=score,reference_override=route_reference(c) if c['id']=='PS12' else None)
            row.update(actual_live_model_requests=engineering['actual_live_model_requests'],model_substitute_calls=engineering['model_substitute_calls'],
                source_family=c['source_family'],source_id=c['source_id'],data_origin=header['data_origin'],trace_origin=obs['trace']['data_origin'],
                outcome=obs['business_outcome'],route_comparison=(obs.get('final_output') or {}).get('route_comparison'),evidence=str(work/'observation.json'))
        except (ValueError,KeyError,TypeError,MissingEvidence):
            row=dict(profile_id=c['id'],checks=[dict(rule='execution_or_evidence',layer='engineering',status='ERROR')],diagnostic_only=True,formal_quality_score=None)
        results.append(row)
        atomic(directory/'partial-results.json',dict(planned=12,results=results))
    report=dict(schema=VERSION,planned=12,results=results,formal_quality_score=None,formal_quality_status='NOT_EVALUATED',
        real_model_requests=0,judge_calls=0,provenance='isolated_offline_replay',diagnostic_counts=dict(Counter(c['status'] for r in results for c in r['checks'])),
        limitation='Pending references; deterministic business improvements are distinct from neutral model diagnostics; seen sources are not independent holdout.')
    atomic(directory/'report.json',report);return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['validate','replay']);parser.add_argument('--directory')
    args=parser.parse_args()
    if args.command=='validate':print(dict(schema=VERSION,profiles=len(load_cases()),real_model_requests=0))
    else:
        if not args.directory:parser.error('--directory required')
        result=replay(args.directory);print(dict(planned=12,counts=result['diagnostic_counts'],real_model_requests=0,formal_quality_score=None))


if __name__=='__main__':main()
