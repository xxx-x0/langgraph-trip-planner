"""Combination regressions against persisted drafts and actual history reads."""
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database import init_db
from app.models.schemas import TripRequest, MacroPlan, DaySkeleton, DiningPoolDay
from app.services import trip_draft_service


@pytest_asyncio.fixture
async def editable_day():
    await init_db()
    request = TripRequest(city="北京", start_date="2026-10-20", end_date="2026-10-20",
                          travel_days=1, transportation="步行", accommodation="经济型酒店")
    draft_id = await trip_draft_service.create_draft(
        user_id="default", request=request, selected_attractions=[],
        macro_plan=MacroPlan(city="北京", total_days=1, days=[
            DaySkeleton(day_index=0, date=request.start_date, attraction_names=list("ABCD"))
        ]),
        clusters_data=[[{"name": n, "ticket_price": 20} for n in "ABCD"]],
        hotels_by_day=[[]], dining_pool=[DiningPoolDay().model_dump(mode="json")],
        weather_info=[],
    )
    with patch("app.api.routes.trip_draft.compute_day_route", new=AsyncMock(return_value=[])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            url = f"/api/trip/draft/{draft_id}/day/0"
            response = await client.post(url + "/recompute", json={"locked_attraction_names": ["B"]})
            assert response.status_code == 200
            yield client, draft_id, url


@pytest.mark.asyncio
async def test_manual_lock_delete_compaction_restore_and_refresh(editable_day):
    client, draft_id, url = editable_day
    for edit in [{"removed_attraction_names": ["B"]},
                 {"attractions_order": ["B", "A", "C", "D"]}]:
        response = await client.post(url + "/recompute", json=edit)
        assert response.status_code == 409
    # Removing A naturally compacts B to slot zero without unlocking it.
    response = await client.post(url + "/recompute", json={"removed_attraction_names": ["A"]})
    assert [a["name"] for a in response.json()["day_detail"]["attractions"]] == list("BCD")
    assert response.json()["day_detail"]["day_budget"]["total_attractions"] == 60
    response = await client.post(url + "/recompute", json={"attractions_order": list("BDCA")})
    assert [a["name"] for a in response.json()["day_detail"]["attractions"]] == list("BDC")
    assert response.json()["day_detail"]["removed_attraction_names"] == ["A"]
    response = await client.post(url + "/recompute", json={"removed_attraction_names": []})
    detail = response.json()["day_detail"]
    assert [a["name"] for a in detail["attractions"]] == list("BDCA")
    assert detail["locked_attraction_names"] == ["B"]
    refreshed = await client.get(f"/api/trip/draft/{draft_id}")
    assert refreshed.json()["days_detail"][0] == detail
    # Unlock, move and remove; later partial edits must preserve the explicit deletion.
    assert (await client.post(url + "/recompute", json={"locked_attraction_names": []})).status_code == 200
    response = await client.post(url + "/recompute", json={"attractions_order": list("DCAB"), "removed_attraction_names": ["B"]})
    assert [a["name"] for a in response.json()["day_detail"]["attractions"]] == list("DCA")
    response = await client.post(url + "/recompute", json={"day_start_time": "09:45"})
    assert response.json()["day_detail"]["removed_attraction_names"] == ["B"]


@pytest.mark.asyncio
async def test_ai_cannot_move_locks_or_restore_deleted_attractions(editable_day):
    client, draft_id, url = editable_day
    await client.post(url + "/recompute", json={"removed_attraction_names": ["A"], "day_start_time": "10:00"})
    llm_response = type("Response", (), {"content": json.dumps({
        "attractions_order": list("ADCBX"), "meals": [{"name": "午餐", "insert_after": "A"}]
    })})()
    with patch("app.api.routes.trip_draft.get_llm"), patch(
        "app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=llm_response)
    ):
        response = await client.post(url + "/ai-rearrange", json={})
    assert response.status_code == 200
    detail = response.json()["day_detail"]
    assert [a["name"] for a in detail["attractions"]] == list("BDC")
    assert detail["locked_attraction_names"] == ["B"]
    assert detail["removed_attraction_names"] == ["A"]
    assert detail["day_start_time"] == "10:00"
    assert "A" not in [item["ref_name"] for item in detail["timeline_order"]]
    refreshed = await client.get(f"/api/trip/draft/{draft_id}")
    assert refreshed.json()["days_detail"][0] == detail


@pytest.mark.asyncio
@pytest.mark.parametrize("locked, expected", [
    (["A", "C"], list("ADCB")), (list("ABCD"), list("ABCD")), ([], list("DCBA")),
])
async def test_ai_respects_multiple_all_and_no_locks(editable_day, locked, expected):
    client, _, url = editable_day
    await client.post(url + "/recompute", json={"locked_attraction_names": locked})
    llm_response = type("Response", (), {"content": json.dumps({"attractions_order": list("DCBA")})})()
    with patch("app.api.routes.trip_draft.get_llm"), patch(
        "app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=llm_response)
    ):
        detail = (await client.post(url + "/ai-rearrange", json={})).json()["day_detail"]
    assert [a["name"] for a in detail["attractions"]] == expected
    assert detail["locked_attraction_names"] == locked


@pytest.mark.asyncio
async def test_force_assemble_preserves_saved_edits_and_meal_anchor(editable_day):
    client, _, url = editable_day
    edit = {"removed_attraction_names": ["A"], "day_start_time": "09:45",
            "meals": [{"name": "午餐", "category": "main", "insert_after": "B"}]}
    before = (await client.post(url + "/recompute", json=edit)).json()["day_detail"]
    with patch("app.api.routes.trip_draft.write_day_narrative_llm", new=AsyncMock(return_value="刷新文案")):
        response = await client.post(url + "/assemble?force=true", json={})
    after = response.json()["day_detail"]
    for key in ["attractions", "locked_attraction_names", "removed_attraction_names", "day_start_time", "timeline_order"]:
        assert after[key] == before[key]
    response = await client.post(url + "/assemble?force=true", json={"attractions_order": list("DCB")})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_recompute_and_ai_failure_do_not_write_partial_state(editable_day):
    client, draft_id, url = editable_day
    before = (await client.get(f"/api/trip/draft/{draft_id}")).json()["days_detail"][0]
    with patch("app.api.routes.trip_draft.compute_day_route", new=AsyncMock(side_effect=RuntimeError("模拟地图失败"))):
        with pytest.raises(RuntimeError, match="模拟地图失败"):
            await client.post(url + "/recompute", json={"removed_attraction_names": ["C"], "day_start_time": "11:00"})
    for raw in ['[]', '{"attractions_order": 42}', '{"meals": [42]}', 'invalid JSON']:
        response = type("Response", (), {"content": raw})()
        with patch("app.api.routes.trip_draft.get_llm"), patch(
            "app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=response)
        ):
            assert (await client.post(url + "/ai-rearrange", json={})).status_code == 422
    refreshed = await client.get(f"/api/trip/draft/{draft_id}")
    assert refreshed.json()["days_detail"][0] == before


@pytest.mark.asyncio
async def test_finalize_and_history_keep_final_choices(editable_day):
    client, draft_id, url = editable_day
    saved = (await client.post(url + "/recompute", json={
        "attractions_order": list("ABDC"), "removed_attraction_names": ["A"],
        "day_start_time": "09:45", "meals": [{"name": "午餐", "insert_after": "B"}],
    })).json()["day_detail"]
    with patch("app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer", new=AsyncMock(return_value=("", "", ""))), patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_extract_preferences", new=AsyncMock(return_value=None)
    ), patch("app.agents.langgraph_agent.finalize.pipeline.compute_day_route", new=AsyncMock(return_value=[])):
        response = await client.post(f"/api/trip/draft/{draft_id}/finalize")
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    completed = next(event for event in events if event["type"] == "complete")
    history = (await client.get(f"/api/trips/{completed['trip_id']}")).json()["data"]["plan"]["days"][0]
    for key in ["attractions", "meals", "day_start_time", "timeline_order", "route_segments", "locked_attraction_names"]:
        assert history[key] == saved[key]
    assert [a["name"] for a in history["attractions"]] == list("BDC")
    finalized = (await client.get(f"/api/trip/draft/{draft_id}")).json()
    assert finalized["status"] == "finalized"
    assert finalized["finalized_trip_id"] == completed["trip_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining,lunch_anchor,dinner_anchor", [
    ("BCD", "hotel_start", "C"), ("AB", "A", "B"), ("AC", "A", "C"),
    ("B", "hotel_start", "B"), ("A", "A", "A"), ("C", "hotel_start", "C"),
    ("", "hotel_start", "hotel_start"),
])
async def test_deleted_meal_anchors_and_facts_survive_force_rebuild(editable_day, remaining, lunch_anchor, dinner_anchor):
    client, draft, url = editable_day
    from app.agents.langgraph_agent.assemble.meals import saved_meals
    from app.models.schemas import DayDetail
    meals = [
        {"name":"Lunch", "category":"main", "insert_after":"A", "description":"保留说明", "estimated_cost":0, "source":None},
        {"name":"Dinner", "category":"main", "insert_after":"C", "estimated_cost":37, "source":"nearby"},
    ]
    initial = await client.post(url + "/recompute", json={"locked_attraction_names":[], "meals":meals})
    assert initial.status_code == 200
    before_meals = initial.json()["day_detail"]["meals"]
    assert before_meals[0]["estimated_cost"] == 0 and before_meals[0]["source"] is None
    assert before_meals[0]["description"] == "保留说明"
    assert before_meals[1]["estimated_cost"] == 37
    updated = await client.post(url + "/recompute", json={"removed_attraction_names":[n for n in "ABCD" if n not in remaining]})
    assert updated.status_code == 200
    detail = updated.json()["day_detail"]
    assert [m["insert_after"] for m in saved_meals(DayDetail.model_validate(detail))] == [lunch_anchor,dinner_anchor]
    assert detail["meals"] == before_meals
    with patch("app.api.routes.trip_draft.write_day_narrative_llm", new=AsyncMock(return_value="重建说明")):
        forced = await client.post(url + "/assemble?force=true", json={})
    assert forced.status_code == 200
    for key in ["attractions", "meals", "timeline_order", "removed_attraction_names"]:
        assert forced.json()["day_detail"][key] == detail[key]


@pytest.mark.asyncio
async def test_ai_cannot_clear_server_locks_or_restore_by_forging_edit_fields(editable_day):
    client, draft, url = editable_day
    saved = await client.post(url + "/recompute", json={"removed_attraction_names":["A"]})
    assert saved.status_code == 200
    response = type("Response", (), {"content":json.dumps({
        "attractions_order":["A", "D", "D", "B", "X"],
        "locked_attraction_names":[], "removed_attraction_names":[], "day_start_time":"23:00",
    })})()
    with patch("app.api.routes.trip_draft.get_llm"), patch("app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=response)):
        result = await client.post(url + "/ai-rearrange", json={})
    assert result.status_code == 200
    detail = result.json()["day_detail"]
    assert [a["name"] for a in detail["attractions"]] == list("BDC")
    for key in ["locked_attraction_names", "removed_attraction_names", "day_start_time"]:
        assert detail[key] == saved.json()["day_detail"][key]


@pytest.mark.asyncio
async def test_ai_cannot_repopulate_an_explicitly_empty_day(editable_day):
    client, draft, url = editable_day
    saved = await client.post(url + "/recompute", json={"locked_attraction_names":[], "removed_attraction_names":list("ABCD"), "meals":[]})
    assert saved.status_code == 200
    response = type("Response", (), {"content":json.dumps({"attractions_order":list("ABCD")})})()
    with patch("app.api.routes.trip_draft.get_llm"), patch("app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=response)):
        result = await client.post(url + "/ai-rearrange", json={})
    assert result.status_code == 200
    assert result.json()["day_detail"]["attractions"] == []
    assert result.json()["day_detail"]["removed_attraction_names"] == list("ABCD")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["recompute", "ai-rearrange"])
@pytest.mark.parametrize("failure", ["estimated", "typed", "unexpected"])
async def test_route_boundary_failure_leaves_protected_day_unchanged(editable_day, operation, failure):
    from app.models.schemas import DayDetail, Location
    from app.agents.langgraph_agent.assemble.route import compute_day_route
    from app.services.external_calls import ExternalServiceError, FailureKind
    client, draft, url = editable_day
    record = await trip_draft_service.get_draft(draft)
    detail = DayDetail.model_validate(json.loads(record.days_detail_json)[0])
    # Narrative and route failures are simulated; these coordinates never go to a live service.
    for i, attraction in enumerate(detail.attractions):
        attraction.location = Location(longitude=120+i*.02, latitude=31)
    await trip_draft_service.patch_day_detail(draft, 0, detail)
    # Context comes from source clusters rather than the saved DayDetail.
    from app.database import async_session
    from app.models.db_models import TripDraft
    async with async_session() as session:
        row = await session.get(TripDraft, draft)
        clusters = json.loads(row.clusters_data_json)
        for i, attraction in enumerate(clusters[0]):
            attraction.update(longitude=120+i*.02, latitude=31)
        row.clusters_data_json = json.dumps(clusters)
        await session.commit()
    before = (await trip_draft_service.get_draft(draft)).days_detail_json
    route = AsyncMock(return_value=[{"is_estimated":True}]) if failure == "estimated" else AsyncMock(
        side_effect=ExternalServiceError("amap", "路线计算", FailureKind.CONNECTION) if failure == "typed" else RuntimeError("simulated map failure"))
    response = type("Response", (), {"content":json.dumps({"attractions_order":list("DCBA")})})()
    with patch("app.api.routes.trip_draft.compute_day_route", new=compute_day_route), patch(
        "app.agents.langgraph_agent.assemble.route.compute_route_segments", new=route
    ), patch("app.api.routes.trip_draft.get_llm"), patch(
        "app.api.routes.trip_draft._invoke_llm_with_retry", new=AsyncMock(return_value=response)
    ):
        result = await client.post(url + "/" + operation, json={"day_start_time":"11:00"} if operation == "recompute" else {})
    assert result.status_code == 503, result.text
    assert route.await_count == 1
    assert (await trip_draft_service.get_draft(draft)).days_detail_json == before
