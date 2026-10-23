from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.food import search_dining_pool_node
from app.models.schemas import DiningCategory, TripRequest


def _make_state(travel_days=2, clusters=None, attractions_info=""):
    return {
        "request": TripRequest(
            city="北京", start_date="2026-06-01", end_date="2026-06-02",
            travel_days=travel_days, transportation="公共交通",
            accommodation="经济型酒店",
        ),
        "clusters_data": clusters or [],
        "attractions_info": attractions_info,
    }


@pytest.mark.asyncio
async def test_returns_one_pool_per_day():
    state = _make_state(
        travel_days=2,
        clusters=[
            [{"name": "故宫", "longitude": 116.397, "latitude": 39.916}],
            [{"name": "颐和园", "longitude": 116.273, "latitude": 39.999}],
        ],
    )

    fake_poi = AsyncMock(return_value=[
        {"name": "某餐厅", "address": "...", "longitude": 116.4, "latitude": 39.9,
         "rating": 4.5, "avg_cost": 80}
    ])
    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=fake_poi):
        result = await search_dining_pool_node(state)

    pools = result["dining_pool"]
    assert len(pools) == 2
    for p in pools:
        assert isinstance(p, dict)
        assert {"main", "snack", "dessert", "cafe", "late_night"}.issubset(p.keys())


@pytest.mark.asyncio
async def test_failure_in_one_category_does_not_break_others():
    """某一类失败应返回 []，不影响其他类别"""
    state = _make_state(
        travel_days=1,
        clusters=[[{"name": "天坛", "longitude": 116.41, "latitude": 39.88}]],
    )

    async def fake_search(category, center, city):
        if category == DiningCategory.LATE_NIGHT:
            raise RuntimeError("amap 暂时挂了")
        return [{"name": f"{category.value}餐厅", "longitude": 116.41,
                 "latitude": 39.88, "rating": 4.0}]

    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=fake_search):
        result = await search_dining_pool_node(state)

    pool = result["dining_pool"][0]
    assert pool["main"] and pool["snack"] and pool["dessert"] and pool["cafe"]
    assert pool["late_night"] == []


@pytest.mark.asyncio
async def test_no_coordinates_falls_back_to_city_search():
    """当日聚类全部无坐标时，应走城市级文本搜索（不带 location）"""
    state = _make_state(
        travel_days=1,
        clusters=[[{"name": "未知景点", "longitude": 0, "latitude": 0}]],
    )

    called_with = []

    async def capture(category, center, city):
        called_with.append((category.value, center, city))
        return []

    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=capture):
        await search_dining_pool_node(state)

    for _, center, city in called_with:
        assert center is None
        assert city == "北京"


@pytest.mark.asyncio
async def test_detail_batch_can_recover_after_previous_batch_trips_circuit():
    from app.agents.langgraph_agent.nodes.food import _enrich_pois_with_detail
    failed=[{'name':str(i),'poi_id':str(i)} for i in range(3)]
    healthy=[{'name':'recovered','poi_id':'recovered'}]
    response={'id':'recovered','name':'recovered','location':'116.4,39.9','cost':'68','open_time':'11:00-23:00'}
    with patch('app.agents.langgraph_agent.nodes.food._invoke_tool_with_retry',
               new=AsyncMock(side_effect=[ConnectionError('down')]*3+[response])) as call, patch(
                   'app.agents.langgraph_agent.nodes.food.asyncio.sleep',new=AsyncMock()):
        await _enrich_pois_with_detail(failed,object())
        await _enrich_pois_with_detail(healthy,object())
    assert call.await_count==4
    assert healthy[0]['longitude']==116.4 and healthy[0]['avg_cost']==68
