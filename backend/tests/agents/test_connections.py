import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SMOKE_TESTS") != "1",
    reason="Live LLM/MCP smoke tests require RUN_SMOKE_TESTS=1 and configured credentials.",
)


def test_llm_connection():
    from app.services.llm_service import get_llm

    llm = get_llm()
    response = llm.invoke([{"role": "user", "content": "回复我'OK'即可"}])
    assert response is not None


@pytest.mark.asyncio
async def test_amap_weather_connection():
    from app.services.langchain_amap_tools import get_langchain_amap_service

    service = get_langchain_amap_service()
    result = await service.get_weather("北京")
    assert result is not None


@pytest.mark.asyncio
async def test_amap_poi_search_connection():
    from app.services.langchain_amap_tools import get_langchain_amap_service

    service = get_langchain_amap_service()
    result = await service.search_poi("故宫", "北京")
    assert result is not None


@pytest.mark.asyncio
async def test_amap_direction_connection():
    from app.services.langchain_amap_tools import get_langchain_amap_service

    service = get_langchain_amap_service()
    result = await service.plan_route(
        origin_address="北京市东城区景山前街4号故宫博物院",
        destination_address="北京市东城区长安街天安门",
        origin_city="北京",
        destination_city="北京",
        route_type="walking",
    )
    assert result is not None
