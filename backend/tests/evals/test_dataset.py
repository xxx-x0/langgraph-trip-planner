"""P2 asset checks, no application execution, network, business DB or live model."""
import copy
import hashlib
import json
import shutil
import socket
import subprocess
import sys

import pytest

from evals.contracts import Case, digest
from evals.dataset import DATA, load_all, load_case, model_inputs, read_json
from evals.validation import validate, review_queue


def test_manifest_counts_sources_and_human_annotations():
    result=validate()
    assert result['cases']==30 and result['rules']==22
    assert result['pending_human']==30 and result['formal_ready'] is False
    assert result['origins']=={'synthetic':28,'mixed_historical_itinerary_and_new_capture':1,'mixed_historical_day_and_new_route_capture':1}
    assert len(review_queue())==30
    for c,*_ in load_all():
        assert c.annotation.reviewer is None and c.annotation.reviewed_at is None
        assert c.annotation.author_kind=='agent_draft'


@pytest.mark.parametrize('cid',[f'T{i:02d}' for i in range(1,19)]+[f'R{i:02d}' for i in range(1,13)])
def test_native_payload_schema_compatibility(cid):
    # Model-only validation. Never call ScheduleCheck, projection, scheduler, model or DB.
    from app.services.ticket_assistant import TicketRankingRequest
    from app.models.schemas import TripRequest,DayDetail,DiningCandidate
    from app.models.multicity import MultiTrip
    c,i,_,_=load_case(cid)
    if c.target=='ticket_recommendation':
        TicketRankingRequest.model_validate({k:i[k] for k in ['query','candidates','context']})
        if i['context'] and i['context']['kind']=='multi':
            MultiTrip.model_validate(i['saved_state']['plan'])
            for s in i['saved_state']['snapshots'].values():
                TripRequest.model_validate(s['request'])
                for day in s['days_detail']:
                    if day:DayDetail.model_validate(day)
    else:
        TripRequest.model_validate(i['request']);DayDetail.model_validate(i['day_detail'])
        for candidate in i['dining_candidates']:DiningCandidate.model_validate(candidate)


def test_mixed_sources_are_not_silently_moved_or_relabelled():
    c,i,r,_=load_case('T18')
    assert i['query']['date']=='2026-11-01' and len(i['candidates'])==80
    assert len(r['eligible_ids'])==35 and r['acceptable_first'] is None
    assert len([x for x in r['candidate_checks'] if not x['eligible']])==45
    assert next(x for x in r['candidate_checks'] if x['candidate_id'].endswith('G3106'))['margins']==[3]
    assert {s['origin'] for s in c.sources}>={'historical_capture','new_capture'}
    c,i,r,routes=load_case('R10')
    assert i['day_detail']['date']=='2026-10-15'
    assert len(routes['edges'])==23 and len(r['permutations'])==20
    assert r['historical_baseline_minutes_archive_only']==168
    assert r['baseline_traffic_minutes']==180
    assert sorted(p['traffic_minutes'] for p in r['permutations'] if p['feasible'])==[138,162,180]
    assert all(e['source']=='amap_mcp_live_20261024' and e['collected_at'].startswith('2026-10-24') for e in routes['edges'])
    supplement=next(s for s in c.sources if s['origin']=='new_capture')
    assert supplement['new_missing_edges']==15 and supplement['refreshed_control_edges']==8
    assert len(supplement['raw_files'])==24  # Includes the preserved failed QPS response.


def test_reference_margin_arithmetic_and_saved_buffers_are_independently_consistent():
    from datetime import datetime
    for c,inp,ref,_ in load_all():
        if c.target!='ticket_recommendation':continue
        if inp['context']:
            if inp['context']['kind']=='draft':leg=inp['saved_state']['request']['journey'][inp['query']['direction']]
            else:leg=next(t['leg'] for t in inp['saved_state']['plan']['transfers'] if t['from_stop']==inp['context']['from_stop'] and t['to_stop']==inp['context']['to_stop'])
            assert all(leg[k]==v for k,v in ref['buffer_fields'].items())
        candidates={x['id']:x for x in inp['candidates']}
        for row in ref['candidate_checks']:
            candidate=candidates[row['candidate_id']];margins=[]
            if 'departure_after' in ref['bounds']:margins.append((datetime.fromisoformat(candidate['departure'])-datetime.fromisoformat(ref['bounds']['departure_after'])).total_seconds()/60)
            if 'arrival_before' in ref['bounds']:margins.append((datetime.fromisoformat(ref['bounds']['arrival_before'])-datetime.fromisoformat(candidate['arrival'])).total_seconds()/60)
            assert margins==row['margins']
            assert row['tight']==(bool(margins) and 0<=min(margins)<=30)


def test_packaged_projection_contains_no_private_fields_urls_or_local_paths():
    import re
    forbidden={'user_id','api_key','authorization','cookie','tel','phone','email','free_text_input','dietary_requirements'}
    def inspect(v):
        if isinstance(v,dict):
            for k,item in v.items():
                assert k.lower() not in forbidden or item in [None,'',[],{}]
                inspect(item)
        elif isinstance(v,list):
            for item in v:inspect(item)
        elif isinstance(v,str):assert '/Users/' not in v and not re.search(r'https?://',v)
    for path in DATA.rglob('*.json'):inspect(read_json(path))


def test_model_inputs_never_include_gold_or_fault_injections():
    for c,i,r,_ in load_all():
        ids=[i['candidates'][0]['id']] if c.target=='ticket_recommendation' else None
        payload=model_inputs(c.case_id,eligible_ids=ids)
        assert not {'reference','annotation','expected_assertions','fault','eligible_ids','acceptable_first'}&payload.keys()
        if ids:assert [x['id'] for x in payload['candidates']]==ids
    with pytest.raises(ValueError):model_inputs('T01')
    with pytest.raises(ValueError):model_inputs('T01',eligible_ids=['not_from_observed_batch'])


def test_tampering_and_path_escape_require_new_version(tmp_path):
    copy_root=tmp_path/'dataset';shutil.copytree(DATA,copy_root)
    path=copy_root/'inputs/T01.json';value=read_json(path);value['candidates'][0]['fare_per_person']=0
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):load_case('T01',copy_root)
    with pytest.raises(ValueError):validate(copy_root)
    from evals.dataset import asset
    with pytest.raises(ValueError):asset('../../private.json',copy_root)


def test_cannot_confirm_an_unreviewed_or_changed_reference():
    raw=load_case('T18')[0].model_dump()
    raw['annotation']['status']='confirmed'
    with pytest.raises(ValueError):Case.model_validate(raw)
    raw['annotation'].update(reviewer='synthetic-test-reviewer',reviewed_at='2027-01-01',pending_items=[],confirmed_reference_sha256='wrong-hash')
    with pytest.raises(ValueError):Case.model_validate(raw)


def test_cli_offline_under_network_denial_and_hostile_sdk_flags(monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('LANGSMITH_API_KEY','synthetic-secret-should-not-be-used')
    script="""
import socket, sys
def deny(*args,**kwargs):raise AssertionError('network forbidden')
socket.socket.connect=deny
from evals.validation import validate
from evals.dataset import load_all
from evals.selftest import observation_vector
from evals.scorers import evaluate
assert validate()['cases']==30
for c,*_ in load_all():
    bundle,obs=observation_vector(c.case_id)
    evaluate(*bundle,obs)
assert 'app.database' not in sys.modules
assert 'langsmith' not in sys.modules
"""
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('text',['NaN','Infinity','1e999'])
def test_nonfinite_evidence_rejected(tmp_path,text):
    p=tmp_path/'bad.json';p.write_text('{"value":'+text+'}')
    with pytest.raises(ValueError):read_json(p)
