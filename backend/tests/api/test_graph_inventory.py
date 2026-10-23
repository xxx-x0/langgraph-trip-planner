from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.api.routes import trip_lg


@pytest.mark.asyncio
async def test_health_reports_running_graphs_and_disabled_implicit_history(monkeypatch):
    monkeypatch.setattr(trip_lg, "get_langchain_amap_service", lambda: SimpleNamespace(health_check=AsyncMock(return_value=True)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/trip/health")
    assert response.status_code == 200
    result = response.json()
    assert result["features"]["implicit_preference_loading"] is False
    assert result["features"]["preference_memory"] is False
    assert set(result["graphs"]) == {"full_plan", "discovery", "draft_skeleton"}
    assert "search_hotels_by_day" in result["graph_nodes"]
    assert "search_hotel" not in result["graph_nodes"]
    assert set(result["graphs"]["draft_skeleton"]) == {
        "cluster_from_selections", "search_dining_pool", "search_hotels_by_day", "macro_planner", "save_draft"}
    assert all("load_user_preferences" not in nodes for nodes in result["graphs"].values())
