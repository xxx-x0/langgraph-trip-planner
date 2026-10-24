"""Read-only ticket feasibility against authoritative saved itinerary snapshots."""
import hashlib
from types import SimpleNamespace
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from ..models.schemas import TripRequest, DayDetail
from ..models.multicity import MultiTrip
from . import multicity, trip_draft_service
from .journey_comparison import synchronize_days


def draft_basis(record):
    return hashlib.sha256((record.request_json + record.days_detail_json + record.weather_info_json).encode()).hexdigest()


class TicketContext(BaseModel):
    kind: Literal['draft', 'multi']
    draft_id: str = Field(min_length=1, max_length=80)
    revision: int | None = Field(default=None, ge=1)
    from_stop: str | None = Field(default=None, max_length=80)
    to_stop: str | None = Field(default=None, max_length=80)
    request: TripRequest | None = None
    days_detail: list[DayDetail | None] | None = Field(default=None, max_length=30)

    @model_validator(mode='after')
    def complete_scope(self):
        if self.kind == 'multi' and (self.revision is None or not self.from_stop or not self.to_stop):
            raise ValueError('整趟查询须关联已保存版本和当前交通段')
        if self.kind == 'draft' and (self.request is None or self.days_detail is None):
            raise ValueError('查票须关联当前草稿安排快照')
        return self


def day_facts(day):
    if day is None:
        return None
    value = DayDetail.model_validate(day).model_dump(mode='json')
    return {k: value.get(k) for k in ('date', 'attractions', 'meals', 'hotel', 'route_segments',
        'timeline_schedule', 'timeline_order', 'day_start_time', 'rest_periods', 'locked_attraction_names', 'removed_attraction_names')}


def changed():
    return HTTPException(409, '安排已改变，请重新读取草稿后查票；本次结果未采用')


class ScheduleCheck:
    async def initialize(self, context, query):
        self.context, self.query = context, query
        if context.kind == 'multi':
            self.document = await multicity.load(context.draft_id)
            if self.document['status'] == 'saved' or self.document['revision'] != context.revision:
                raise changed()
            self.basis = multicity.token(self.document)
            self.plan = MultiTrip.model_validate(self.document['plan'])
            self.edge = next((e for e in multicity.edges(self.plan) if e[:2] == (context.from_stop, context.to_stop)), None)
            if self.edge is None:
                raise changed()
            a, b, frm, to, self.old_leg = self.edge
            expected_date = self.plan.start_date if a == 'origin' else next(s.end_date for s in self.plan.stops if s.id == a)
            party = self.plan.companions.count
            self.affected = {a, b} - {'origin', 'destination'}
        else:
            if context.draft_id.startswith('mc_'):
                raise changed()
            self.record = await trip_draft_service.get_draft(context.draft_id)
            if not self.record or self.record.status in {'finalized', 'expired'}:
                raise changed()
            # Import here: API payload projection is also used by the actual preview.
            from ..api.routes.trip_draft import _load_payload
            self.payload = _load_payload(self.record)
            if context.request is None or context.days_detail is None:
                raise changed()
            if (TripRequest.model_validate(context.request) != self.payload.request or
                [day_facts(d) for d in context.days_detail] != [day_facts(d) for d in self.payload.days_detail]):
                raise changed()
            self.basis = draft_basis(self.record)
            req = self.payload.request
            journey = req.journey
            self.old_leg = getattr(journey, query.direction, None) if journey else None
            expected_date = req.start_date if query.direction == 'outbound' else req.end_date
            frm = SimpleNamespace(name=(journey.origin_city if journey else query.from_place) if query.direction == 'outbound' else req.city)
            to = SimpleNamespace(name=req.city if query.direction == 'outbound' else (journey.return_city or journey.origin_city if journey else query.to_place))
            party = req.companions.count if req.companions else 1
        def same_city(place, city):
            return bool(city) and place.removesuffix('市').startswith(city.removesuffix('市'))
        if (str(expected_date) != str(query.date) or party != query.passengers or
            not same_city(query.from_place, frm.name) or not same_city(query.to_place, to.name)):
            raise HTTPException(422, '查询日期、城市或人数与当前交通段不一致，请先保存本次安排或核对查询条件')
        return self

    async def assert_current(self):
        if self.context.kind == 'multi':
            current = multicity.token(await multicity.load(self.context.draft_id))
        else:
            record = await trip_draft_service.get_draft(self.context.draft_id)
            if not record or record.status in {'finalized', 'expired'}:
                raise changed()
            current = draft_basis(record)
        if current != self.basis:
            raise changed()

    def evaluate(self, candidate):
        leg = candidate.leg(self.query.passengers)
        if self.old_leg:
            fields = ['transfer_before_minutes', 'transfer_after_minutes', 'lodging_buffer_minutes']
            if self.old_leg.mode == leg.mode:
                fields += ['station_buffer_minutes', 'baggage_minutes']
            leg = leg.model_copy(update={k: getattr(self.old_leg, k) for k in fields})
        try:
            if self.context.kind == 'multi':
                plan = self.plan.model_copy(deep=True)
                if leg.arrival_time[:10] > str(plan.end_date) or leg.departure_time[:10] < str(plan.start_date):
                    return leg, [], ['班次跨出本次旅行日期，请调整日期后重新规划']
                plan.transfers = [t for t in plan.transfers if (t.from_stop, t.to_stop) != self.edge[:2]]
                from ..models.multicity import CityTransfer
                plan.transfers.append(CityTransfer(from_stop=self.edge[0], to_stop=self.edge[1], leg=leg))
                summary = multicity.projection(plan, self.document['snapshots'])
                cities = [c for c in summary['cities'] if c['id'] in self.affected]
                problems = list(summary['conflicts'])
                if any(c['stale'] for c in cities):
                    problems.append('城市日期或人数变化，原每日安排不能直接沿用')
            else:
                req = self.payload.request.model_copy(deep=True)
                if leg.arrival_time[:10] > req.end_date or leg.departure_time[:10] < req.start_date:
                    return leg, [], ['班次跨出本次旅行日期，请调整日期后重新规划']
                if not req.journey:
                    from ..models.journey import Journey
                    origin = self.query.from_place if self.query.direction == 'outbound' else self.query.to_place
                    req.journey = Journey(origin_city=origin, return_city=origin)
                setattr(req.journey, self.query.direction, leg)
                req = TripRequest.model_validate(req.model_dump(mode='json'))
                details, impacts, _ = synchronize_days(self.payload, req)
                problems = [p for i in impacts for p in i['conflicts']]
                cities = [dict(city=req.city, days=[d.model_dump(mode='json') if d else None for d in details], windows=[dict(date=i['date'], **i['window']) for i in impacts])]
            reasons = []
            for city in cities:
                relevant = [d for d in city['days'] if d and d['date'] in {leg.departure_time[:10], leg.arrival_time[:10]}]
                for detail in relevant:
                    window = next(w for w in city['windows'] if w['date'] == detail['date'])
                    lo, hi = window['start_minutes'], window['end_minutes']
                    clock = lambda n: f'{n // 60:02d}:{n % 60:02d}'
                    places = [a['name'] for a in detail['attractions']] + [m['name'] for m in detail['meals']]
                    if detail.get('hotel'):
                        places.append(detail['hotel']['name'])
                    label = '、'.join(places) or '当前空白安排'
                    reasons.append(f"{detail['date']} {city['city']}：含接驳及办理缓冲后市内窗口 {clock(max(480,lo))}—{clock(min(1320,hi))}；保留{label}及原时长、餐次和休息")
                    scheduled = [i for i in detail.get('timeline_schedule', []) if i['kind'] != 'free_time']
                    if scheduled and not problems:
                        first, last = min(i['start_minutes'] for i in scheduled), max(i['end_minutes'] for i in scheduled)
                        departing = (self.context.kind == 'draft' and self.query.direction == 'inbound' or
                                     self.context.kind == 'multi' and city['id'] == self.edge[0])
                        arriving = (self.context.kind == 'draft' and self.query.direction == 'outbound' or
                                    self.context.kind == 'multi' and city['id'] == self.edge[1])
                        if departing and detail['date'] == leg.departure_time[:10]:
                            margin = hi - last
                            note = '；时间较紧，建议增加接驳缓冲后重查' if margin <= 30 else ''
                            reasons.append(f"{detail['date']} 原安排至{clock(last)}，含缓冲须{clock(hi)}前结束，现有缓冲外剩余{margin}分钟{note}")
                        if arriving and detail['date'] == leg.arrival_time[:10]:
                            margin = first - lo
                            note = '；时间较紧，建议增加接驳缓冲后重查' if margin <= 30 else ''
                            reasons.append(f"{detail['date']} 含缓冲{clock(lo)}后可开始，当前安排{clock(first)}开始，现有缓冲外剩余{margin}分钟{note}")
                    if problems:
                        if scheduled:
                            first, last = min(i['start_minutes'] for i in scheduled), max(i['end_minutes'] for i in scheduled)
                            if last > hi:
                                problems.insert(0, f"{detail['date']} 含缓冲须{clock(hi)}前结束市内安排，原安排至{clock(last)}，无法保留全部活动与用餐")
                            if first < lo:
                                problems.insert(0, f"{detail['date']} 含缓冲{clock(lo)}后才可开始，原安排{clock(first)}开始")
                if not relevant:
                    reasons.append(city['city'] + '尚无当天完整安排，仅核对交通日期与窗口，不能确认全部游玩衔接')
            reasons.append('沿用已保存市内路线；站场接驳及办理缓冲为可编辑估计，未重新导航核实')
            return leg, reasons, list(dict.fromkeys(problems))
        except (ValidationError, ValueError):
            return leg, [], ['班次日期或安排无法沿用，请调整后重新查询']


async def load_schedule(context, query):
    return await ScheduleCheck().initialize(context, query)
