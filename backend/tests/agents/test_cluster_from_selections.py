import pytest
from unittest.mock import AsyncMock

from app.agents.langgraph_agent.nodes.cluster import cluster_from_selections_node
from app.models.schemas import TripRequest
from app.services.attractions_cache_service import CachedAttraction


@pytest.fixture(autouse=True)
def duration_estimator(monkeypatch):
    estimator=AsyncMock(side_effect=lambda items: {a['name']:90 for a in items})
    monkeypatch.setattr('app.agents.langgraph_agent.nodes.cluster.estimate_durations_batch',estimator)
    return estimator


def _make_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


@pytest.mark.asyncio
async def test_estimates_only_missing_durations_and_preserves_existing_minutes(duration_estimator):
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
    assert "预计游玩: 90min" in info
    assert [a['name'] for a in duration_estimator.call_args.args[0]] == ['颐和园']
    assert [a['visit_minutes'] for a in result['user_selected_attractions']] == [150,90]
    assert 'visit_minutes' not in state['user_selected_attractions'][1]


@pytest.mark.asyncio
async def test_automatic_grouping_estimates_duration_without_frontend_preview():
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
        ],
        "user_day_assignments": None,
    }
    result = await cluster_from_selections_node(state)
    assert "预计游玩: 90min" in result["attractions_info"]


from app.agents.langgraph_agent.nodes.cluster import _selection_to_cluster_dict


def test_selection_to_cluster_dict_preserves_fields():
    attr = {
        "name": "故宫", "description": "皇家宫殿", "category": "博物馆",
        "address": "东城区景山前街4号", "rating": 4.8, "ticket_price": "60",
        "image_url": "http://img/gugong.jpg", "poi_id": "B000A8UIN8",
        "location": {"longitude": 116.397, "latitude": 39.916},
        "visit_minutes": 180,
        "open_hours": "08:30-17:00",
        "tel": "010-85007421",
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
    assert d["open_hours"] == "08:30-17:00"
    assert d["tel"] == "010-85007421"


def test_selection_to_cluster_dict_missing_location_defaults_zero():
    d = _selection_to_cluster_dict({"name": "X"})
    assert d["name"] == "X"
    assert d["longitude"] == 0
    assert d["latitude"] == 0
    assert d["address"] == ""


@pytest.mark.asyncio
async def test_clusters_data_preserves_rich_fields(duration_estimator):
    state = {
        "request": _make_request(),
        "user_selected_attractions": [
            {"name": "故宫", "address": "东城区", "rating": 4.8,
             "ticket_price": "60", "category": "博物馆", "description": "皇家宫殿",
             "poi_id": "P1", "image_url": "http://img/1.jpg",
             "location": {"longitude": 116.397, "latitude": 39.916},
             "visit_minutes": 180, "open_hours": "08:30-17:00", "tel": "010-85007421"},
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
    assert by_name["故宫"]["open_hours"] == "08:30-17:00"
    assert by_name["故宫"]["tel"] == "010-85007421"
    duration_estimator.assert_not_awaited()


@pytest.mark.asyncio
async def test_cluster_from_selections_backfills_missing_rich_fields_from_cache(monkeypatch, duration_estimator):
    class FakeCacheService:
        async def find_by_name(self, city, name):
            assert city == "北京"
            assert name == "故宫"
            return CachedAttraction(
                name="故宫",
                address="东城区景山前街4号",
                category="历史文化",
                rating=4.8,
                image_url="http://img/gugong.jpg",
                open_hours="08:30-17:00",
                tel="010-85007421",
                poi_id="P1",
            )

    monkeypatch.setattr(
        "app.agents.langgraph_agent.nodes.cluster.get_attractions_cache_service",
        lambda: FakeCacheService(),
    )

    selection = {
        "name": "故宫",
        "address": "东城区",
        "category": "景点",
        "location": {"longitude": 116.397, "latitude": 39.916},
    }
    state = {
        "request": _make_request(),
        "user_selected_attractions": [dict(selection)],
        "user_day_assignments": [[dict(selection)]],
    }

    result = await cluster_from_selections_node(state)

    attr = result["clusters_data"][0][0]
    assert attr["rating"] == 4.8
    assert attr["image_url"] == "http://img/gugong.jpg"
    assert attr["open_hours"] == "08:30-17:00"
    assert attr["tel"] == "010-85007421"
    duration_estimator.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('located', [False, True])
async def test_automatic_grouping_keeps_selected_places_with_missing_coordinates(located):
    selected=[{'name':'待核对坐标的公园','visit_minutes':60}]
    if located:
        selected.append({'name':'故宫','visit_minutes':150,'location':{'longitude':116.397,'latitude':39.916}})
    result=await cluster_from_selections_node({'request':_make_request(),'user_selected_attractions':selected,'user_day_assignments':None})
    flat=[a for day in result['clusters_data'] for a in day]
    assert {a['name'] for a in flat}=={a['name'] for a in selected}
    unknown=next(a for a in flat if a['name']=='待核对坐标的公园')
    assert unknown['longitude']==0 and unknown['latitude']==0
    assert len(result['clusters_data'])==2


@pytest.mark.asyncio
async def test_automatic_grouping_respects_partial_days_and_retains_overflow_catalog():
    data=_make_request().model_dump()
    data['journey']={'origin_city':'上海','return_city':'上海','destination_timezone':'Asia/Shanghai',
        'planning':{'arrival_policy':'time_window','departure_policy':'time_window','ready_at':'2026-06-01T21:30','leave_by':'2026-06-02T10:00'}}
    selected=[{'name':f'公园{i}','visit_minutes':90,'location':{'longitude':116.39+i*.01,'latitude':39.91}} for i in range(3)]
    result=await cluster_from_selections_node({'request':TripRequest(**data),'user_selected_attractions':selected,'user_day_assignments':None})
    assert result['clusters_data'][0]==[]
    assert len(result['clusters_data'][1])==1
    assert {a['name'] for a in result['user_selected_attractions']}=={a['name'] for a in selected}
