from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.search import search_attractions_node
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
            poi_id="B000A8UIN8",
            amap_type="风景名胜;风景名胜",
        ),
        CachedAttraction(
            name="天坛公园",
            address="北京市东城区天坛路甲1号",
            longitude=116.410829,
            latitude=39.881913,
            category="历史文化",
            poi_id="B000A83M61",
            amap_type="风景名胜;公园广场",
        ),
    ]


@pytest.mark.asyncio
async def test_search_attractions_node_returns_selected_pois_and_info(mock_trip_request, cached_attractions):
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions
    service.find_by_name.return_value = None

    with patch("app.agents.langgraph_agent.nodes.search.get_attractions_cache_service", return_value=service):
        with patch("app.agents.langgraph_agent.nodes.search.analyze_free_text", AsyncMock(return_value={"attractions": [], "food_preferences": [], "accommodation_preferences": [], "general_suggestions": []})):
            result = await search_attractions_node({"request": mock_trip_request, "errors": []})

    assert [p["name"] for p in result["selected_pois"]] == ["故宫博物院", "天坛公园"]
    assert "pois" in result["attractions_info"]
    service.get_attractions.assert_awaited_once_with(city="北京", min_count=15, categories=["历史文化"])


@pytest.mark.asyncio
async def test_search_attractions_node_puts_must_visit_first(mock_trip_request, cached_attractions):
    mock_trip_request.free_text_input = "一定要去颐和园"
    service = AsyncMock()
    service.get_attractions.return_value = cached_attractions
    service.find_by_name.return_value = CachedAttraction(
        name="颐和园",
        address="北京市海淀区",
        longitude=116.273,
        latitude=39.999,
        category="历史文化",
    )

    with patch("app.agents.langgraph_agent.nodes.search.get_attractions_cache_service", return_value=service):
        with patch("app.agents.langgraph_agent.nodes.search.analyze_free_text", AsyncMock(return_value={"attractions": ["颐和园"], "food_preferences": [], "accommodation_preferences": [], "general_suggestions": []})):
            result = await search_attractions_node({"request": mock_trip_request, "errors": []})

    assert result["selected_pois"][0]["name"] == "颐和园"
    service.find_by_name.assert_awaited_once_with("北京", "颐和园")


@pytest.mark.asyncio
async def test_search_attractions_node_records_service_error(mock_trip_request):
    service = AsyncMock()
    service.get_attractions.side_effect = RuntimeError("AMap unavailable")

    with patch("app.agents.langgraph_agent.nodes.search.get_attractions_cache_service", return_value=service):
        result = await search_attractions_node({"request": mock_trip_request, "errors": []})

    assert result["selected_pois"] == []
    assert result["attractions_info"] == ""
    assert result["errors"][0].startswith("search_attractions: 查询失败")
