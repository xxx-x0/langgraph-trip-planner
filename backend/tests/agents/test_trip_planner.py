import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.langgraph_agent.graph import LangGraphTripPlanner
from app.agents.langgraph_agent.utils.parsing import _create_fallback_plan, _parse_response
from app.models.schemas import TripPlan, TripRequest


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
        free_text_input="想吃烤鸭",
    )


@pytest.fixture
def mock_trip_plan_json():
    return json.dumps({
        "city": "北京",
        "start_date": "2026-05-01",
        "end_date": "2026-05-03",
        "days": [],
        "weather_info": [],
        "overall_suggestions": "祝您旅途愉快",
        "budget": {
            "total_attractions": 100,
            "total_hotels": 200,
            "total_meals": 300,
            "total_transportation": 400,
            "total": 1000,
        },
    })


def test_parse_response_with_markdown_json(mock_trip_request, mock_trip_plan_json):
    response_text = f"这是为您生成的计划：\n```json\n{mock_trip_plan_json}\n```\n希望您喜欢！"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)
    assert plan.city == "北京"


def test_parse_response_with_markdown_only(mock_trip_request, mock_trip_plan_json):
    response_text = f"```\n{mock_trip_plan_json}\n```"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)


def test_parse_response_with_pure_json(mock_trip_request, mock_trip_plan_json):
    response_text = f"一些废话... {mock_trip_plan_json} ...还有废话"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)


def test_parse_response_failure(mock_trip_request):
    bad_response = "我找不到任何 JSON 数据"
    with pytest.raises(ValueError, match="解析 JSON 失败: 响应中未找到JSON数据"):
        _parse_response(bad_response, mock_trip_request)


def test_create_fallback_plan(mock_trip_request):
    fallback_plan = _create_fallback_plan(mock_trip_request)
    assert isinstance(fallback_plan, TripPlan)
    assert fallback_plan.city == "北京"
    assert len(fallback_plan.days) == 3
    assert fallback_plan.days[0].date == "2026-05-01"
    assert fallback_plan.days[2].date == "2026-05-03"
    assert "建议提前确认各景点的开放时间" in fallback_plan.overall_suggestions


@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.graph.create_discovery_graph")
@patch("app.agents.langgraph_agent.graph.create_planning_graph")
@patch("app.agents.langgraph_agent.graph.create_trip_planner_graph")
async def test_plan_trip_success(mock_create_graph, mock_create_planning, mock_create_discovery, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock()
    mock_create_graph.return_value = mock_app
    mock_create_discovery.return_value = MagicMock()
    mock_create_planning.return_value = MagicMock()

    mock_plan = TripPlan(
        city="北京",
        start_date="2026-05-01",
        end_date="2026-05-03",
        days=[],
        weather_info=[],
        overall_suggestions="好建议",
    )
    mock_app.ainvoke.return_value = {"trip_plan": mock_plan}

    planner = LangGraphTripPlanner()
    with patch.object(planner, "_pre_init_services", AsyncMock()):
        result = await planner.plan_trip(mock_trip_request)

    assert result is mock_plan
    mock_app.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.graph.create_discovery_graph")
@patch("app.agents.langgraph_agent.graph.create_planning_graph")
@patch("app.agents.langgraph_agent.graph.create_trip_planner_graph")
async def test_plan_trip_fallback_on_exception(mock_create_graph, mock_create_planning, mock_create_discovery, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock(side_effect=Exception("LLM 请求超时"))
    mock_create_graph.return_value = mock_app
    mock_create_discovery.return_value = MagicMock()
    mock_create_planning.return_value = MagicMock()

    planner = LangGraphTripPlanner()
    with patch.object(planner, "_pre_init_services", AsyncMock()):
        result = await planner.plan_trip(mock_trip_request)

    assert isinstance(result, TripPlan)
    assert result.city == "北京"
    assert "建议提前确认各景点的开放时间" in result.overall_suggestions


@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.graph.create_discovery_graph")
@patch("app.agents.langgraph_agent.graph.create_planning_graph")
@patch("app.agents.langgraph_agent.graph.create_trip_planner_graph")
async def test_plan_trip_fallback_on_none_plan(mock_create_graph, mock_create_planning, mock_create_discovery, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock(return_value={"trip_plan": None})
    mock_create_graph.return_value = mock_app
    mock_create_discovery.return_value = MagicMock()
    mock_create_planning.return_value = MagicMock()

    planner = LangGraphTripPlanner()
    with patch.object(planner, "_pre_init_services", AsyncMock()):
        result = await planner.plan_trip(mock_trip_request)

    assert isinstance(result, TripPlan)
    assert len(result.days) == 3
