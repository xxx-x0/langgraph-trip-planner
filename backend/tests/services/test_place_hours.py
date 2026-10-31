import copy
import json
from pathlib import Path

import pytest

from app.models.schemas import DayDetail
from app.services.place_hours import resolve_hours,place_hours_report


@pytest.mark.parametrize('text,date,windows,entry',[
    ('08:00-21:00','2026-10-15',[(480,1260)],None),
    ('09:00–17:00 最晚入园16:00','2026-10-15',[(540,1020)],960),
    ('3–10月7:30–17:30(17:00 止入),11–2月7:30–17:00(16:30 止入)','2026-10-15',[(450,1050)],1020),
    ('3–10月7:30–17:30(17:00 止入),11–2月7:30–17:00(16:30 止入)','2026-01-15',[(450,1020)],990),
    ('1月至4月,11月至12月 周一至周日 07:30-17:30 最晚进入17:00；5月至10月 周一至周日 07:30-18:00 最晚进入17:30','2026-10-15',[(450,1080)],1050),
    ('1月至4月,11月至12月 周一至周日 07:30-17:30 最晚进入17:00；5月至10月 周一至周日 07:30-18:00 最晚进入17:30','2026-12-15',[(450,1050)],1020),
])
def test_explicit_rules_select_date_without_unioning_seasons(text,date,windows,entry):
    assert resolve_hours(text,date)==dict(status='known',windows=windows,last_entry=entry)


@pytest.mark.parametrize('text',['周一闭馆，09:00-17:00','节假日09:00-22:00','5月1日09:00-17:00',
    '夏令09:00-17:00 冬令10:00-16:00','11月09:00-17:00',None,'需预约',
    '1–12月09:00-17:00；5–10月10:00-18:00'])
def test_ambiguous_hours_are_unknown(text):
    assert resolve_hours(text,'2026-10-15')['status']=='unknown'


def test_last_entry_and_closing_are_separate_and_unknown_is_not_pass():
    fixture=Path(__file__).parents[2]/'evals/datasets/inputs/R10.json'
    day=DayDetail.model_validate(json.loads(fixture.read_text())['day_detail'])
    before=copy.deepcopy(day.model_dump(mode='json'))
    row=next(r for r in day.timeline_schedule if r['ref_name']=='虎丘山风景区' and r['kind']=='attraction')
    row.update(start_minutes=1051,end_minutes=1070)
    result=place_hours_report(day)
    assert '虎丘山风景区超过已知最晚入场时间' in result['violations']
    assert '虎丘山风景区不在已知开放时间内' not in result['violations']
    row.update(start_minutes=1144,end_minutes=1294)
    assert '虎丘山风景区不在已知开放时间内' in place_hours_report(day)['violations']
    day.attractions[0].open_hours='节假日另行通知'
    assert any('虎丘' in x for x in place_hours_report(day)['unknown'])
    assert before['attractions'][0]['open_hours']!=day.attractions[0].open_hours


def test_daily_overnight_hours_cover_both_sides_of_midnight_and_dates_abstain():
    assert resolve_hours('22:00-02:00','2026-10-15')['windows']==[(0,120),(1320,1560)]
    assert resolve_hours('2026-12-01 08:00-17:00','2026-10-15')['status']=='unknown'
    assert resolve_hours('5–10月22:00-02:00','2026-10-15')['status']=='unknown'
