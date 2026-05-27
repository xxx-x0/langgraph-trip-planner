from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.discovery import search_attractions_discovery_node
from app.models.schemas import TripRequest
from app.services.attractions_cache_service import CachedAttraction


@pytest.fixture
def mock_trip_request():
    return TripRequest(
        city="北京",
        start_date="2026-05-01",
        end_date="2026-05-03",
        travel_days=3,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化"],
        free_text_input="",
    )


@pytest.fixture
def cached_attractions():
    return [
        CachedAttraction(
            name="故宫博物院",
            address="北京市东城区景山前街4号",
            longitude=116.397128,
            latitude=39.916527,
            category="历史文化",
            rating=4.8,
            poi_id="B000A8UIN8",
        ),
        CachedAttraction(
            name="天坛公园",
            address="北京市东城区天坛路甲1号",
            longitude=116.410829,
            latitude=39.881913,
            category="历史文化",
            rating=4.7,
            poi_id="B000A83M61",
        ),
    ]


@pytest.mark.asyncio
async def test_search_attractions_discovery_node_returns_service_attractions(mock_trip_request, cached_attractions):
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions

    with patch("app.agents.langgraph_agent.nodes.discovery.get_attractions_cache_service", return_value=service):
        result = await search_attractions_discovery_node({"request": mock_trip_request, "errors": []})

    assert len(result["discovered_attractions"]) == 2
    assert result["discovered_attractions"][0]["name"] == "故宫博物院"
    assert result["discovered_attractions"][0]["location"] == {"longitude": 116.397128, "latitude": 39.916527}
    service.get_attractions.assert_awaited_once_with(city="北京", min_count=40, categories=["历史文化"])


@pytest.mark.asyncio
async def test_search_attractions_discovery_node_records_service_error(mock_trip_request):
    service = AsyncMock()
    service.get_attractions.side_effect = RuntimeError("AMap unavailable")

    with patch("app.agents.langgraph_agent.nodes.discovery.get_attractions_cache_service", return_value=service):
        result = await search_attractions_discovery_node({"request": mock_trip_request, "errors": []})

    assert result["discovered_attractions"] == []
    assert result["errors"][0].startswith("search_attractions_discovery: 查询失败")


from app.agents.langgraph_agent.nodes.discovery import (
    _fetch_attractions_batch,
)


@pytest.mark.asyncio
async def test_fetch_attractions_batch_excludes_known_names():
    from app.services.attractions_cache_service import CachedAttraction

    fake_pool = [
        CachedAttraction(name="故宫", longitude=116.397, latitude=39.916, category="博物馆"),
        CachedAttraction(name="天坛", longitude=116.412, latitude=39.882, category="古迹"),
        CachedAttraction(name="颐和园", longitude=116.273, latitude=39.999, category="公园"),
        CachedAttraction(name="圆明园", longitude=116.299, latitude=40.008, category="公园"),
    ]

    class FakeService:
        async def get_attractions(self, city, min_count, categories=None):
            return fake_pool

    with patch(
        "app.agents.langgraph_agent.nodes.discovery.get_attractions_cache_service",
        return_value=FakeService(),
    ):
        result = await _fetch_attractions_batch(
            city="北京",
            exclude_names={"故宫", "天坛"},
            batch_size=2,
            categories=None,
        )

    names = [a["name"] for a in result]
    assert "故宫" not in names
    assert "天坛" not in names
    assert len(result) == 2
