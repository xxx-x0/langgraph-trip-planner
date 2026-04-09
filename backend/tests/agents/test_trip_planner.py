import os
import sys

# 将所需路径加入 sys.path
backend_path = r"F:\hello-agents\helloagents-trip-planner\backend"
project_path = r"F:\hello-agents"

if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if project_path not in sys.path:
    sys.path.insert(0, project_path)

import pytest
import json
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage

# 导入需要测试的模块和数据结构
from app.agents.langgraph_agent import (
    _parse_response,
    _create_fallback_plan,
    search_poi_node,
    generate_plan_node,
    LangGraphTripPlanner,
    TripPlannerState
)
from app.models.schemas import TripRequest, TripPlan

# ================= Fixtures =================

@pytest.fixture
def mock_trip_request():
    """提供一个模拟的 TripRequest 对象"""
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
    """提供一个合法的旅行计划 JSON 字符串"""
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

# ================= 测试 _parse_response =================

def test_parse_response_with_markdown_json(mock_trip_request, mock_trip_plan_json):
    """测试解析带有 ```json 标记的字符串"""
    response_text = f"这是为您生成的计划：\n```json\n{mock_trip_plan_json}\n```\n希望您喜欢！"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)
    assert plan.city == "北京"

def test_parse_response_with_markdown_only(mock_trip_request, mock_trip_plan_json):
    """测试解析只带有 ``` 标记的字符串"""
    response_text = f"```\n{mock_trip_plan_json}\n```"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)

def test_parse_response_with_pure_json(mock_trip_request, mock_trip_plan_json):
    """测试解析纯 JSON 字符串（前后有花括号）"""
    response_text = f"一些废话... {mock_trip_plan_json} ...还有废话"
    plan = _parse_response(response_text, mock_trip_request)
    assert isinstance(plan, TripPlan)

def test_parse_response_failure(mock_trip_request):
    """测试解析失败时是否抛出异常"""
    bad_response = "我找不到任何 JSON 数据"
    with pytest.raises(ValueError, match="解析 JSON 失败: 响应中未找到JSON数据"):
        _parse_response(bad_response, mock_trip_request)

# ================= 测试 _create_fallback_plan =================

def test_create_fallback_plan(mock_trip_request):
    """测试兜底计划的生成"""
    fallback_plan = _create_fallback_plan(mock_trip_request)
    assert isinstance(fallback_plan, TripPlan)
    assert fallback_plan.city == "北京"
    assert len(fallback_plan.days) == 3
    assert fallback_plan.days[0].date == "2026-05-01"
    assert fallback_plan.days[2].date == "2026-05-03"
    assert "建议提前查看各景点的开放时间" in fallback_plan.overall_suggestions

# ================= 测试单个节点 =================

@patch("app.agents.langgraph_agent.get_llm")
def test_search_poi_node_with_tool_call(mock_get_llm, mock_trip_request):
    """测试 search_poi_node 在 LLM 决定调用工具时的状态流转"""
    # 构建初始状态
    state: TripPlannerState = {
        "request": mock_trip_request,
        "attractions_info": "",
        "weather_info": "",
        "hotels_info": "",
        "route_info": "",
        "trip_plan": None,
        "errors": [],
        "messages": []
    }
    
    # Mock LLM 及其 bind_tools 方法
    mock_llm_instance = MagicMock()
    mock_get_llm.return_value = mock_llm_instance
    mock_llm_with_tools = MagicMock()
    mock_llm_instance.bind_tools.return_value = mock_llm_with_tools
    
    # Mock LLM invoke 返回，模拟带有 tool_calls
    mock_ai_message = AIMessage(
        content="", 
        tool_calls=[{"name": "amap_maps_text_search", "args": {"keywords": "历史文化", "city": "北京"}, "id": "call_1"}]
    )
    mock_llm_with_tools.invoke.return_value = mock_ai_message
    
    # Mock 工具的 invoke
    with patch("app.agents.langgraph_agent.amap_maps_text_search.func") as mock_tool_invoke:
        mock_tool_invoke.return_value = "找到故宫、颐和园等景点"
        
        # 为了让 node 里 amap_maps_text_search.invoke 正常工作并返回我们想要的值
        # 我们需要在 patch 之外替换 invoke 方法，或者直接 patch 工具本身
    
    with patch("app.agents.langgraph_agent.amap_maps_text_search") as mock_tool:
        mock_tool.invoke.return_value = "找到故宫、颐和园等景点"
        
        result = search_poi_node(state)
        
        assert "attractions_info" in result
        assert result["attractions_info"] == "找到故宫、颐和园等景点"
        mock_tool.invoke.assert_called_once_with({"keywords": "历史文化", "city": "北京"})

@patch("app.agents.langgraph_agent.get_llm")
def test_generate_plan_node_success(mock_get_llm, mock_trip_request, mock_trip_plan_json):
    """测试 generate_plan_node 成功生成并解析计划"""
    state: TripPlannerState = {
        "request": mock_trip_request,
        "attractions_info": "故宫",
        "weather_info": "晴天",
        "hotels_info": "如家",
        "route_info": "建议打车",
        "trip_plan": None,
        "errors": [],
        "messages": []
    }
    
    mock_llm_instance = MagicMock()
    mock_get_llm.return_value = mock_llm_instance
    
    # 模拟大模型直接返回带 Markdown 的 JSON
    mock_ai_message = AIMessage(content=f"```json\n{mock_trip_plan_json}\n```")
    mock_llm_instance.invoke.return_value = mock_ai_message
    
    result = generate_plan_node(state)
    
    assert "trip_plan" in result
    assert isinstance(result["trip_plan"], TripPlan)
    assert result["trip_plan"].city == "北京"

# ================= 测试主流程 LangGraphTripPlanner =================

@patch("app.agents.langgraph_agent.create_trip_planner_graph")
def test_plan_trip_success(mock_create_graph, mock_trip_request):
    """测试 plan_trip 正常返回大模型生成的计划"""
    mock_app = MagicMock()
    mock_create_graph.return_value = mock_app
    
    # 模拟最终生成了一个正确的计划对象
    mock_plan = TripPlan(
        city="北京",
        start_date="2026-05-01",
        end_date="2026-05-03",
        days=[],
        weather_info=[],
        overall_suggestions="好建议"
    )
    mock_app.invoke.return_value = {"trip_plan": mock_plan}
    
    planner = LangGraphTripPlanner()
    result = planner.plan_trip(mock_trip_request)
    
    assert result is mock_plan
    mock_app.invoke.assert_called_once()

@patch("app.agents.langgraph_agent.create_trip_planner_graph")
def test_plan_trip_fallback_on_exception(mock_create_graph, mock_trip_request):
    """测试 plan_trip 在运行图抛出异常时，是否触发 fallback"""
    mock_app = MagicMock()
    mock_create_graph.return_value = mock_app
    
    # 模拟运行图时发生异常（如网络中断）
    mock_app.invoke.side_effect = Exception("LLM 请求超时")
    
    planner = LangGraphTripPlanner()
    result = planner.plan_trip(mock_trip_request)
    
    # 断言：因为捕获了异常，所以应该返回由 fallback 生成的计划
    assert isinstance(result, TripPlan)
    assert result.city == "北京"
    assert "建议提前查看各景点的开放时间" in result.overall_suggestions

@patch("app.agents.langgraph_agent.create_trip_planner_graph")
def test_plan_trip_fallback_on_none_plan(mock_create_graph, mock_trip_request):
    """测试 plan_trip 当图返回的 trip_plan 为 None 时，是否触发 fallback"""
    mock_app = MagicMock()
    mock_create_graph.return_value = mock_app
    
    # 模拟图正常执行，但是由于解析失败或大模型拒绝回答，trip_plan 为 None
    mock_app.invoke.return_value = {"trip_plan": None}
    
    planner = LangGraphTripPlanner()
    result = planner.plan_trip(mock_trip_request)
    
    # 断言应该触发了 fallback 计划
    assert isinstance(result, TripPlan)
    assert len(result.days) == 3
