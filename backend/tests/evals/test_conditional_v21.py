"""v2.1 is a new diagnostic version, not a rewrite of old paid scores."""
import copy

import pytest

from evals.conditional import load_cases as old_cases, score as old_score
from evals.conditional_v21 import load_cases, profile_inputs, score
from evals.contracts import digest
from evals.outcomes import ticket_outcome


def case(id):return next(c for c in load_cases() if c['id']==id)


def observation(ids,profile='PS06'):
    c=case(profile)
    return dict(case_version='2.1-draft-'+profile,input_sha256=digest(profile_inputs(c)),
                execution_status='success',provenance='replay_model',
                final_output=dict(recommendations=[dict(candidate=dict(id=i)) for i in ids]))


@pytest.mark.parametrize('ids,status',[
    (['SYN_T05_A','SYN_T05_B','SYN_T05_C'],'PASS'),
    (['SYN_T05_A','SYN_T05_C','SYN_T05_B'],'PASS'),
    (['SYN_T05_C','SYN_T05_B','SYN_T05_A'],'FAIL'),
    (['SYN_T05_B'],'NOT_EVALUATED'),
])
def test_known_price_subsequence_does_not_rank_unknown_placement(ids,status):
    result=score(case('PS06'),observation(ids),diagnostic=True)
    assert next(c for c in result['checks'] if c['rule']=='declared_order')['status']==status
    assert result['formal_quality_score'] is None


def test_unknown_first_does_not_become_cheapest():
    result=score(case('PS06'),observation(['SYN_T05_B','SYN_T05_A','SYN_T05_C']),diagnostic=True)
    assert next(c for c in result['checks'] if c['rule']=='conditional_rank')['status']=='FAIL'


def test_v20_unchanged_and_old_paid_observations_rejected():
    c=next(c for c in old_cases() if c['id']=='PS06')
    old=observation(['SYN_T05_A','SYN_T05_B','SYN_T05_C']);old['case_version']='2.0-draft-PS06'
    assert next(c for c in old_score(c,old,diagnostic=True)['checks'] if c['rule']=='declared_order')['status']=='FAIL'
    with pytest.raises(ValueError,match='old paid outputs'):score(case('PS06'),old,diagnostic=True)
    assert score(case('PS06'),observation(['SYN_T05_A']))['checks'][0]['status']=='NOT_EVALUATED'


@pytest.mark.parametrize('reason,preferences,conflicts,expected',[
    ('preferences',True,False,'empty_preferences'),
    ('schedule',False,True,'empty_conflict'),
    ('mixed',True,True,'empty_mixed_constraints'),
    ('availability',False,False,'empty_unavailable'),
    (None,True,True,'empty_mixed_constraints'),
])
def test_empty_reason_is_not_inferred_from_no_tickets_wording(reason,preferences,conflicts,expected):
    result=dict(recommendations=[],preference_excluded=[{}] if preferences else [],excluded=[{}] if conflicts else [])
    if reason:result['empty_reason']=reason
    assert ticket_outcome(result)==expected


def test_empty_preference_reference_requires_actual_classification():
    obs=observation([],profile='PS10');obs['final_output']['preference_excluded']=[{}]
    obs['business_outcome']='empty_preferences'
    result=score(case('PS10'),obs,diagnostic=True)
    assert next(c for c in result['checks'] if c['rule']=='empty_outcome')['status']=='PASS'
    obs['business_outcome']='empty_unavailable'
    assert next(c for c in score(case('PS10'),obs,diagnostic=True)['checks'] if c['rule']=='empty_outcome')['status']=='FAIL'
