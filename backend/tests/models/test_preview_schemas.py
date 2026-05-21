import pytest
from pydantic import ValidationError

from app.models.schemas import (
    DiscoveredAttraction,
    DayDurationInfo,
    PreviewDayAssignmentRequest,
    PreviewDayAssignmentResponse,
)


def test_discovered_attraction_accepts_visit_minutes():
    attr = DiscoveredAttraction(name="故宫", visit_minutes=120)
    assert attr.visit_minutes == 120


def test_discovered_attraction_visit_minutes_optional():
    attr = DiscoveredAttraction(name="故宫")
    assert attr.visit_minutes is None


def test_day_duration_info_basic():
    d = DayDurationInfo(day_index=0, total_minutes=300)
    assert d.day_index == 0
    assert d.total_minutes == 300
    assert d.warning is None


def test_day_duration_info_with_warning():
    d = DayDurationInfo(day_index=1, total_minutes=540, warning="当天偏紧")
    assert d.warning == "当天偏紧"


def test_preview_request_requires_attractions_and_days():
    req = PreviewDayAssignmentRequest(
        selected_attractions=[DiscoveredAttraction(name="A")],
        travel_days=2,
    )
    assert len(req.selected_attractions) == 1
    assert req.travel_days == 2


def test_preview_response_shape():
    resp = PreviewDayAssignmentResponse(
        day_assignments=[
            [DiscoveredAttraction(name="A", visit_minutes=60)],
            [DiscoveredAttraction(name="B", visit_minutes=90)],
        ],
        day_durations=[
            DayDurationInfo(day_index=0, total_minutes=60),
            DayDurationInfo(day_index=1, total_minutes=90),
        ],
    )
    assert len(resp.day_assignments) == 2
    assert resp.day_assignments[0][0].visit_minutes == 60
    assert resp.day_durations[1].total_minutes == 90
