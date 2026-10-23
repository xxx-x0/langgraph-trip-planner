from unittest.mock import AsyncMock
import pytest
from app.services.bing_mcp_service import BingMCPService
from app.services.external_calls import classify_error, FailureKind


@pytest.mark.asyncio
async def test_crawl_uses_observed_server_uuid_url_map_schema():
    service=BingMCPService();service._call_tool=AsyncMock(return_value={'content':'page'})
    await service.crawl_webpage(['known-search-id'],{'known-search-id':'https://example.org'})
    assert service._call_tool.await_args.args==('crawl_webpage',{
        'uuids':['known-search-id'],'urlMap':{'known-search-id':'https://example.org'}})


def test_observed_bing_rejection_is_non_retryable_input_failure():
    assert classify_error(RuntimeError('当前输入可能包含不当内容，请修改后重试。'))==FailureKind.INVALID_REQUEST
