"""Task 3.1 回归测试：cluster_attractions_node 接入时长均衡。

确保主流程聚类节点在生成每日聚类时调用 _rebalance_by_duration，使得
每天的总游玩时长不超过 480 分钟（estimate_durations_batch 提供时长）。
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.cluster import cluster_attractions_node
from app.models.schemas import TripRequest


def _make_request(travel_days: int = 2) -> TripRequest:
    return TripRequest(
        city="北京",
        start_date="2026-06-01",
        end_date="2026-06-02" if travel_days == 2 else "2026-06-03",
        travel_days=travel_days,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=[],
        free_text_input="",
    )


# 复用 test_geo_rebalance.test_moves_farthest_attraction_when_over_limit 的几何布局：
# D 离 day0 的 (A,B,C) 质心很远，但与 day1 的 E 距离更近，
# 使 _rebalance_by_duration 能把 D 搬到 day1。
_ATTRACTIONS = [
    {"name": "A", "longitude": 116.40, "latitude": 39.90},
    {"name": "B", "longitude": 116.41, "latitude": 39.91},
    {"name": "C", "longitude": 116.40, "latitude": 39.92},
    {"name": "D", "longitude": 116.80, "latitude": 40.30},
    {"name": "E", "longitude": 116.85, "latitude": 40.35},
]
_INITIAL_CLUSTERS = [
    # day0 故意拥挤：A/B/C 紧密 + D（D 离 day0 质心远但靠近 E）
    [
        {"name": "A", "longitude": 116.40, "latitude": 39.90},
        {"name": "B", "longitude": 116.41, "latitude": 39.91},
        {"name": "C", "longitude": 116.40, "latitude": 39.92},
        {"name": "D", "longitude": 116.80, "latitude": 40.30},
    ],
    [
        {"name": "E", "longitude": 116.85, "latitude": 40.35},
    ],
]


@pytest.mark.asyncio
async def test_cluster_attractions_balances_long_days():
    """初始聚类把 ABCD 全放到 day0（共 540 分钟，超 480），
    接入 _rebalance_by_duration 后，D 应被搬到 day1（与 E 同组），
    使每天总时长 ≤ 480。

    注：我们通过 mock _cluster_attractions_by_proximity 注入一个
    已知的不均衡聚类，专注验证 cluster_attractions_node 是否真的把
    durations 注入并调用了 rebalance。
    """
    durations = {"A": 150, "B": 150, "C": 120, "D": 120, "E": 60}

    # 模拟 amap 服务不可用，让节点走 haversine 路径
    fake_service = AsyncMock()
    fake_service.get_tool = AsyncMock(return_value=None)

    with patch(
        "app.agents.langgraph_agent.nodes.cluster._extract_coordinates_regex",
        return_value=_ATTRACTIONS,
    ), patch(
        "app.agents.langgraph_agent.nodes.cluster._cluster_attractions_by_proximity",
        return_value=[list(c) for c in _INITIAL_CLUSTERS],
    ), patch(
        "app.agents.langgraph_agent.nodes.cluster.analyze_free_text",
        new=AsyncMock(return_value={"attractions": []}),
    ), patch(
        "app.agents.langgraph_agent.nodes.cluster.get_langchain_amap_service",
        return_value=fake_service,
    ), patch(
        "app.agents.langgraph_agent.nodes.cluster.estimate_durations_batch",
        new=AsyncMock(return_value=durations),
    ):
        result = await cluster_attractions_node({
            "request": _make_request(travel_days=2),
            "attractions_info": "<mocked>",
        })

    clusters = result.get("clusters_data")
    assert clusters is not None, "cluster_attractions_node 应返回 clusters_data"
    assert len(clusters) == 2, f"应有 2 天聚类，实际 {len(clusters)}"

    for day_idx, day in enumerate(clusters):
        total = sum(durations.get(a["name"], 0) for a in day)
        assert total <= 480, (
            f"第 {day_idx + 1} 天总时长 {total} > 480 分钟，"
            f"_rebalance_by_duration 未生效，景点: {[a['name'] for a in day]}"
        )

    # 强信号：D 应被 rebalance 搬到包含 E 的那天
    day_with_e = next(c for c in clusters if any(a["name"] == "E" for a in c))
    assert any(a["name"] == "D" for a in day_with_e), (
        f"D 应被 _rebalance_by_duration 搬到包含 E 的那天；实际 clusters: "
        f"{[[a['name'] for a in c] for c in clusters]}"
    )
