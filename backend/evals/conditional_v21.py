"""Versioned v2.1 diagnostics and guarded offline replay; never paid model calls."""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

from .conditional import profile_inputs, score as score_v20
from .contracts import digest
from .dataset import load_case, read_json

VERSION = 'conditional-v2.1'
DATA = Path(__file__).with_name('conditional_cases_v21.json')


def load_cases():
    data = read_json(DATA)
    if data['schema'] != VERSION or digest(data['cases']) != data['content_sha256']:
        raise ValueError('v2.1 dataset hash mismatch')
    if len(data['cases']) != 12 or {c['id'] for c in data['cases']} != {f'PS{i:02}' for i in range(1,13)}:
        raise ValueError('12 unique v2.1 profiles required')
    for c in data['cases']:
        base, inputs, _, _ = load_case(c['source_id'])
        if (digest(inputs) != c['source_input_sha256'] or digest(c['reference']) != c['reference_sha256']
                or c['version'] != '2.1-draft' or c['source_family'] != base.family):
            raise ValueError('v2.1 source/reference binding changed')
    return data['cases']


def score(case, observation, *, diagnostic=False):
    if (observation.get('case_version') != '2.1-draft-'+case['id']
            or observation.get('input_sha256') != digest(profile_inputs(case))):
        raise ValueError('v2.1 requires new observation/version; old paid outputs cannot be reused')
    compatible = copy.deepcopy(observation)
    compatible['case_version'] = '2.0-draft-'+case['id']
    result = score_v20(case, compatible, diagnostic=diagnostic)
    result.update(schema=VERSION,evaluator_version=VERSION)
    if case['annotation']['status'] != 'confirmed' and not diagnostic:
        return result
    output = observation.get('final_output')
    if observation.get('execution_status') != 'success' or not output:
        return result
    if case['reference'].get('rank_scope') == 'known_prices_only':
        inputs = profile_inputs(case); source = {c['id']:c for c in inputs['candidates']}
        ids = [r['candidate']['id'] for r in output['recommendations']]
        values = [source[i]['fare_per_person'] for i in ids if i in source and source[i]['fare_per_person'] is not None]
        for check in result['checks']:
            if check['rule'] == 'declared_order':
                check.update(status=('PASS' if values == sorted(values) else 'FAIL') if values else 'NOT_EVALUATED',
                             actual=values,expected='known prices nondecreasing; unknown placement not ranked')
    expected = case['reference'].get('empty_outcome')
    if expected:
        actual = observation.get('business_outcome')
        result['checks'].append(dict(rule='empty_outcome',status='ERROR' if actual is None else 'PASS' if actual == expected else 'FAIL',
                                     actual=actual,expected=expected))
    return result


def replay(directory):
    directory = Path(directory).resolve(); repo = Path(__file__).resolve().parents[2]
    if directory.exists() or directory.is_relative_to(repo):
        raise ValueError('use a fresh directory outside repository')
    cases = load_cases(); directory.mkdir(parents=True,mode=0o700); source = directory/'source'; source.mkdir()
    files = {}
    for folder in ['app','evals']:
        for path in sorted((repo/'backend'/folder).rglob('*')):
            if path.is_file() and path.suffix in {'.py','.json'} and '__pycache__' not in path.parts:
                relative = path.relative_to(repo/'backend'); target = source/relative
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(path.read_bytes())
                files[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = dict(schema=VERSION,mode='offline_only',source_sha256=digest(files),source_files=files,
        dataset_sha256=digest(cases),planned_profiles=[c['id'] for c in cases],
        packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        dependency_locks={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [repo/'backend/requirements.txt',repo/'backend/requirements.lock.txt',repo/'frontend/package-lock.json']},
        real_model_requests=0,judge_calls=0)
    (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    results = []
    for profile in cases:
        base, _, _, routes = load_case(profile['source_id']); inputs = profile_inputs(profile)
        model_path = profile['source_id'].startswith('R') or inputs['query']['priority'] in {'balanced','daytime'}
        header = {k:base.model_dump(mode='json')[k] for k in
                  ('case_id','case_version','input_sha256','clock','data_origin','execution_mode')}
        header.update(case_version='2.1-draft-'+profile['id'],input_sha256=digest(inputs),
                      execution_mode='live_model_with_replay' if model_path else 'no_model')
        work = directory/profile['id'];work.mkdir()
        job = dict(case=header,inputs=inputs,routes=routes,variant='current_replay',
                   slot_id=profile['id']+'-offline-v21',experiment_id=directory.name,repetition=1)
        (work/'job.json').write_text(json.dumps(job,ensure_ascii=False))
        env = {k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','TMPDIR','LANG'}}
        env.update(DATABASE_URL='sqlite+aiosqlite:///'+str(work/'case.sqlite'),PYTHONPATH=str(source),
                   PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
        observation = dict(execution_status='worker_error',provenance='replay_model',
                           input_sha256=header['input_sha256'],case_version=header['case_version'])
        try:
            with (work/'worker.log').open('w') as log:
                done = subprocess.run([sys.executable,'-m','evals.worker'],cwd=work,env=env,stdout=log,stderr=log,timeout=120)
            if done.returncode == 0:observation = read_json(work/'observation.json')
        except subprocess.TimeoutExpired:observation['execution_status'] = 'worker_timeout'
        try:
            result = score(profile,observation,diagnostic=True)
            from .conditional_live import extra_checks
            result['checks'] = [dict(c,layer='system') for c in result['checks']]
            engineering = read_json(work/'engineering.json')
            bundle = dict(inputs=inputs,prompt=engineering['captured_prompts'][0] if engineering['captured_prompts'] else [])
            result['checks'] += extra_checks(profile,observation,bundle,model_path,scorer=score)
            result.update(actual_model_substitute_calls=engineering['model_substitute_calls'],
                          actual_live_model_requests=engineering['actual_live_model_requests'])
        except (ValueError,KeyError,TypeError):
            result = dict(profile_id=profile['id'],schema=VERSION,checks=[dict(rule='execution_or_evidence',layer='engineering',status='ERROR')],
                          diagnostic_only=True,formal_quality_score=None)
        results.append(result)
        (directory/'partial-results.json').write_text(json.dumps(dict(planned=12,results=results),ensure_ascii=False,indent=2)+'\n')
    report = dict(schema=VERSION,planned=12,results=results,formal_quality_score=None,formal_quality_status='NOT_EVALUATED',
                  real_model_requests=0,judge_calls=0,provenance='isolated_offline_replay',
                  limitation='Pending references; neutral substitutes do not prove real model improvement.')
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['validate','replay']);parser.add_argument('--directory')
    args = parser.parse_args()
    if args.command == 'validate':print(dict(schema=VERSION,profiles=len(load_cases()),real_model_requests=0))
    else:
        if not args.directory:parser.error('--directory required')
        result = replay(args.directory);print(dict(planned=result['planned'],real_model_requests=0,formal_quality_score=None))


if __name__ == '__main__':main()
