import pytest

from app.agents.langgraph_agent.utils.route import (
    _parse_amap_result,
    compute_route_segments,
)


class _FakeTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke(self, arguments):
        self.calls.append(arguments)
        return self.result


class _FakeAmapService:
    def __init__(self, tools):
        self.tools = tools
        self.requested = []

    async def get_tool(self, name):
        self.requested.append(name)
        return self.tools.get(name)


def _waypoints(distance_delta=0.001):
    return [
        {"name": "酒店", "longitude": 106.575533, "latitude": 29.557208},
        {
            "name": "解放碑",
            "longitude": 106.575533 + distance_delta,
            "latitude": 29.557208,
        },
    ]


def test_parse_empty_transit_result_does_not_leak_raw_payload():
    parsed = _parse_amap_result(
        {"origin": "106,29", "destination": "106.1,29.1", "transits": []},
        "maps_direction_transit_integrated",
    )

    assert parsed == {"distance": "", "duration": "", "detail": ""}


@pytest.mark.asyncio
async def test_nearby_waypoints_prefer_walking_over_transit(monkeypatch):
    walking = _FakeTool({
        "paths": [{
            "distance": "160",
            "duration": "120",
            "steps": [{"instruction": "沿步行街步行"}],
        }],
    })
    transit = _FakeTool({"transits": []})
    service = _FakeAmapService({
        "maps_direction_walking": walking,
        "maps_direction_transit_integrated": transit,
    })
    monkeypatch.setattr(
        "app.agents.langgraph_agent.utils.route.get_langchain_amap_service",
        lambda: service,
    )

    segments = await compute_route_segments(_waypoints(), "公共交通", "重庆")

    assert segments[0]["mode"] == "步行"
    assert segments[0]["duration"] == "2分钟"
    assert service.requested[0] == "maps_direction_walking"
    assert walking.calls
    assert not transit.calls


@pytest.mark.asyncio
async def test_failed_transit_candidate_falls_back_to_readable_estimate(monkeypatch):
    service = _FakeAmapService({
        "maps_direction_transit_integrated": _FakeTool({"transits": []}),
    })
    monkeypatch.setattr(
        "app.agents.langgraph_agent.utils.route.get_langchain_amap_service",
        lambda: service,
    )

    segments = await compute_route_segments(_waypoints(0.08), "公共交通", "重庆")

    assert segments[0]["distance"]
    assert segments[0]["duration"]
    assert segments[0]["detail"].startswith("约")
    assert "transits" not in segments[0]["detail"]
