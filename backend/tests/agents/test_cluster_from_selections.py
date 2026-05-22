import pytest

from app.agents.langgraph_agent.nodes.cluster import cluster_from_selections_node
from app.models.schemas import TripRequest


def _make_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


@pytest.mark.asyncio
async def test_visit_minutes_propagated_to_attractions_info():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {
                "name": "故宫",
                "description": "皇家宫殿",
                "category": "博物馆",
                "address": "东城区",
                "location": {"longitude": 116.397, "latitude": 39.916},
                "visit_minutes": 150,
            },
            {
                "name": "颐和园",
                "category": "公园",
                "location": {"longitude": 116.273, "latitude": 39.999},
                # 无 visit_minutes
            },
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    info = result["attractions_info"]
    assert "预计游玩: 150min" in info
    # 没有 visit_minutes 的不应出现该字段
    assert info.count("预计游玩:") == 1


@pytest.mark.asyncio
async def test_no_visit_minutes_does_not_break():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    assert "预计游玩:" not in result["attractions_info"]
