"""Version 2 conditional evaluations. Independent of production filters/schedulers.

The original dataset and rules-v1.1 remain readable and immutable. This module
never enables live models or judges; replay uses the existing guarded worker.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

from .contracts import digest

VERSION = 'conditional-v2.0'
DATA = Path(__file__).with_name('conditional_cases.json')


def load_cases():
    data = json.loads(DATA.read_text())
    if data['schema'] != VERSION or digest(data['cases']) != data['content_sha256']:
        raise ValueError('conditional dataset hash mismatch')
    ids = [c['id'] for c in data['cases']]
    if len(ids) != len(set(ids)) or len(ids) != 12:
        raise ValueError('12 unique scenario specifications required')
    for case in data['cases']:
        if case['source_id'] not in {f'T{i:02}' for i in range(1,19)} | {f'R{i:02}' for i in range(1,13)}:
            raise ValueError('unknown base fixture')
        source = Path(__file__).parent / 'datasets' / 'inputs' / (case['source_id'] + '.json')
        if digest(json.loads(source.read_text())) != case['source_input_sha256']:
            raise ValueError('base fixture changed; new review required')
        if digest(case['reference']) != case['reference_sha256']:
            raise ValueError('reference hash mismatch')
    return data['cases']


def profile_inputs(case):
    inputs = json.loads((Path(__file__).parent/'datasets/inputs'/f"{case['source_id']}.json").read_text())
    if 'query' in inputs:
        inputs['query'].update(copy.deepcopy(case['query_overrides']))
    return inputs


def score(case, observation, *, diagnostic=False):
    """References never reach the replay worker or model. Pending stays diagnostic."""
    if (observation.get('input_sha256') != digest(profile_inputs(case))
            or observation.get('case_version') != '2.0-draft-'+case['id']):
        raise ValueError('observation does not belong to this profile input/version; do not reuse old model outputs')
    reference = case['reference']
    if digest(reference) != case['reference_sha256']:
        raise ValueError('reference changed')
    checks = []
    def add(rule, status, actual=None, expected=None):
        checks.append(dict(rule=rule, status=status, actual=actual, expected=expected))
    result = observation.get('final_output')
    # A replay is never eligible for a formal quality score, even after future human review.
    pending = case['annotation']['status'] != 'confirmed'
    if pending and not diagnostic:
        add('reference', 'NOT_EVALUATED')
    elif not result or observation.get('execution_status') != 'success':
        add('execution', 'ERROR', observation.get('execution_status'), 'success')
    elif case['source_id'].startswith('R'):
        from .dataset import load_case
        from .contracts import Observation
        from .scorers import day_constraints
        _, inputs, original_ref, routes = load_case(case['source_id'])
        try:
            ok, expected, actual, _ = day_constraints('R-ROUTE', 'system', inputs, original_ref,
                                                    Observation.model_validate(observation), routes)
            add('route_goal', 'PASS' if ok else 'FAIL', actual, expected)
        except (KeyError, ValueError, TypeError):
            add('route_goal', 'ERROR')
    else:
        recs = result['recommendations']
        ids = [r['candidate']['id'] for r in recs]
        actual_set = set(ids)
        # Preference filters and the full schedule-assessment set have separate scopes.
        allowed = set(reference['eligible_ids'])
        add('eligible_recommendations', 'PASS' if len(ids) == len(actual_set) and actual_set <= allowed else 'FAIL', ids, sorted(allowed))
        first = reference['acceptable_first']
        if first is None:
            add('conditional_rank', 'NOT_EVALUATED', ids, 'no explicit ranking intent')
        else:
            ok = (not ids and not first) or (bool(ids) and ids[0] in first)
            for a, b in reference.get('preferred_pairs', []):
                if a in ids and b in ids and ids.index(a) > ids.index(b):
                    ok = False
            add('conditional_rank', 'PASS' if ok else 'FAIL', ids, first)
        if reference.get('rank_key') and ids:
            from datetime import datetime
            source = json.loads((Path(__file__).parent/'datasets/inputs'/f"{case['source_id']}.json").read_text())
            candidates = {c['id']:c for c in source['candidates']}
            key = reference['rank_key']
            values = [(candidates[i]['fare_per_person'] if candidates[i]['fare_per_person'] is not None else float('inf'))
                      if key == 'price' else (datetime.fromisoformat(candidates[i]['arrival'])-datetime.fromisoformat(candidates[i]['departure'])).total_seconds()
                      for i in ids if i in candidates]
            add('declared_order', 'PASS' if values == sorted(values) else 'FAIL')
        assessments = result.get('assessments', {})
        for candidate_id, expected in reference.get('stages', {}).items():
            actual = assessments.get(candidate_id)
            if actual is None:
                add('stage:'+candidate_id, 'ERROR')
            elif actual.get('stage') != expected['stage']:
                add('stage:'+candidate_id, 'FAIL', actual, expected)
            elif expected['stage'] == 'date':
                add('stage:'+candidate_id, 'PASS' if actual.get('margins') is None else 'FAIL', actual, expected)
            elif actual.get('margins') is None:
                add('stage:'+candidate_id, 'ERROR')
            else:
                add('stage:'+candidate_id, 'PASS' if actual['margins'] == expected['margins'] else 'FAIL', actual, expected)
        if allowed and case['query_overrides'].get('priority') == 'unspecified':
            add('no_implicit_winner', 'PASS' if result.get('preference_status') == 'unspecified' and result.get('ranked_by') == 'options' else 'FAIL')
        if not allowed:
            add('empty_constraints', 'PASS' if not ids and result.get('preference_excluded') else 'FAIL')
    return dict(schema=VERSION, profile_id=case['id'], source_id=case['source_id'],
                reference_status=case['annotation']['status'], diagnostic_only=True,
                formal_quality_score=None, provenance=observation.get('provenance'), checks=checks)


def replay(directory):
    """New offline observations, not reinterpreted old model outputs."""
    directory = Path(directory).resolve()
    repo = Path(__file__).resolve().parents[2]
    if directory.is_relative_to(repo) or directory.exists():
        raise ValueError('use a fresh directory outside the repository')
    directory.mkdir(parents=True)
    from .dataset import load_case
    source = directory/'source'; source.mkdir()
    files = {}
    for folder in ['app','evals']:
        for path in sorted((repo/'backend'/folder).rglob('*')):
            if path.is_file() and path.suffix in {'.py','.json'} and '__pycache__' not in path.parts:
                relative = path.relative_to(repo/'backend'); target = source/relative
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(path.read_bytes())
                files[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    locks = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'backend').glob('requirements*.txt')}
    manifest = dict(schema=VERSION, source_sha256=digest(files), source_files=files,
        dependency_locks=locks, packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        dataset_sha256=digest(load_cases()), planned_profiles=[c['id'] for c in load_cases()],
        mode='offline_only', real_model_requests=0, judge_calls=0)
    (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    results = []
    for profile in load_cases():
        case, inputs, _, routes = load_case(profile['source_id'])
        inputs = copy.deepcopy(inputs)
        if 'query' in inputs:
            inputs['query'].update(profile['query_overrides'])
        # Keep every base fixture intact; a future movable-time variant needs its own case version.
        header = case.model_dump(mode='json')
        header.update(case_version='2.0-draft-'+profile['id'], input_sha256=digest(inputs))
        job = dict(case=header, inputs=inputs, routes=routes, variant='current_replay',
                   slot_id=profile['id']+'-offline', experiment_id=directory.name, repetition=1)
        slot = directory/profile['id'];slot.mkdir()
        (slot/'job.json').write_text(json.dumps(job, ensure_ascii=False))
        # Never inherit credentials or service-enabling flags.
        env = {k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','TMPDIR','LANG'}}
        env.update(DATABASE_URL='sqlite+aiosqlite:///'+str(slot/'case.sqlite'),
                   PYTHONPATH=str(source), PYTHONIOENCODING='utf-8')
        observation = {'execution_status':'worker_error','provenance':'replay_model',
                       'input_sha256':header['input_sha256'],'case_version':header['case_version']}
        try:
            with (slot/'worker.log').open('w') as log:
                done = subprocess.run([sys.executable, '-m', 'evals.worker'], cwd=slot, env=env,
                                      stdout=log, stderr=log, timeout=120)
            if done.returncode == 0:
                observation = json.loads((slot/'observation.json').read_text())
        except subprocess.TimeoutExpired:
            observation['execution_status'] = 'worker_timeout'
        try:
            result = score(profile, observation, diagnostic=True)
        except (ValueError, KeyError, TypeError):
            result = dict(schema=VERSION,profile_id=profile['id'],source_id=profile['source_id'],
                reference_status=profile['annotation']['status'],diagnostic_only=True,formal_quality_score=None,
                provenance='replay_model',checks=[dict(rule='evidence_binding',status='ERROR')])
        results.append(result)
        (directory/'partial-results.json').write_text(json.dumps(dict(planned=12,completed=len(results),results=results),ensure_ascii=False,indent=2)+'\n')
    report = dict(schema=VERSION, planned=12, results=results, formal_quality_score=None,
                  real_model_requests=0, judge_calls=0, provenance='isolated_offline_replay',
                  limitation='All references pending human; source families already seen; not a quality or usability acceptance.')
    (directory/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'replay'])
    parser.add_argument('--directory')
    args = parser.parse_args()
    if args.command == 'validate':
        print(json.dumps(dict(schema=VERSION, cases=len(load_cases()), formal_quality_score=None)))
    else:
        if not args.directory:
            parser.error('--directory is required')
        report = replay(args.directory)
        print(json.dumps(dict(planned=report['planned'], formal_quality_score=None, real_model_requests=0)))


if __name__ == '__main__':
    main()
