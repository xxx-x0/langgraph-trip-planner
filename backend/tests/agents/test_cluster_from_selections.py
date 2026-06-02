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


from app.agents.langgraph_agent.nodes.cluster import _selection_to_cluster_dict


def test_selection_to_cluster_dict_preserves_fields():
    attr = {
        "name": "故宫", "description": "皇家宫殿", "category": "博物馆",
        "address": "东城区景山前街4号", "rating": 4.8, "ticket_price": "60",
        "image_url": "http://img/gugong.jpg", "poi_id": "B000A8UIN8",
        "location": {"longitude": 116.397, "latitude": 39.916},
        "visit_minutes": 180,
    }
    d = _selection_to_cluster_dict(attr)
    assert d["name"] == "故宫"
    assert d["longitude"] == 116.397
    assert d["latitude"] == 39.916
    assert d["address"] == "东城区景山前街4号"
    assert d["category"] == "博物馆"
    assert d["rating"] == 4.8
    assert d["ticket_price"] == "60"
    assert d["description"] == "皇家宫殿"
    assert d["poi_id"] == "B000A8UIN8"
    assert d["visit_minutes"] == 180
    assert d["image_url"] == "http://img/gugong.jpg"


def test_selection_to_cluster_dict_missing_location_defaults_zero():
    d = _selection_to_cluster_dict({"name": "X"})
    assert d["name"] == "X"
    assert d["longitude"] == 0
    assert d["latitude"] == 0
    assert d["address"] == ""


@pytest.mark.asyncio
async def test_clusters_data_preserves_rich_fields():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "address": "东城区", "rating": 4.8,
             "ticket_price": "60", "category": "博物馆", "description": "皇家宫殿",
             "poi_id": "P1", "image_url": "http://img/1.jpg",
             "location": {"longitude": 116.397, "latitude": 39.916},
             "visit_minutes": 180},
            {"name": "颐和园", "address": "海淀区", "rating": 4.7,
             "ticket_price": "30", "category": "公园", "description": "皇家园林",
             "poi_id": "P2", "image_url": "http://img/2.jpg",
             "location": {"longitude": 116.273, "latitude": 39.999},
             "visit_minutes": 150},
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    flat = [a for cluster in result["clusters_data"] for a in cluster]
    by_name = {a["name"]: a for a in flat}
    assert by_name["故宫"]["address"] == "东城区"
    assert by_name["故宫"]["rating"] == 4.8
    assert by_name["故宫"]["ticket_price"] == "60"
    assert by_name["故宫"]["category"] == "博物馆"
    assert by_name["故宫"]["description"] == "皇家宫殿"
    assert by_name["故宫"]["poi_id"] == "P1"
    assert by_name["故宫"]["visit_minutes"] == 180
    assert by_name["故宫"]["image_url"] == "http://img/1.jpg"
