"""User supplied intercity legs; no inferred live fares or bookings."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import BaseModel, Field, model_validator


def local_instant(value: str, zone: str) -> datetime:
    try:
        naive = datetime.fromisoformat(value)
        tz = ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError('请使用有效当地日期时间和IANA时区，例如Asia/Shanghai') from error
    if naive.tzinfo is not None:
        raise ValueError('日期时间不带偏移，时区请单独填写')
    if naive.second or naive.microsecond:
        raise ValueError('时间精确到分钟即可')
    value = naive.replace(tzinfo=tz)
    if value.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive:
        raise ValueError('该当地时间处于夏令时跳变空档')
    if value.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
        raise ValueError('该当地时间因夏令时重复，请使用不歧义的时间')
    return value


class JourneyExtras(BaseModel):
    # Whole-party additional costs, not already included in ticket_total.
    taxes: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    baggage: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    transfers: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    overnight: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)


class JourneyLeg(BaseModel):
    mode: Literal['train', 'flight', 'bus', 'driving', 'other'] = 'train'
    service_number: str = Field(default='', max_length=60)
    departure_station: str = Field(min_length=1, max_length=120)
    arrival_station: str = Field(min_length=1, max_length=120)
    departure_time: str
    arrival_time: str
    departure_timezone: str = 'Asia/Shanghai'
    arrival_timezone: str = 'Asia/Shanghai'
    passengers: int = Field(default=1, ge=1, le=20)
    booking_status: Literal['planned', 'booked'] = 'planned'
    price_source: Literal['unknown', 'user_estimate', 'user_quote', 'paid'] = 'unknown'
    price_note: str = Field(default='', max_length=300)
    quoted_at: str | None = None
    ticket_total: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    currency: str = Field(default='CNY', pattern=r'^[A-Z]{3}$')
    extras_total: float | None = Field(default=None, ge=0, le=10000000, allow_inf_nan=False)
    extra_costs: JourneyExtras | None = None
    connections: int | None = Field(default=None, ge=0, le=10)
    seat_class: str = Field(default='', max_length=80)
    baggage_policy: str = Field(default='', max_length=300)
    refund_policy: str = Field(default='', max_length=300)
    quote_expires_at: str | None = None
    # All prices cover the entire party; never multiply by passenger count again.
    transfer_before_minutes: int = Field(default=60, ge=0, le=720)
    station_buffer_minutes: int = Field(default=60, ge=0, le=720)
    baggage_minutes: int = Field(default=30, ge=0, le=720)
    transfer_after_minutes: int = Field(default=60, ge=0, le=720)
    lodging_buffer_minutes: int = Field(default=30, ge=0, le=240)

    @model_validator(mode='after')
    def valid_leg(self):
        start = local_instant(self.departure_time, self.departure_timezone)
        end = local_instant(self.arrival_time, self.arrival_timezone)
        if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
            raise ValueError('到达必须晚于出发，请核对跨日日期和时区')
        if (end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds() > 7*86400:
            raise ValueError('单段交通不能超过7天')
        if self.ticket_total is not None and self.price_source == 'unknown':
            raise ValueError('填写票价时请同时标明价格来源')
        if self.price_source in {'user_quote','paid'} and (not self.price_note.strip() or not self.quoted_at):
            raise ValueError('报价或已付金额需填写来源说明与记录时间')
        if self.extra_costs is not None:
            self.extras_total = round(sum(v for v in self.extra_costs.model_dump().values() if v is not None), 2)
        if self.quote_expires_at:
            expiry = local_instant(self.quote_expires_at, self.departure_timezone)
            if not self.quoted_at or expiry <= local_instant(self.quoted_at, self.departure_timezone):
                raise ValueError('报价失效时间必须晚于记录时间')
        if self.quoted_at:
            local_instant(self.quoted_at, self.departure_timezone)
        return self


class Journey(BaseModel):
    origin_city: str = Field(min_length=1, max_length=80)
    return_city: str = Field(min_length=1, max_length=80)
    destination_timezone: str = 'Asia/Shanghai'
    outbound: JourneyLeg | None = None
    inbound: JourneyLeg | None = None

    @model_validator(mode='after')
    def valid_journey(self):
        try: ZoneInfo(self.destination_timezone)
        except ZoneInfoNotFoundError as error: raise ValueError('目的地时区无效') from error
        if self.outbound and self.inbound:
            arrival = local_instant(self.outbound.arrival_time,self.outbound.arrival_timezone)
            departure = local_instant(self.inbound.departure_time,self.inbound.departure_timezone)
            if departure <= arrival: raise ValueError('返程出发必须晚于去程到达')
        return self
