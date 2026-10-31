"""Browser protocol substitutes, not evidence of website or login availability."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import get_settings
from app.services.ticket_browser import TicketBrowser
from app.services.ticket_search import SearchJob
from tests.services.test_ticket_search import query


@pytest.fixture
def browser_fixture(monkeypatch,tmp_path):
    settings=get_settings()
    monkeypatch.setattr(settings,'ticket_browser_profile_dir',str(tmp_path/'profile'))
    page=SimpleNamespace(is_closed=Mock(return_value=False),goto=AsyncMock(),evaluate=AsyncMock())
    context=SimpleNamespace(pages=[page],add_init_script=AsyncMock(),close=AsyncMock())
    driver=SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=AsyncMock(return_value=context)),stop=AsyncMock())
    factory=SimpleNamespace(start=AsyncMock(return_value=driver))
    monkeypatch.setitem(sys.modules,'playwright.async_api',SimpleNamespace(async_playwright=lambda:factory))
    job=SearchJob('job-one',query().model_copy(update={'mode':'flight','from_place':'上海','to_place':'北京'}))
    c=dict(id='flight_one',mode='flight',service='MU5000',from_station='虹桥',to_station='首都',
           departure=f'{job.query.date}T08:00',arrival=f'{job.query.date}T10:00',seat='经济舱',
           fare_per_person=500,availability='unknown',source='ctrip')
    return page,context,driver,job,c


@pytest.mark.asyncio
async def test_managed_browser_reads_only_candidates_and_uses_independent_profile(browser_fixture):
    page,context,driver,job,c=browser_fixture
    page.evaluate.side_effect=[dict(candidates=[c],empty=False),[c]]
    browser=TicketBrowser();result=await browser.search(job)
    assert result['candidates']==[c] and not job.browser_visible
    launched=driver.chromium.launch_persistent_context.call_args
    assert launched.kwargs['headless'] is True
    assert launched.args[0]==get_settings().ticket_browser_profile_dir
    assert 'adult=1' in page.goto.call_args.args[0]
    assert 'oneway-sha-bjs' in page.goto.call_args.args[0]
    await browser.close();context.close.assert_awaited_once();driver.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_list_requires_action_then_explicit_window_can_read(browser_fixture,monkeypatch):
    page,context,driver,job,c=browser_fixture
    monkeypatch.setattr('app.services.ticket_browser.asyncio.sleep',AsyncMock())
    page.evaluate.return_value=dict(candidates=[],empty=False)
    browser=TicketBrowser();result=await browser.search(job)
    assert result['status']=='needs_action' and not job.browser_visible
    context.close.assert_awaited_once()
    page.evaluate.side_effect=[dict(candidates=[c],empty=False),[c]]
    result=await browser.search(job,headed=True)
    assert result['candidates']==[c] and job.browser_visible
    assert driver.chromium.launch_persistent_context.call_args.kwargs['headless'] is False
    await browser.close()


@pytest.mark.asyncio
async def test_explicit_website_empty_is_distinct_from_missing_reader(browser_fixture):
    page,context,driver,job,c=browser_fixture
    page.evaluate.return_value=dict(candidates=[],empty=True)
    browser=TicketBrowser();result=await browser.search(job)
    assert result['candidates']==[] and result.get('status','completed')=='completed'
    assert '未找到' in result['message']
    await browser.close()


@pytest.mark.asyncio
async def test_cancel_closes_browser_without_turning_into_empty_success(browser_fixture):
    page,context,driver,job,c=browser_fixture
    entered=asyncio.Event()
    async def pending(*args):
        entered.set();await asyncio.Event().wait()
    page.evaluate.side_effect=pending
    browser=TicketBrowser();task=asyncio.create_task(browser.search(job))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    context.close.assert_awaited_once()
    await browser.close()


@pytest.mark.asyncio
async def test_runtime_failure_is_safe_and_closes_partial_context(browser_fixture):
    page,context,driver,job,c=browser_fixture
    page.goto.side_effect=RuntimeError('private cookie sentinel')
    browser=TicketBrowser();result=await browser.search(job)
    assert result['status']=='failed' and result['code']=='browser_unavailable'
    assert 'sentinel' not in str(result)
    context.close.assert_awaited_once();await browser.close()
