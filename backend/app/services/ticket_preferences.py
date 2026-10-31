"""Preferences from this request only; facts and hard filters never come from an LLM."""
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class TicketPreferences(BaseModel):
    accepted_seats: list[str] = Field(default_factory=list, max_length=12)
    max_reference_fare_per_person: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    departure_after: str = Field(default='07:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    arrival_before: str = Field(default='22:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    daytime_hard: bool = False

    @field_validator('accepted_seats')
    @classmethod
    def seats(cls, value):
        if any(not x.strip() or len(x) > 80 for x in value) or len(value) != len(set(value)):
            raise ValueError('席别条件为空、过长或重复')
        return value


def duration(candidate):
    return round((datetime.fromisoformat(candidate.arrival) - datetime.fromisoformat(candidate.departure)).total_seconds() / 60)


def metric_order(candidates, priority):
    """One explicitly chosen metric; stable ties carry no hidden preference."""
    if priority == 'time':
        return sorted(candidates,key=duration)
    if priority != 'price':
        raise ValueError('explicit price or time required')
    known = [c for c in candidates if c.fare_per_person is not None]
    unknown = [c for c in candidates if c.fare_per_person is None]
    return sorted(known,key=lambda c:c.fare_per_person) + unknown


def in_daytime(candidate, preferences):
    return (candidate.departure[:10] == candidate.arrival[:10]
            and candidate.departure[11:16] >= preferences.departure_after
            and candidate.arrival[11:16] <= preferences.arrival_before)


def preference_conflicts(candidate, preferences):
    reasons = []
    if preferences.accepted_seats and candidate.seat not in preferences.accepted_seats:
        reasons.append('不符合本次指定席别；未自动降级')
    limit = preferences.max_reference_fare_per_person
    if limit is not None:
        if candidate.fare_per_person is None:
            reasons.append('列表参考价未知，无法确认符合每人参考价上限')
        elif candidate.fare_per_person > limit:
            reasons.append('超出本次每人列表参考价上限')
    if preferences.daytime_hard and not in_daytime(candidate, preferences):
        reasons.append('不符合本次必须满足的出发/到达时段')
    return reasons


def alternatives(candidates, assessments=None):
    """Offer actual price/time/arrival differences, without an implicit winner."""
    keys = [lambda c: c.fare_per_person if c.fare_per_person is not None else float('inf'),
            duration, lambda c: c.arrival]
    if assessments and any(v.get('margins') for v in assessments.values()):
        keys.append(lambda c: -min((assessments.get(c.id, {}).get('margins') or [float('-inf')])))
    chosen = []
    for key in keys:
        first = min(candidates, key=key)
        if first.id not in {c.id for c in chosen}:
            chosen.append(first)
    return chosen[:3]


def badges(candidate, candidates):
    result = []
    known = [c.fare_per_person for c in candidates if c.fare_per_person is not None]
    if known and len(set(known)) > 1 and candidate.fare_per_person == min(known):
        result.append('已知列表参考价较低')
    times = [duration(c) for c in candidates]
    if len(set(times)) > 1 and duration(candidate) == min(times):
        result.append('车程较短')
    arrivals = [c.arrival for c in candidates]
    if len(set(arrivals)) > 1 and candidate.arrival == min(arrivals):
        result.append('较早到达')
    return result
