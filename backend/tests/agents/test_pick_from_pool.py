from unittest.mock import AsyncMock, patch
import pytest

from app.agents.langgraph_agent.utils.strategy_extract import (
    pick_attractions_from_pool,
    _rating_based_fallback,
)


def test_rating_fallback_descending_with_split():
    """days × 3 个 must + days × 2 个 optional，按 rating 降序"""
    pool = [
        {"poi_id": "1", "name": "A", "rating": "3.5"},
        {"poi_id": "2", "name": "B", "rating": "4.8"},
        {"poi_id": "3", "name": "C", "rating": "4.5"},
        {"poi_id": "4", "name": "D", "rating": "4.2"},
        {"poi_id": "5", "name": "E", "rating": "5.0"},
        {"poi_id": "6", "name": "F", "rating": "4.0"},
        {"poi_id": "7", "name": "G", "rating": "3.0"},
    ]
    must_ids, optional_ids = _rating_based_fallback(pool, days=1)
    # days=1 → must = top 3, optional = next 2
    assert must_ids == ["5", "2", "3"]  # rating 5.0, 4.8, 4.5
    assert optional_ids == ["4", "6"]  # rating 4.2, 4.0


def test_rating_fallback_handles_unparseable_rating():
    """rating 非数字时应当成 0 处理"""
    pool = [
        {"poi_id": "1", "name": "A", "rating": "4.0"},
        {"poi_id": "2", "name": "B", "rating": "未知"},
        {"poi_id": "3", "name": "C", "rating": ""},
        {"poi_id": "4", "name": "D"},  # 缺字段
    ]
    must_ids, optional_ids = _rating_based_fallback(pool, days=1)
    # rating 4.0 排第一
    assert must_ids[0] == "1"


def test_rating_fallback_skips_items_without_poi_id():
    """没有 poi_id 的景点不应出现在结果中"""
    pool = [
        {"poi_id": "1", "name": "A", "rating": "5.0"},
        {"name": "B-no-id", "rating": "4.9"},
        {"poi_id": "3", "name": "C", "rating": "4.5"},
    ]
    must_ids, _ = _rating_based_fallback(pool, days=1)
    assert "1" in must_ids
    assert "3" in must_ids
    # B 缺 poi_id 不出现
    for mid in must_ids:
        assert mid != ""


@pytest.mark.asyncio
async def test_pick_from_pool_falls_back_when_llm_fails():
    """LLM 抛异常时应当用 rating 兜底"""
    pool = [
        {"poi_id": str(i), "name": f"P{i}", "rating": str(5.0 - i * 0.1), "category": "x"}
        for i in range(5)
    ]

    # mock estimate_durations_batch 返回默认 120
    with patch(
        "app.agents.langgraph_agent.utils.strategy_extract.estimate_durations_batch",
        new=AsyncMock(return_value={f"P{i}": 120 for i in range(5)}),
    ), patch(
        "app.agents.langgraph_agent.utils.strategy_extract.get_llm",
        side_effect=RuntimeError("LLM 服务不可用"),
    ):
        result = await pick_attractions_from_pool(
            destination="北京",
            days=1,
            pool=pool,
        )

    # 应当 fallback：days=1 → must = top 3, optional = next 2
    assert "must_ids" in result and "optional_ids" in result
    assert result["must_ids"] == ["0", "1", "2"]  # 按 rating 降序
    assert result["optional_ids"] == ["3", "4"]


@pytest.mark.asyncio
async def test_pick_from_pool_returns_llm_result_on_success():
    """LLM 成功时返回 LLM 的选择"""
    pool = [
        {"poi_id": "1", "name": "故宫", "rating": "4.8", "category": "历史"},
        {"poi_id": "2", "name": "天坛", "rating": "4.7", "category": "古迹"},
        {"poi_id": "3", "name": "颐和园", "rating": "4.6", "category": "公园"},
    ]

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=type("R", (), {
        "content": '{"must": [{"poi_id": "1", "reason": "经典"}, {"poi_id": "2", "reason": "必去"}], "optional": [{"poi_id": "3", "reason": "时间足够可看"}]}'
    })())

    with patch(
        "app.agents.langgraph_agent.utils.strategy_extract.estimate_durations_batch",
        new=AsyncMock(return_value={"故宫": 120, "天坛": 90, "颐和园": 150}),
    ), patch(
        "app.agents.langgraph_agent.utils.strategy_extract.get_llm",
        return_value=fake_llm,
    ), patch(
        "app.agents.langgraph_agent.utils.strategy_extract.is_structured_output_supported",
        return_value=False,  # 走 JSON-in-prompt 路径，更易 mock
    ):
        result = await pick_attractions_from_pool(
            destination="北京",
            days=1,
            pool=pool,
        )

    assert result["must_ids"] == ["1", "2"]
    assert result["optional_ids"] == ["3"]


@pytest.mark.asyncio
async def test_pick_from_pool_falls_back_when_llm_returns_invalid_json():
    """LLM 返回无效 JSON 时也应兜底"""
    pool = [
        {"poi_id": "1", "name": "A", "rating": "5.0"},
        {"poi_id": "2", "name": "B", "rating": "4.0"},
        {"poi_id": "3", "name": "C", "rating": "3.0"},
        {"poi_id": "4", "name": "D", "rating": "2.0"},
        {"poi_id": "5", "name": "E", "rating": "1.0"},
    ]

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=type("R", (), {
        "content": "我不知道你在说什么"  # 非 JSON
    })())

    with patch(
        "app.agents.langgraph_agent.utils.strategy_extract.estimate_durations_batch",
        new=AsyncMock(return_value={f"{c}": 120 for c in "ABCDE"}),
    ), patch(
        "app.agents.langgraph_agent.utils.strategy_extract.get_llm",
        return_value=fake_llm,
    ), patch(
        "app.agents.langgraph_agent.utils.strategy_extract.is_structured_output_supported",
        return_value=False,
    ):
        result = await pick_attractions_from_pool(
            destination="测试",
            days=1,
            pool=pool,
        )

    # 兜底：按 rating 降序
    assert result["must_ids"] == ["1", "2", "3"]
    assert result["optional_ids"] == ["4", "5"]
