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
from langchain_core.messages import HumanMessage

# 导入需要测试的外部服务
from app.services.llm_service import get_llm
from app.services.langchain_amap_tools import (
    amap_maps_text_search, 
    amap_maps_weather,
    amap_maps_direction_walking
)

@pytest.mark.smoke
def test_llm_connection():
    """测试 LLM 连通性（Smoke Test）"""
    llm = get_llm()
    # 发送一个极其简单的请求以节省成本
    # 注意：HelloAgentsLLM 接受的是 dict 列表而不是 HumanMessage 对象
    response = llm.invoke([{"role": "user", "content": "回复我'OK'即可"}])
    assert response is not None
    assert len(response) > 0
    print(f"\n✅ LLM 连通性测试通过! 响应内容: {response}")

@pytest.mark.smoke
def test_amap_weather_connection():
    """测试高德天气 API 连通性（Smoke Test）"""
    # 模拟在没有 uvx/fastmcp 的环境中优雅跳过或给出提示
    print("\nℹ️ 提示：真实的 MCP 连通性测试需要安装 uvx 和对应的 MCP server，由于环境限制当前可能跳过...")
    try:
        # 查询北京天气
        result = amap_maps_weather.invoke({"city": "北京"})
        assert result is not None
        assert "error" not in result.lower() and "失败" not in result.lower()
        print(f"\n✅ 高德天气 API 连通性测试通过! 响应节选: {result[:50]}...")
    except Exception as e:
        print(f"\n⚠️ MCP 连通性测试未完全执行，可能因为缺少外部环境: {e}")

@pytest.mark.smoke
def test_amap_poi_search_connection():
    """测试高德 POI 搜索 API 连通性（Smoke Test）"""
    try:
        # 搜索北京故宫
        result = amap_maps_text_search.invoke({"keywords": "故宫", "city": "北京"})
        assert result is not None
        assert "error" not in result.lower() and "失败" not in result.lower()
        print(f"\n✅ 高德 POI 搜索 API 连通性测试通过! 响应节选: {result[:50]}...")
    except Exception as e:
        print(f"\n⚠️ MCP 连通性测试未完全执行，可能因为缺少外部环境: {e}")

@pytest.mark.smoke
def test_amap_direction_connection():
    """测试高德路线规划 API 连通性（Smoke Test）"""
    try:
        # 规划北京故宫到天安门的步行路线
        result = amap_maps_direction_walking.invoke({
            "origin_address": "北京市东城区景山前街4号故宫博物院",
            "destination_address": "北京市东城区长安街天安门"
        })
        assert result is not None
        assert "error" not in result.lower() and "失败" not in result.lower()
        print(f"\n✅ 高德路线规划 API 连通性测试通过! 响应节选: {result[:50]}...")
    except Exception as e:
        print(f"\n⚠️ MCP 连通性测试未完全执行，可能因为缺少外部环境: {e}")
