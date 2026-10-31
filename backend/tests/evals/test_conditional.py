"""Independent expected sets/partial orders and stage semantics, no app helpers."""
import copy
import pytest
from evals.conditional import load_cases, score, profile_inputs
from evals.contracts import digest


def observation(ids, *, stage=None, profile="PS01"):
    return dict(execution_status='success',provenance='replay_model',input_sha256=digest(profile_inputs(case(profile))),case_version='2.0-draft-'+profile,final_output=dict(
        recommendations=[dict(candidate=dict(id=i)) for i in ids],
        ranked_by='options',preference_status='unspecified',assessments=stage or {}))


def case(id): return next(c for c in load_cases() if c['id']==id)


@pytest.mark.parametrize('answer', ['SYN_T04_A','SYN_T04_C'])
def test_two_equal_duration_answers_are_both_accepted_under_explicit_time_goal(answer):
    result=score(case('PS02'),observation([answer],profile="PS02"),diagnostic=True)
    assert all(c['status']=='PASS' for c in result['checks'])
    assert result['formal_quality_score'] is None


def test_pending_reference_and_unspecified_preference_never_create_formal_rank():
    assert score(case('PS01'),observation(['SYN_T04_B']))['checks'][0]['status']=='NOT_EVALUATED'
    result=score(case('PS04'),observation(['SYN_T04_A'],profile='PS04'),diagnostic=True)
    assert next(c for c in result['checks'] if c['rule']=='conditional_rank')['status']=='NOT_EVALUATED'


@pytest.mark.parametrize('stages,expected', [({},'ERROR'),
    ({'rail_109_K5834':{'stage':'date','margins':None},'rail_118_K552':{'stage':'date','margins':None}},'PASS'),
    ({'rail_109_K5834':{'stage':'date','margins':[0]},'rail_118_K552':{'stage':'date','margins':None}},'FAIL')])
def test_date_rejection_null_is_distinct_from_zero_and_missing_evidence(stages,expected):
    checks=score(case('PS07'),observation(['rail_127_G236'],stage=stages,profile='PS07'),diagnostic=True)['checks']
    assert next(c for c in checks if c['rule']=='stage:rail_109_K5834')['status']==expected


def test_invalid_fact_candidate_and_reference_tampering_are_not_hidden_by_multiple_answers():
    result=score(case('PS02'),observation(['invented'],profile='PS02'),diagnostic=True)
    assert result['checks'][0]['status']=='FAIL'
    damaged=copy.deepcopy(case('PS02'));damaged['reference']['acceptable_first'].append('invented')
    with pytest.raises(ValueError):score(damaged,observation(['invented'],profile='PS02'),diagnostic=True)


def test_old_real_output_cannot_be_reinterpreted_under_a_new_profile():
    old=observation(['SYN_T04_A'],profile='PS02');old['case_version']='1.0.1-draft'
    with pytest.raises(ValueError,match='do not reuse old'):score(case('PS02'),old,diagnostic=True)
