import copy
import json
from pathlib import Path

import pytest

from evals.conditional_v22 import load_cases,profile_inputs,score,route_reference
from evals.contracts import digest
from evals.dataset import load_case
from evals.scorers import window_violations
from evals.worker import trace_origin


def test_old_versions_cannot_be_relabelled_as_new_evidence():
    c=next(c for c in load_cases() if c['id']=='PS12')
    with pytest.raises(ValueError,match='old paid outputs'):
        score(c,dict(case_version='2.1-draft-PS12',input_sha256=digest(profile_inputs(c))),diagnostic=True)
    assert all(c['annotation']['status']=='pending_human' for c in load_cases())
    assert route_reference(c)['hard_constraints']['end_latest']==1440
    assert route_reference(c)['hard_constraints']['dinner_start_range']==[1050,1380]
    assert load_case('R10')[2]['hard_constraints']['end_latest']==1320


def test_unprovided_22_limit_is_absent_from_new_independent_window_check():
    c=next(c for c in load_cases() if c['id']=='PS12');_,inputs,old,routes=load_case('R10')
    day=copy.deepcopy(inputs['day_detail']);row=day['timeline_schedule'][-1]
    assert row['kind']=='hotel'
    start=row['start_minutes'];row.update(start_minutes=1380,end_minutes=1410,start_time='23:00',end_time='23:30')
    day['timeline_schedule'].insert(-1,dict(kind='wait',ref_name='自由等待',start_minutes=start,end_minutes=1380,duration=1380-start))
    assert 'outside_day_window' in window_violations(day,old['hard_constraints'],routes)
    assert not window_violations(day,route_reference(c)['hard_constraints'],routes)


@pytest.mark.parametrize('origin,expected',[
    ('mixed_historical_day_and_new_route_capture','mixed'),('mixed_historical_itinerary_and_new_capture','mixed'),
    ('synthetic','synthetic'),('arbitrary private text','unclassified')])
def test_trace_origin_is_normalized_without_accepting_arbitrary_text(origin,expected):
    assert trace_origin(origin)==expected
