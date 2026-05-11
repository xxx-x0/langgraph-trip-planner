import os
import sys

backend_path = r"F:\hello-agents\helloagents-trip-planner\backend"
project_path = r"F:\hello-agents"

if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if project_path not in sys.path:
    sys.path.insert(0, project_path)

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import AIMessage

from app.agents.langgraph_agent import (
    _parse_response,
    _create_fallback_plan,
    quality_gate_node,
    route_after_quality_gate,
    LangGraphTripPlanner,
    TripPlannerState
)
from app.models.schemas import TripRequest, TripPlan, Location

# ================= Fixtures =================

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
        free_text_input="想吃烤鸭"
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
            "total": 1000
        }
    })

@pytest.fixture
def base_state(mock_trip_request):
    return {
        "request": mock_trip_request,
        "attractions": [],
        "weather": [],
        "hotels": [],
        "foods": [],
        "clusters": [],
        "routes": [],
        "poi_details": {},
        "quality_report": {},
        "trip_plan": None,
        "errors": [],
        "messages": []
    }

# ================= 测试 _parse_response =================

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

# ================= 测试 _create_fallback_plan =================

def test_create_fallback_plan(mock_trip_request):
    fallback_plan = _create_fallback_plan(mock_trip_request)
    assert isinstance(fallback_plan, TripPlan)
    assert fallback_plan.city == "北京"
    assert len(fallback_plan.days) == 3
    assert fallback_plan.days[0].date == "2026-05-01"
    assert fallback_plan.days[2].date == "2026-05-03"
    assert "建议提前查看各景点的开放时间" in fallback_plan.overall_suggestions

# ================= 测试 quality_gate_node =================

def test_quality_gate_node_full_pipeline(base_state):
    base_state["attractions"] = [{"id": "1", "name": "故宫"}]
    base_state["weather"] = [{"date": "2026-05-01", "day_weather": "晴"}]
    base_state["hotels"] = [{"id": "h1", "name": "如家"}]

    result = quality_gate_node(base_state)

    assert "quality_report" in result
    assert result["quality_report"]["has_attractions"] is True
    assert result["quality_report"]["has_weather"] is True
    assert result["quality_report"]["has_hotels"] is True
    assert result["quality_report"]["attraction_count"] == 1

def test_quality_gate_node_degraded_mode(base_state):
    result = quality_gate_node(base_state)

    assert "quality_report" in result
    assert result["quality_report"]["has_attractions"] is False
    assert result["quality_report"]["has_weather"] is False
    assert result["quality_report"]["has_hotels"] is False

# ================= 测试 route_after_quality_gate =================

def test_route_after_quality_gate_full(base_state):
    base_state["quality_report"] = {"has_attractions": True}
    assert route_after_quality_gate(base_state) == "full_pipeline"

def test_route_after_quality_gate_degraded(base_state):
    base_state["quality_report"] = {"has_attractions": False}
    assert route_after_quality_gate(base_state) == "degraded_mode"

def test_route_after_quality_gate_empty_report(base_state):
    assert route_after_quality_gate(base_state) == "degraded_mode"

# ================= 测试主流程 LangGraphTripPlanner =================

@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.create_trip_planner_graph")
async def test_plan_trip_success(mock_create_graph, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock()
    mock_create_graph.return_value = mock_app

    mock_plan = TripPlan(
        city="北京",
        start_date="2026-05-01",
        end_date="2026-05-03",
        days=[],
        weather_info=[],
        overall_suggestions="好建议"
    )
    mock_app.ainvoke.return_value = {"trip_plan": mock_plan}

    planner = LangGraphTripPlanner()
    result = await planner.plan_trip(mock_trip_request)

    assert result is mock_plan
    mock_app.ainvoke.assert_called_once()

@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.create_trip_planner_graph")
async def test_plan_trip_fallback_on_exception(mock_create_graph, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock()
    mock_create_graph.return_value = mock_app

    mock_app.ainvoke.side_effect = Exception("LLM 请求超时")

    planner = LangGraphTripPlanner()
    result = await planner.plan_trip(mock_trip_request)

    assert isinstance(result, TripPlan)
    assert result.city == "北京"
    assert "建议提前查看各景点的开放时间" in result.overall_suggestions

@pytest.mark.asyncio
@patch("app.agents.langgraph_agent.create_trip_planner_graph")
async def test_plan_trip_fallback_on_none_plan(mock_create_graph, mock_trip_request):
    mock_app = MagicMock()
    mock_app.ainvoke = AsyncMock()
    mock_create_graph.return_value = mock_app

    mock_app.ainvoke.return_value = {"trip_plan": None}

    planner = LangGraphTripPlanner()
    result = await planner.plan_trip(mock_trip_request)

    assert isinstance(result, TripPlan)
    assert len(result.days) == 3
