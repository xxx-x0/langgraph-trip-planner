from unittest.mock import AsyncMock, patch

import pytest

from app.agents.langgraph_agent.nodes.food import search_dining_pool_node
from app.models.schemas import DiningCategory, TripRequest


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

    async def fake_search(category, center, city, **kwargs):
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

    async def capture(category, center, city, **kwargs):
        called_with.append((category.value, center, city))
        return []

    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category",
               new=capture):
        await search_dining_pool_node(state)

    for _, center, city in called_with:
        assert center is None
        assert city == "北京"


@pytest.mark.asyncio
async def test_dining_search_details_supply_missing_meal_coordinates():
    search = AsyncMock(return_value=[{"name":"苏帮菜餐厅","poi_id":"restaurant-1"}])
    tool = AsyncMock()
    tool.ainvoke.return_value = [{"type":"text","text":'{"id":"restaurant-1","name":"苏帮菜餐厅","location":"116.4,39.9","cost":"68.00","rating":"4.6","open_time":"11:00-23:00"}'}]
    service = AsyncMock()
    service.get_tool.return_value = tool
    with patch("app.agents.langgraph_agent.nodes.food._search_dining_category", search), patch(
        "app.agents.langgraph_agent.nodes.food.get_langchain_amap_service", return_value=service
    ), patch("app.agents.langgraph_agent.nodes.food.asyncio.sleep", new=AsyncMock()):
        result = await search_dining_pool_node(_make_state())
    for pool in result["dining_pool"]:
        for category in DiningCategory:
            assert pool[category.value][0]["location"] == {"longitude":116.4,"latitude":39.9}
            assert pool[category.value][0]["avg_cost"] == 68
            assert pool[category.value][0]["open_hours"] == "11:00-23:00"


@pytest.mark.asyncio
async def test_budget_search_broadens_cuisine_when_all_known_prices_exceed_cap():
    from app.agents.langgraph_agent.nodes.food import search_dining_for_day
    from app.services.recommendations import cluster_attractions
    request=_make_state()['request'];request.meal_budget_per_person=50
    async def search(category, center, city, food_preference=''):
        if category != DiningCategory.MAIN:return []
        return [{'name':'日常饭馆' if food_preference=='快餐' else '特色大餐',
                 'longitude':116.4,'latitude':39.9,'avg_cost':30 if food_preference=='快餐' else 150,
                 'rating':4,'open_hours':'10:00-22:00'}]
    with patch('app.agents.langgraph_agent.nodes.food._search_dining_category',side_effect=search) as calls:
        result=await search_dining_for_day(request,cluster_attractions([{'name':'景点','longitude':116.4,'latitude':39.9}]))
    assert any(c['name']=='日常饭馆' and c['avg_cost']==30 for c in result['main'])
    assert any(c.kwargs.get('food_preference')=='快餐' for c in calls.call_args_list)


@pytest.mark.asyncio
async def test_sparse_search_reserves_detail_calls_for_budget_alternatives():
    from app.agents.langgraph_agent.nodes.food import search_dining_for_day
    request=_make_state()['request'];request.meal_budget_per_person=50
    async def search(category, center, city, food_preference=''):
        if category!=DiningCategory.MAIN:return []
        prefix='简餐' if food_preference=='快餐' else '大餐'
        return [{'name':prefix+str(i),'poi_id':prefix+str(i)} for i in range(10)]
    async def enrich(pois,*args,**kwargs):
        for p in pois:p.update(longitude=116.4,latitude=39.9,avg_cost=25 if p['name'].startswith('简餐') else 150,open_hours='10:00-22:00')
    service=AsyncMock()
    with patch('app.agents.langgraph_agent.nodes.food._search_dining_category',side_effect=search),patch(
        'app.agents.langgraph_agent.nodes.food._enrich_pois_with_detail',side_effect=enrich),patch(
        'app.agents.langgraph_agent.nodes.food.get_langchain_amap_service',return_value=service):
        result=await search_dining_for_day(request,[])
    assert any(c['avg_cost']==25 for c in result['main'])
    assert any(c['avg_cost']==150 for c in result['main'])


@pytest.mark.asyncio
async def test_candidates_without_poi_identity_do_not_load_an_unusable_detail_tool():
    from app.agents.langgraph_agent.nodes.food import search_dining_for_day
    service=AsyncMock();service.get_tool.side_effect=AssertionError('no identity to query')
    with patch('app.agents.langgraph_agent.nodes.food._search_dining_category',new=AsyncMock(return_value=[{'name':'已知候选','longitude':116.4,'latitude':39.9,'avg_cost':40}])), patch('app.agents.langgraph_agent.nodes.food.get_langchain_amap_service',return_value=service):
        pool=await search_dining_for_day(_make_state()['request'],[])
    assert pool['main'][0]['avg_cost']==40
    assert pool['main'][0]['open_hours'] is None
    service.get_tool.assert_not_called()
