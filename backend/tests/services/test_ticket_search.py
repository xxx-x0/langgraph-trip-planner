"""Synthetic HTTP/browser fixtures. No live ticket providers or business database."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.services.ticket_search import (SearchQuery, TicketSearches, SearchProblem, SHANGHAI,
    rail_candidates, station_data, station_scope, sample, search_rail, SearchJob)


def query(**changes):
    return SearchQuery(mode='train', from_place='上海虹桥', to_place='北京南',
        date=datetime.now(SHANGHAI).date() + timedelta(days=1), passengers=2, **changes)


def row(service='G100', frm='AOH', to='VNP', start='08:00', end='12:30', duration='04:30', count='有', price='O055300021'):
    values = [''] * 57
    for index, value in {3:service, 6:frm, 7:to, 8:start, 9:end, 10:duration, 11:'Y',
        13:'20200101', 30:count, 31:'无', 39:price}.items():
        values[index] = value
    return '|'.join(values)


def payload(*rows):
    return {'status':True, 'data':{'result':list(rows), 'map':{'AOH':'上海虹桥','SHH':'上海','VNP':'北京南','BJP':'北京'}}}


def parse(*rows, q=None):
    return rail_candidates(payload(*rows), q or query(), {'AOH'}, {'VNP'}, {})


def test_scope_and_boarding_date_checked_before_sampling():
    values = parse(row(frm='SHH'), row(start='23:00', end='03:30'))
    assert len(values) == 1
    assert values[0]['from_station'] == '上海虹桥'
    assert values[0]['departure'] == f'{query().date}T23:00'
    assert values[0]['arrival'] == f'{query().date + timedelta(days=1)}T03:30'
    assert values[0]['fare_per_person'] == 553
    assert '20200101' not in str(values)
    assert all(key not in str(values) for key in ['secret_Sstr','Cookie','token'])


def test_multiple_seats_unknown_price_and_party_availability():
    values = row(count='1').split('|');values[31]='2'
    result = parse('|'.join(values))
    assert [c['seat'] for c in result] == ['一等座']
    assert result[0]['fare_per_person'] is None
    assert parse(row(count='候补')) == []
    assert parse(row(count='0')) == []
    both = row().split('|');both[31]='有'
    assert {c['seat'] for c in parse('|'.join(both))} == {'一等座','二等座'}


@pytest.mark.parametrize('raw',[row(duration='99:99'), row(end='01:00'), 'broken', row(start='bad')])
def test_malformed_provider_data_is_failure_not_empty_success(raw):
    with pytest.raises(SearchProblem):
        parse(raw)


def test_wrong_station_only_and_failure_envelope_not_no_tickets():
    with pytest.raises(SearchProblem, match='no_matching_stations'):
        parse(row(frm='SHH'))
    for value in [{'status':False}, {'status':True,'data':{}}, '<html>verify</html>']:
        with pytest.raises(SearchProblem):
            rail_candidates(value, query(), {'AOH'}, {'VNP'}, {})


def test_station_city_scope_is_explicit_and_asset_is_not_executed():
    stations,cities = station_data("var station_names ='@shh|上海|SHH|shanghai|sh|1|1|上海||@aoh|上海虹桥|AOH|shanghaihongqiao|shhq|2|2|上海||';")
    assert station_scope('上海','auto',stations,cities)[1] == {'SHH','AOH'}
    assert station_scope('上海','exact',stations,cities)[1] == {'SHH'}
    assert station_scope('上海虹桥站','auto',stations,cities)[1] == {'AOH'}
    with pytest.raises(SearchProblem):
        station_scope('未知','city',stations,cities)


def test_sampling_preserves_late_departures_and_unique_ids():
    candidates = [dict(departure=f'2026-10-27T{i//6:02d}:{i%6*10:02d}',service=f'G{i}',seat='二等座',id=str(i)) for i in range(140)]
    result = sample(candidates)
    assert len(result) == 80 and result[-1] == candidates[-1]
    assert len({r['id'] for r in result}) == 80


@pytest.mark.asyncio
async def test_http_initialization_uses_only_expected_hosts_and_json_not_html_tickets():
    from app.services import ticket_search
    calls = []
    async def get(client,url,**kwargs):
        calls.append((url,kwargs))
        if 'leftTicket/init' in url:
            return httpx.Response(200,text="var CLeftTicketUrl = 'leftTicket/queryG';")
        if url.endswith('/index/'):
            return httpx.Response(200,text='<script src="./script/core/common/station_name_v1.js"></script>')
        if 'station_name' in url:
            return httpx.Response(200,text="var station_names ='@a|上海虹桥|AOH|a|a|1|1|上海||@b|北京南|VNP|b|b|2|2|北京||';")
        return httpx.Response(200,json=payload(row()))
    with patch.object(ticket_search,'rail_get',side_effect=get):
        result = await search_rail(query())
    assert len(result['candidates']) == 1
    assert calls[-1][0] == 'https://kyfw.12306.cn/otn/leftTicket/queryG'
    assert calls[2][0] == 'https://www.12306.cn/index/script/core/common/station_name_v1.js'
    assert calls[-1][1]['params']['leftTicketDTO.train_date'] == str(query().date)
    assert 'leftTicketDTO.from_station' in calls[-1][1]['params']


@pytest.mark.asyncio
async def test_jobs_cancel_late_results_expire_and_never_save_itinerary():
    service = TicketSearches()
    entered = asyncio.Event()
    async def pending(q):
        entered.set();await asyncio.Event().wait()
    with patch('app.services.ticket_search.search_rail',side_effect=pending):
        result = await service.start(query())
        await entered.wait()
        await service.cancel(result['search_id'])
        job = await service.get(result['search_id'])
        assert job.status == 'cancelled' and not job.candidates and job.task.cancelled()
        assert '已停止' in job.message
        job.created -= 901
        with pytest.raises(Exception) as expired:
            await service.get(job.id)
        assert expired.value.status_code == 410
    await service.close()


@pytest.mark.asyncio
async def test_explicit_login_resume_and_shutdown_close_browser():
    service=TicketSearches()
    service.browser=AsyncMock()
    service.browser.search.return_value=dict(status='needs_action',message='请登录')
    q=query().model_copy(update={'mode':'flight','from_place':'上海','to_place':'北京'})
    started=await service.start(q);job=await service.get(started['search_id'])
    await job.task
    assert job.status == 'needs_action'
    service.browser.search.return_value=dict(candidates=[],message='网站显示未找到')
    await service.resume(job.id,show_browser=True);await job.task
    assert job.status == 'completed'
    assert service.browser.search.call_args.args[1] is True
    await service.close()
    service.browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_api_restricts_remote_browser_control_and_arbitrary_urls():
    from app.api.routes.ticket_assistant import router
    app=FastAPI();app.include_router(router,prefix='/api')
    body=query().model_dump(mode='json')
    with patch('app.api.routes.ticket_assistant.searches.start',new=AsyncMock(return_value={'search_id':'x','status':'searching'})) as start:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://localhost') as client:
            assert (await client.post('/api/tickets/search',json=body)).status_code == 200
            assert (await client.post('/api/tickets/search',json=body,headers={'Origin':'https://evil.example'})).status_code == 403
            assert (await client.post('/api/tickets/search',json=body|{'mode':'flight','from_place':'file:///etc/passwd'})).status_code == 422
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app,client=('192.0.2.10',1)),base_url='http://localhost') as client:
            assert (await client.post('/api/tickets/search',json=body)).status_code == 403
        assert start.await_count == 1
