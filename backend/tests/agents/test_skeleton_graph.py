from unittest.mock import patch, AsyncMock

import pytest

from app.agents.langgraph_agent.graph import create_planning_graph
from app.database import init_db
from app.services import trip_draft_service
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton


@pytest.mark.asyncio
async def test_skeleton_graph_runs_and_persists_draft():
    await init_db()

    request = TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )

    initial_state = {
        "request": request,
        "user_id": "test_user",
        "user_selected_attractions": [
            {"name": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
            {"name": "颐和园", "location": {"longitude": 116.273, "latitude": 39.999}},
        ],
        "user_day_assignments": None,
        "user_preferences": None,
        "attractions_info": "",
        "weather_info": "",
        "hotels_info": "",
        "food_info": "",
        "cluster_info": "",
        "route_info": "",
        "trip_plan": None,
        "errors": [],
        "messages": [],
        "extracted_preferences": None,
        "macro_plan": None,
        "day_plans": [],
        "global_narrative": None,
        "clusters_data": [],
        "hotels_by_day": [],
        "selected_pois": [],
        "selected_hotels": [],
        "aigohotel_raw_results": "",
        "dining_pool": [],
        "draft_id": None,
    }

    with patch(
        "app.agents.langgraph_agent.nodes.draft.trip_draft_service.create_draft",
        new=AsyncMock(return_value="draft_xyz"),
    ), patch(
        "app.agents.langgraph_agent.nodes.food._search_dining_category",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.agents.langgraph_agent.graph.search_hotels_by_day_node",
        new=AsyncMock(return_value={"hotels_by_day": [[], []], "hotels_info": ""}),
    ), patch(
        "app.agents.langgraph_agent.graph.macro_planner_node",
        new=AsyncMock(return_value={"macro_plan": MacroPlan(
            city="北京", total_days=2,
            days=[
                DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["故宫"]),
                DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["颐和园"]),
            ],
        )}),
    ), patch(
        "app.agents.langgraph_agent.graph.load_user_preferences_node",
        new=AsyncMock(return_value={"user_preferences": None}),
    ):
        app = create_planning_graph()
        final = await app.ainvoke(initial_state)

    assert final["draft_id"] == "draft_xyz"
    assert final.get("macro_plan") is not None
