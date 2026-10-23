"""Explicit local rest reservations; never inferred from unallocated gaps."""
from datetime import date
from pydantic import BaseModel, Field, model_validator

class RestPeriod(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    date: date
    start_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    label: str = Field(default="留给自己的休息时间", min_length=1, max_length=80)

    @model_validator(mode="after")
    def valid(self):
        if self.start_time >= self.end_time: raise ValueError("休息结束须晚于开始，跨日请分开填写")
        return self

def validate_rest_periods(periods, start, end):
    if len({r.id for r in periods}) != len(periods): raise ValueError("休息时段标识不能重复")
    ordered=sorted(periods,key=lambda r:(r.date,r.start_time))
    for r in ordered:
        if not start <= r.date <= end: raise ValueError("休息日期须位于所在城市停留期间")
    for a,b in zip(ordered,ordered[1:]):
        if a.date==b.date and a.end_time>b.start_time: raise ValueError("休息时段不能重叠")
