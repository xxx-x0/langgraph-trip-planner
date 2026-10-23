"""Current intent and parallel error behavior across the running graphs."""
import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from app.agents.langgraph_agent import graph
from app.database import init_db
from app.models.schemas import TripRequest, UserPreference, MacroPlan, DaySkeleton
from app.services import preferences_service, trip_draft_service


def request():
    return TripRequest(city="北京", start_date="2026-10-15", end_date="2026-10-15",
                       travel_days=1, transportation="公共交通", accommodation="经济型酒店",
                       preferences=["户外徒步"], food_preference="本地特色")


@pytest.mark.asyncio
@pytest.mark.parametrize("interests", [["户外徒步"], []])
async def test_conflicting_history_does_not_enter_skeleton_prompt_or_saved_request(monkeypatch, interests):
    await init_db()
    user = "current-trip-" + uuid4().hex
    old = UserPreference(user_id=user, preferred_hotel_types=["HISTORICAL_LUXURY_ONLY"],
                         preferred_cuisines=["HISTORICAL_CUISINE_ONLY"],
                         preferred_attraction_categories=["HISTORICAL_MUSEUM_ONLY"])
    await preferences_service.save_preferences(user, old, source="explicit", confidence=1)
    read_history = AsyncMock(side_effect=AssertionError("planning must not load historical preferences"))
    monkeypatch.setattr(preferences_service, "load_preferences", read_history)
    monkeypatch.setattr(graph, "search_hotels_by_day_node", AsyncMock(return_value={"hotels_by_day": [[]]}))
    monkeypatch.setattr(graph, "search_dining_pool_node", AsyncMock(return_value={"dining_pool": [{}]}))

    from app.agents.langgraph_agent.nodes import generate
    macro = MacroPlan(city="北京", total_days=1, days=[DaySkeleton(
        day_index=0, date="2026-10-15", attraction_names=["新探索山地公园"])])
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content=macro.model_dump_json())
    monkeypatch.setattr(generate, "get_llm", lambda: llm)
    monkeypatch.setattr(generate, "is_structured_output_supported", lambda: False)
    planner = graph.LangGraphTripPlanner()
    current = request()
    current.preferences = interests
    selected = [{"name": "新探索山地公园", "location": {"longitude": 116.4, "latitude": 39.9},
                 "visit_minutes": 120}]
    state = planner._build_planning_state(current, selected, user_id=user)
    # Stale or caller-supplied history is not a graph input channel either.
    state["user_preferences"] = old
    result = await planner.planning_app.ainvoke(state)
    read_history.assert_not_awaited()
    assert "user_preferences" not in result
    messages = llm.ainvoke.call_args.args[0]
    prompt = "\n".join(m.content for m in messages)
    assert "HISTORICAL_" not in prompt
    assert "新探索山地公园" in prompt and "经济型酒店" in prompt
    saved = await trip_draft_service.get_draft(result["draft_id"])
    payload = json.loads(saved.request_json)
    assert payload["preferences"] == interests
    assert payload["accommodation"] == "经济型酒店"
    assert json.loads(saved.selected_attractions_json)[0]["name"] == "新探索山地公园"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["discovery", "full_plan"])
async def test_parallel_failures_keep_both_errors_instead_of_invalid_update(monkeypatch, kind):
    attraction_error = {"errors": ["attraction service unavailable"]}
    weather_error = {"errors": ["weather service unavailable"]}
    if kind == "discovery":
        monkeypatch.setattr(graph, "search_attractions_discovery_node", AsyncMock(return_value=attraction_error))
        monkeypatch.setattr(graph, "search_weather_node", AsyncMock(return_value=weather_error))
        app = graph.create_discovery_graph()
    else:
        monkeypatch.setattr(graph, "search_attractions_node", AsyncMock(return_value=attraction_error))
        monkeypatch.setattr(graph, "search_weather_node", AsyncMock(return_value=weather_error))
        for name in ["cluster_attractions_node", "search_hotels_by_day_node", "search_food_node",
                     "plan_route_node", "reduce_assemble_node", "global_synthesizer_node",
                     "extract_preferences_node", "save_preferences_node"]:
            monkeypatch.setattr(graph, name, AsyncMock(return_value={}))
        macro = MacroPlan(city="北京", total_days=1, days=[DaySkeleton(
            day_index=0, date="2026-10-15", attraction_names=["公园"])])
        monkeypatch.setattr(graph, "macro_planner_node", AsyncMock(return_value={"macro_plan": macro}))
        monkeypatch.setattr(graph, "day_plan_subgraph_node", AsyncMock(return_value={"day_plans": [{"day_index": 0}]}))
        app = graph.create_trip_planner_graph()
    result = await app.ainvoke({"request": request(), "errors": []})
    assert sorted(result["errors"]) == ["attraction service unavailable", "weather service unavailable"]


def test_stream_updates_replace_selections_and_keep_reduced_errors():
    initial = {"selected_pois": [{"name": "old"}], "errors": ["first"], "day_plans": []}
    streamed = dict(initial)
    graph._merge_stream_update(streamed, {"selected_pois": [{"name": "new"}], "errors": ["second"]})
    graph._merge_stream_update(streamed, {"day_plans": [{"day_index": 0}]})
    graph._merge_stream_update(streamed, {"day_plans": [{"day_index": 1}]})
    assert streamed["selected_pois"] == [{"name": "new"}]
    assert streamed["errors"] == ["first", "second"]
    assert [d["day_index"] for d in streamed["day_plans"]] == [0, 1]
    assert initial["errors"] == ["first"] and initial["day_plans"] == []


@pytest.mark.asyncio
async def test_skeleton_progress_keeps_forward_when_hotels_finish_before_dining(monkeypatch):
    hotel_done = asyncio.Event()
    async def hotels(state):
        hotel_done.set()
        return {"hotels_by_day": [[]]}
    async def dining(state):
        await hotel_done.wait()
        await asyncio.sleep(0.01)
        return {"dining_pool": [{}]}
    monkeypatch.setattr(graph, "search_hotels_by_day_node", hotels)
    monkeypatch.setattr(graph, "search_dining_pool_node", dining)
    macro = MacroPlan(city="北京", total_days=1, days=[DaySkeleton(
        day_index=0, date="2026-10-15", attraction_names=["公园"])])
    monkeypatch.setattr(graph, "macro_planner_node", AsyncMock(return_value={"macro_plan": macro}))
    monkeypatch.setattr(graph, "save_draft_node", AsyncMock(return_value={"draft_id": "progress-test"}))
    planner = graph.LangGraphTripPlanner()
    monkeypatch.setattr(planner, "_pre_init_services", AsyncMock())
    events = [e async for e in planner.plan_from_selections_stream(request(), [
        {"name": "公园", "location": {"longitude": 116.4, "latitude": 39.9}, "visit_minutes": 120}])]
    nodes = [e["node"] for e in events if e["type"] == "node_complete"]
    assert nodes.index("search_hotels_by_day") < nodes.index("search_dining_pool")
    assert len(nodes) == 5
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress)
    assert events[-1]["draft_id"] == "progress-test"
