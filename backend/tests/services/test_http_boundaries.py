import asyncio
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.services.external_calls import classify_error, FailureKind, clear_external_state
from app.services.open_meteo_service import OpenMeteoWeatherService
from app.services.unsplash_service import UnsplashService


@pytest.mark.parametrize('error,kind', [
    (httpx.ReadTimeout(''),FailureKind.TIMEOUT),
    (httpx.ConnectError(''),FailureKind.CONNECTION),
    (ExceptionGroup('transport',[httpx.ReadTimeout('')]),FailureKind.TIMEOUT)])
def test_typed_transport_errors_work_without_message_heuristics(error,kind):
    assert classify_error(error)==kind


@pytest.mark.asyncio
async def test_open_meteo_uses_the_shared_retry_owner():
    clear_external_state()
    service=OpenMeteoWeatherService()
    service._fetch_daily_weather=AsyncMock(side_effect=[httpx.ConnectError(''),[]])
    assert await service.fetch_daily_weather('苏州','2026-10-15','2026-10-16')==[]
    assert service._fetch_daily_weather.await_count==2


@pytest.mark.asyncio
async def test_photo_cancellation_propagates_and_releases_capacity():
    clear_external_state()
    service=UnsplashService();service.access_key='synthetic-local-test-value'
    entered=asyncio.Event();cancelled=asyncio.Event()
    async def stalled(*args):
        entered.set()
        try:await asyncio.Event().wait()
        finally:cancelled.set()
    service._search_photos=stalled
    task=asyncio.create_task(service.search_photos('苏州'))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert cancelled.is_set()
    service._search_photos=AsyncMock(return_value=[{'url':'https://example.org/photo'}])
    assert await service.get_photo_url('苏州')=='https://example.org/photo'


@pytest.mark.asyncio
async def test_no_photo_is_explicit_fallback_not_success():
    from app.api.routes.poi_lg import get_attraction_photo
    service=AsyncMock();service.get_photo_url.return_value=None
    with patch('app.api.routes.poi_lg.get_unsplash_service',return_value=service):
        result=await get_attraction_photo('苏州博物馆','苏州')
    assert result['success'] is False
    assert result['data']['photo_url'] is None and '行程已保留' in result['message']
