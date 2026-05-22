from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.utils.duration import (
    CATEGORY_DURATION_MAP,
    estimate_durations_batch,
    _fallback_durations,
)


def test_category_map_has_default():
    assert "default" in CATEGORY_DURATION_MAP
    assert CATEGORY_DURATION_MAP["default"] > 0


def test_fallback_uses_category_map():
    attractions = [
        {"name": "故宫", "category": "博物馆"},
        {"name": "未知地点", "category": "未知类别"},
        {"name": "无类别"},
    ]
    result = _fallback_durations(attractions)
    assert result["故宫"] == CATEGORY_DURATION_MAP["博物馆"]
    assert result["未知地点"] == CATEGORY_DURATION_MAP["default"]
    assert result["无类别"] == CATEGORY_DURATION_MAP["default"]


@pytest.mark.asyncio
async def test_estimate_durations_returns_llm_result_when_valid():
    fake_response = type("R", (), {"content":
        '[{"name":"故宫","visit_minutes":150},'
        '{"name":"颐和园","visit_minutes":120}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration.get_llm",
               return_value=object()), \
         patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "故宫", "description": "", "category": "博物馆"},
            {"name": "颐和园", "description": "", "category": "公园"},
        ])
    assert result == {"故宫": 150, "颐和园": 120}


@pytest.mark.asyncio
async def test_estimate_durations_falls_back_on_llm_failure():
    with patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await estimate_durations_batch([
            {"name": "故宫", "category": "博物馆"},
        ])
    assert result == {"故宫": CATEGORY_DURATION_MAP["博物馆"]}


@pytest.mark.asyncio
async def test_estimate_durations_falls_back_for_invalid_minutes():
    fake_response = type("R", (), {"content":
        '[{"name":"A","visit_minutes":5},'
        '{"name":"B","visit_minutes":600},'
        '{"name":"C","visit_minutes":"bad"}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration.get_llm",
               return_value=object()), \
         patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "A", "category": "公园"},
            {"name": "B", "category": "博物馆"},
            {"name": "C", "category": "美食"},
        ])
    # A < 15 → fallback；B > 480 → fallback；C 非数字 → fallback
    assert result["A"] == CATEGORY_DURATION_MAP["公园"]
    assert result["B"] == CATEGORY_DURATION_MAP["博物馆"]
    assert result["C"] == CATEGORY_DURATION_MAP["美食"]


@pytest.mark.asyncio
async def test_estimate_durations_fills_missing_names():
    """LLM 只返回了部分景点的估算，缺失项用 fallback 补齐"""
    fake_response = type("R", (), {"content":
        '[{"name":"故宫","visit_minutes":150}]'
    })()
    with patch("app.agents.langgraph_agent.utils.duration.get_llm",
               return_value=object()), \
         patch("app.agents.langgraph_agent.utils.duration._invoke_llm_with_retry",
               new=AsyncMock(return_value=fake_response)):
        result = await estimate_durations_batch([
            {"name": "故宫", "category": "博物馆"},
            {"name": "颐和园", "category": "公园"},
        ])
    assert result["故宫"] == 150
    assert result["颐和园"] == CATEGORY_DURATION_MAP["公园"]
