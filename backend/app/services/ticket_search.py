"""Local, read-only ticket searches. No account data or itinerary writes."""
import asyncio
import ipaddress
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .external_calls import CallPolicy, ExternalServiceError, FailureKind, invoke_external, operation_deadline
from .ticket_assistant import ObservedTicket

SHANGHAI = ZoneInfo('Asia/Shanghai')
REPO = Path(__file__).resolve().parents[3]
TTL = 15 * 60
CAP = 80
FLIGHT_CITIES = dict(zip(
    '北京 上海 广州 深圳 杭州 成都 重庆 西安 昆明 武汉 南京 厦门 长沙 青岛 威海 天津 郑州 海口 三亚 哈尔滨 沈阳 大连 济南 福州 贵阳 南宁 南昌 合肥 太原 兰州 乌鲁木齐 银川 西宁 拉萨 长春 呼和浩特'.split(),
    'bjs sha can szx hgh ctu ckg sia kmg wuh nkg xmn csx tao weh tsn cgo hak syx hrb she dlc tna foc kwe nng khn tyn lhw urc inc xnn lxa cgq het'.split()))


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['train', 'flight']
    direction: Literal['outbound', 'inbound'] = 'outbound'
    from_place: str = Field(min_length=1, max_length=80)
    to_place: str = Field(min_length=1, max_length=80)
    date: date
    passengers: int = Field(ge=1, le=20)
    adult_passengers: int | None = Field(default=None, ge=1, le=20)
    from_scope: Literal['auto', 'exact', 'city'] = 'auto'
    to_scope: Literal['auto', 'exact', 'city'] = 'auto'

    @model_validator(mode='after')
    def valid_query(self):
        self.from_place, self.to_place = self.from_place.strip(), self.to_place.strip()
        if not self.from_place or not self.to_place or self.from_place == self.to_place:
            raise ValueError('请填写不同的出发地和目的地')
        if self.adult_passengers is not None and self.adult_passengers != self.passengers:
            raise ValueError('仅在明确全部为成人时传递成人总人数')
        if self.mode == 'flight' and any(p.removesuffix('市') not in FLIGHT_CITIES for p in (self.from_place, self.to_place)):
            raise ValueError('该地点尚无航班城市代码，请使用网站查询或选择已收录城市')
        return self


def local_only(request: Request):
    """This unauthenticated browser controller is restricted to the local machine."""
    def loopback(host):
        if host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host or '').is_loopback
        except ValueError:
            return False
    origin = request.headers.get('origin')
    if (not request.client or not loopback(request.client.host) or
        not loopback(request.url.hostname) or
        (origin and (urlparse(origin).scheme != 'http' or not loopback(urlparse(origin).hostname)))):
        raise HTTPException(403, '免扩展查票仅限本机使用')


class SearchProblem(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(code)  # Never include website bodies, cookies or login URLs.


def sample(candidates):
    ordered = sorted(candidates, key=lambda c: (c['departure'], c['service'], c['seat']))
    if len(ordered) <= CAP:
        return ordered
    return [ordered[i * (len(ordered) - 1) // (CAP - 1)] for i in range(CAP)]


async def rail_get(client, path, **kwargs):
    async def fetch():
        response = await client.get(path, **kwargs)
        if response.status_code >= 400:
            kind = FailureKind.AUTH if response.status_code in {401, 403} else FailureKind.RATE_LIMIT if response.status_code == 429 else FailureKind.UNAVAILABLE
            raise ExternalServiceError('12306', 'search', kind)
        if len(response.content) > 5_000_000:
            raise SearchProblem('invalid_response', '12306返回数据过大，本次未采用')
        return response
    return await invoke_external('12306', 'search', fetch,
        policy=CallPolicy(total_timeout=20, attempt_timeout=18, max_attempts=1, concurrency=2))


def station_data(script):
    """The public station-name asset contains @-separated records; never execute it."""
    stations, cities = {}, {}
    for record in script.split('@')[1:]:
        parts = record.split('|')
        if len(parts) < 8 or not re.fullmatch(r'[A-Z]{3}', parts[2]):
            continue
        name, code, city = parts[1], parts[2], parts[7]
        stations[name] = code
        if city:
            cities.setdefault(city, set()).add(code)
    if not stations:
        raise SearchProblem('invalid_stations', '12306车站表无法识别，请稍后重试或使用网站查询')
    return stations, cities


def station_scope(place, scope, stations, cities):
    name = place.removesuffix('市')
    if name not in stations:
        name = name.removesuffix('站')
    if scope == 'city' or (scope == 'auto' and name in cities):
        if name not in cities:
            raise SearchProblem('invalid_station', '城市未匹配，请改填具体车站或使用网站查询')
        codes = cities[name]
        return stations.get(name, sorted(codes)[0]), codes
    if name not in stations:
        raise SearchProblem('invalid_station', '站名未匹配，请核对具体车站或使用网站查询')
    return stations[name], {stations[name]}


# Public 12306 query row fields, not an executable third-party MCP implementation.
SEATS = [('O', '二等座', 30), ('M', '一等座', 31), ('9', '商务座', 32),
         ('P', '特等座', 25), ('1', '硬座', 29), ('3', '硬卧', 28),
         ('4', '软卧', 23), ('6', '高级软卧', 21), ('2', '软座', 24)]


def rail_candidates(payload, query, from_codes, to_codes, stations):
    if not isinstance(payload, dict) or payload.get('status') is not True or not isinstance(payload.get('data'), dict):
        raise SearchProblem('invalid_response', '12306未返回有效查询结果，请使用网站核对；不能据此判断无票')
    data = payload['data']
    if not isinstance(data.get('result'), list) or not isinstance(data.get('map'), dict):
        raise SearchProblem('invalid_response', '12306结果格式已变化，请使用网站查询')
    names = {code: name for name, code in stations.items()} | data['map']
    candidates, malformed, relevant = [], 0, 0
    for raw in data['result']:
        if not isinstance(raw, str):
            malformed += 1
            continue
        row = raw.split('|')
        if len(row) < 40:
            malformed += 1
            continue
        if row[6] not in from_codes or row[7] not in to_codes:
            continue  # Exact/city scope must be checked before sampling.
        relevant += 1
        if row[11] != 'Y':
            continue
        try:
            if not re.fullmatch(r'[GDCZTKYSL]?\d{1,5}', row[3]) or not re.fullmatch(r'\d{2,3}:\d{2}', row[10]):
                raise ValueError()
            hours, mins = map(int, row[10].split(':'))
            start = datetime.fromisoformat(f'{query.date}T{row[8]}')
            end = start + timedelta(hours=hours, minutes=mins)
            if mins >= 60 or end <= start or end - start > timedelta(days=7) or end.strftime('%H:%M') != row[9]:
                raise ValueError()
            # Query date is the boarding date. row[13] is the train's origin date.
            prices = {}
            for offset in range(0, len(row[39]) - 9, 10):
                chunk = row[39][offset:offset + 10]
                if chunk[1:6].isdigit() and chunk[6:10].isdigit() and int(chunk[6:10]) < 3000:
                    prices[chunk[0]] = int(chunk[1:6]) / 10
            for code, seat, index in SEATS:
                count = row[index]
                if count != '有' and not (count.isdigit() and int(count) >= query.passengers):
                    continue
                # Unknown/discounted or unmapped price is unknown, never zero.
                amount = prices.get(code)
                candidate = ObservedTicket(id=f'rail_{len(candidates)}_{row[3]}', mode='train', service=row[3],
                    from_station=names[row[6]], to_station=names[row[7]],
                    departure=start.isoformat(timespec='minutes'), arrival=end.isoformat(timespec='minutes'),
                    seat=seat, fare_per_person=amount, availability='available', source='12306')
                candidates.append(candidate.model_dump())
        except (ValueError, KeyError, TypeError):
            malformed += 1
    if malformed:
        raise SearchProblem('invalid_response', '部分12306班次无法正确解析，本次结果未采用，请使用网站核对')
    if data['result'] and not relevant:
        raise SearchProblem('no_matching_stations', '返回班次均不符合本次车站范围，请使用网站核对；不能据此判断无票')
    return candidates


async def search_rail(query):
    async with httpx.AsyncClient(timeout=18, follow_redirects=False,
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://kyfw.12306.cn/otn/leftTicket/init'}) as client:
        page = await rail_get(client, 'https://kyfw.12306.cn/otn/leftTicket/init')
        path = re.search(r"\bCLeftTicketUrl\s*=\s*['\"](leftTicket/[A-Za-z0-9]+)['\"]", page.text)
        if not path:
            raise SearchProblem('invalid_response', '12306查询入口未能初始化，请稍后重试或使用网站查询')
        home = await rail_get(client, 'https://www.12306.cn/index/')
        asset = re.search(r"(?:\./)?(/?script/core/common/station_name[\w.-]*\.js)(?:\?[^'\"<> ]*)?", home.text)
        if not asset:
            raise SearchProblem('invalid_stations', '12306车站表入口无法识别，请使用网站查询')
        response = await rail_get(client, urljoin('https://www.12306.cn/index/', asset[0]))
        stations, cities = station_data(response.text)
        frm, from_codes = station_scope(query.from_place, query.from_scope, stations, cities)
        to, to_codes = station_scope(query.to_place, query.to_scope, stations, cities)
        result = await rail_get(client, 'https://kyfw.12306.cn/otn/' + path[1], params={
            'leftTicketDTO.train_date': str(query.date), 'leftTicketDTO.from_station': frm,
            'leftTicketDTO.to_station': to, 'purpose_codes': 'ADULT'})
        try:
            payload = result.json()
        except ValueError:
            raise SearchProblem('invalid_response', '12306返回了非查询数据，请使用网站完成验证后再试') from None
        values = rail_candidates(payload, query, from_codes, to_codes, stations)
        return dict(candidates=sample(values), total_count=len(values), sampled=len(values) > CAP,
            message='已读取12306本次可识别的有票席别；票价为成人参考价，人数、票种及可购状态请在出票前核对。' if values else
                    '未读到满足同行人数的可识别有票席别；本次不含候补、无座及不支持席别，请到12306核对。')


@dataclass
class SearchJob:
    id: str
    query: SearchQuery
    created: float = field(default_factory=time.monotonic)
    status: str = 'searching'
    message: str = '正在查询…'
    candidates: list = field(default_factory=list)
    total_count: int = 0
    sampled: bool = False
    browser_visible: bool = False
    code: str | None = None
    collected_at: str | None = None
    task: asyncio.Task | None = None
    expiry_task: asyncio.Task | None = None

    def public(self):
        return dict(search_id=self.id, status=self.status, message=self.message,
            candidates=self.candidates, total_count=self.total_count, sampled=self.sampled,
            browser_visible=self.browser_visible, code=self.code, collected_at=self.collected_at,
            source='rail_http' if self.query.mode == 'train' else 'managed_browser')


class TicketSearches:
    def __init__(self):
        self.jobs = OrderedDict()
        self.browser = None
        self.start_lock = asyncio.Lock()

    async def start(self, query):
        async with self.start_lock:
            return await self._start(query)

    async def _start(self, query):
        today = datetime.now(SHANGHAI).date()
        if query.date < today:
            raise HTTPException(422, '不能查询过去日期，请核对出发日期')
        if query.mode == 'train' and query.date > today + timedelta(days=14):
            raise HTTPException(422, '铁路日期超出通常15天预售范围，请临近出发时再查或到12306核对')
        for key, value in list(self.jobs.items()):
            if time.monotonic() - value.created > TTL or (query.mode == 'flight' and value.query.mode == 'flight'):
                await self.cancel(key)
                self.jobs.pop(key, None)
        if len(self.jobs) >= 16:
            terminal = next((k for k, v in self.jobs.items() if v.status not in {'searching', 'needs_action'}), None)
            if terminal:
                await self.cancel(terminal)
                self.jobs.pop(terminal)
            else:
                raise HTTPException(429, '正在进行的查询过多，请先停止旧查询')
        job = SearchJob(uuid.uuid4().hex, query)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self.run(job))
        job.expiry_task = asyncio.create_task(self.expire(job.id))
        return job.public()

    async def expire(self, key):
        await asyncio.sleep(TTL)
        await self.cancel(key)
        self.jobs.pop(key, None)

    async def get(self, key):
        job = self.jobs.get(key)
        if not job:
            raise HTTPException(404, '查询不存在或后端已重启，请重新查票')
        if time.monotonic() - job.created > TTL:
            await self.cancel(key)
            self.jobs.pop(key, None)
            raise HTTPException(410, '本次查票已过期，请重新查询')
        return job

    async def run(self, job, headed=False):
        try:
            async with operation_deadline(55):
                if job.query.mode == 'train':
                    result = await search_rail(job.query)
                else:
                    from .ticket_browser import TicketBrowser
                    if self.browser is None:
                        self.browser = TicketBrowser()
                    result = await invoke_external('ctrip', 'search', lambda: self.browser.search(job, headed),
                        policy=CallPolicy(total_timeout=50, attempt_timeout=50, max_attempts=1, concurrency=1))
            if job.status == 'cancelled':
                return
            job.status = result.get('status', 'completed')
            job.message = result['message']
            job.code = result.get('code')
            job.candidates = result.get('candidates', [])
            job.total_count = result.get('total_count', len(job.candidates))
            job.sampled = result.get('sampled', False)
            if job.status == 'completed':
                job.collected_at = datetime.now(SHANGHAI).isoformat(timespec='seconds')
        except asyncio.CancelledError:
            job.status, job.message = 'cancelled', '已停止本次查询，已保存行程未改变。'
            raise
        except SearchProblem as error:
            job.status, job.code, job.message = 'failed', error.code, error.message
        except (ExternalServiceError, TimeoutError) as error:
            job.status = 'failed'
            job.code = str(getattr(error, 'kind', 'timeout'))
            job.message = '本次网站查询未完成或访问受限，可重试或使用网站查询；已保存行程未改变。'
        except Exception:
            job.status, job.code = 'failed', 'unavailable'
            job.message = '本次查询未完成，可重试或使用网站查询；已保存行程未改变。'

    async def resume(self, key, show_browser=False):
        job = await self.get(key)
        if job.query.mode != 'flight' or job.status != 'needs_action':
            raise HTTPException(409, '当前查询不处于待处理状态，请重新查票')
        job.status, job.code = 'searching', None
        job.message = '正在打开本机查询窗口…' if show_browser else '正在继续读取携程列表…'
        job.task = asyncio.create_task(self.run(job, headed=show_browser or job.browser_visible))
        return job.public()

    async def cancel(self, key):
        job = self.jobs.get(key)
        if not job:
            return
        job.status, job.candidates, job.message = 'cancelled', [], '已停止本次查询，已保存行程未改变。'
        if job.expiry_task and job.expiry_task is not asyncio.current_task():
            job.expiry_task.cancel()
            await asyncio.gather(job.expiry_task, return_exceptions=True)
        if job.task and not job.task.done():
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)
        if self.browser:
            await self.browser.close_job(key)

    async def close(self):
        for key in list(self.jobs):
            await self.cancel(key)
        self.jobs.clear()
        if self.browser:
            await self.browser.close()


searches = TicketSearches()
