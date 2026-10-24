"""Whole-trip structure. Stable stop IDs identify visits, not city-name strings."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict
from .journey import JourneyLeg, local_instant
from .rest import RestPeriod, validate_rest_periods
from .schemas import Location, HotelOccupancy, CompanionInfo


class CityRef(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=60, pattern=r'^[\w-]+$')
    name: str = Field(min_length=1, max_length=80)
    adcode: str | None = None
    location: Location | None = None
    timezone: Literal['Asia/Shanghai'] = 'Asia/Shanghai'


class Lodging(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    check_in: date
    check_out: date
    rooms: int = Field(default=1, ge=1, le=20)
    amount: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    basis: Literal['stay_total', 'room_night'] = 'stay_total'
    currency: str = Field(default='CNY', pattern=r'^[A-Z]{3}$')
    source: Literal['unknown', 'user_estimate', 'user_quote', 'paid'] = 'unknown'
    source_note: str = Field(default='', max_length=300)
    recorded_at: str | None = None
    taxes_included: bool | None = None
    booked: bool = False

    @model_validator(mode='after')
    def valid(self):
        if self.check_out <= self.check_in: raise ValueError('退房须晚于入住；当日不住宿请移除住宿区间')
        if self.amount is not None and (self.source == 'unknown' or not self.source_note.strip()):
            raise ValueError('填写住宿金额时请填写价格来源和说明')
        if self.source in {'user_quote','paid'} and not self.recorded_at: raise ValueError('报价或已付住宿请填写记录时间')
        if self.recorded_at: local_instant(self.recorded_at, 'Asia/Shanghai')
        return self


class CityStay(BaseModel):
    id: str = Field(min_length=1, max_length=60, pattern=r'^[\w-]+$')
    city: CityRef
    start_date: date
    end_date: date
    must_visit: bool = True
    lodgings: list[Lodging] = Field(default_factory=list, max_length=10)
    rest_periods: list[RestPeriod] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def valid(self):
        if self.start_date > self.end_date: raise ValueError('城市离开日期不能早于抵达日期')
        validate_rest_periods(self.rest_periods, self.start_date, self.end_date)
        nights=set()
        for h in self.lodgings:
            if not self.start_date <= h.check_in < h.check_out <= self.end_date: raise ValueError('住宿日期须位于所在城市停留期间')
            for n in range(h.check_in.toordinal(),h.check_out.toordinal()):
                if n in nights: raise ValueError('同一城市的住宿区间不能重复覆盖一晚')
                nights.add(n)
        if len({h.id for h in self.lodgings}) != len(self.lodgings): raise ValueError('住宿标识不能重复')
        return self


class CityTransfer(BaseModel):
    from_stop: str
    to_stop: str
    leg: JourneyLeg | None = None


class MultiTrip(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='我的多城市旅行', min_length=1, max_length=120)
    start_date: date
    end_date: date
    origin: CityRef
    destination: CityRef
    companions: CompanionInfo
    hotel_occupancy: HotelOccupancy | None = None
    budget: int | None = Field(default=None, ge=1, le=10000000)
    pace: Literal['slow','balanced','active'] = 'balanced'
    preferences: list[str] = Field(default_factory=list, max_length=20)
    transportation: str = '公共交通'
    accommodation: str = '经济型酒店'
    meal_budget_per_person: int | None = Field(default=None, ge=1, le=10000)
    dietary_requirements: str = Field(default='', max_length=300)
    stops: list[CityStay] = Field(min_length=2, max_length=3)
    transfers: list[CityTransfer] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def valid(self):
        if not 5 <= (self.end_date-self.start_date).days+1 <= 10: raise ValueError('本阶段支持5至10天、2至3座城市')
        ids=[s.id for s in self.stops]
        if len(set(ids))!=len(ids) or any(i in {'origin','destination'} for i in ids): raise ValueError('城市停留标识须唯一且不能使用保留名称')
        previous=None
        for s in self.stops:
            if not self.start_date<=s.start_date<=s.end_date<=self.end_date: raise ValueError('城市停留须在整趟日期内')
            if previous and previous.end_date>s.start_date: raise ValueError('城市停留时间重叠；同日换城可使用相同日期')
            previous=s
        validate_rest_periods([r for s in self.stops for r in s.rest_periods], self.start_date, self.end_date)
        edges=list(zip(['origin']+ids,ids+['destination']))
        seen=set()
        for t in self.transfers:
            edge=(t.from_stop,t.to_stop)
            if edge not in edges or edge in seen: raise ValueError('交通须连接相邻停留，且每段只能有一个所选班次')
            seen.add(edge)
            if t.leg:
                l=t.leg
                if l.passengers!=self.companions.count: raise ValueError('交通人数须与整趟同行人数一致')
                if l.departure_timezone!='Asia/Shanghai' or l.arrival_timezone!='Asia/Shanghai': raise ValueError('本阶段多城市仅支持中国标准时间')
                if not self.start_date<=date.fromisoformat(l.departure_time[:10])<=date.fromisoformat(l.arrival_time[:10])<=self.end_date: raise ValueError('交通日期须在整趟日期范围内')
        known=[next((t.leg for t in self.transfers if (t.from_stop,t.to_stop)==edge),None) for edge in edges]
        known=[leg for leg in known if leg]
        for a,b in zip(known,known[1:]):
            if local_instant(a.arrival_time,a.arrival_timezone)>=local_instant(b.departure_time,b.departure_timezone): raise ValueError('前段到达不能晚于或等于后段出发，请核对交通顺序')
        if self.hotel_occupancy:
            o=self.hotel_occupancy
            if o.room_count*(o.adults_per_room+len(o.children_ages))!=self.companions.count: raise ValueError('房间配置须与同行人数一致')
        return self
