import pytest

from app.agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from app.models.schemas import (
    Attraction, Hotel, Location, DiningCandidate, DiningCategory,
    DiningPoolDay, DraftDayContext, WeatherInfo,
)


def _attr(name: str) -> Attraction:
    return Attraction(
        name=name, address=f"{name}地址", visit_duration=120,
        description=f"{name}简介",
        location=Location(longitude=116.4, latitude=39.9),
    )


def _candidate(name: str, category: DiningCategory) -> DiningCandidate:
    return DiningCandidate(
        name=name, category=category, source="nearby",
        location=Location(longitude=116.41, latitude=39.91),
        rating=4.5, avg_cost=80,
    )


def _ctx(attractions, dining_pool=None, hotel=None) -> DraftDayContext:
    return DraftDayContext(
        day_index=0, date="2026-06-01",
        attraction_names=[a.name for a in attractions],
        attractions=attractions,
        hotel=hotel,
        dining_pool=dining_pool or DiningPoolDay(),
    )


def test_no_overrides_no_dining_pool_returns_empty_meals():
    ctx = _ctx([_attr("A"), _attr("B")])
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    assert [a.name for a in detail.attractions] == ["A", "B"]
    assert detail.meals == []
    assert detail.is_assembled is True


def test_no_overrides_with_main_pool_inserts_one_main_at_midpoint():
    pool = DiningPoolDay(main=[_candidate("M1", DiningCategory.MAIN)])
    ctx = _ctx([_attr("A"), _attr("B"), _attr("C"), _attr("D")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    assert len(detail.meals) == 1
    m = detail.meals[0]
    assert m.name == "M1"
    assert m.category == DiningCategory.MAIN
    # 中点：4 个景点 → 第 1 个景点之后（index = 4//2 - 1 = 1，即 attractions[1]=B 之后）
    insert_after_indices = [
        i for i, item in enumerate(detail.timeline_order)
        if item.get("ref_name") == "B"
    ]
    meal_indices = [
        i for i, item in enumerate(detail.timeline_order)
        if item.get("kind") == "meal" and item.get("ref_name") == "M1"
    ]
    assert insert_after_indices and meal_indices
    assert meal_indices[0] == insert_after_indices[0] + 1


def test_override_attractions_order_reorders():
    ctx = _ctx([_attr("A"), _attr("B"), _attr("C")])
    detail = rule_assemble_day_timeline(
        ctx, overrides={"attractions_order": ["C", "A", "B"]}
    )
    assert [a.name for a in detail.attractions] == ["C", "A", "B"]


def test_override_meals_empty_clears_default():
    pool = DiningPoolDay(main=[_candidate("M1", DiningCategory.MAIN)])
    ctx = _ctx([_attr("A"), _attr("B")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides={"meals": []})
    assert detail.meals == []


def test_override_meals_with_user_picks():
    pool = DiningPoolDay(
        main=[_candidate("M1", DiningCategory.MAIN)],
        snack=[_candidate("S1", DiningCategory.SNACK)],
    )
    ctx = _ctx([_attr("A"), _attr("B")], dining_pool=pool)
    detail = rule_assemble_day_timeline(ctx, overrides={
        "meals": [
            {"name": "M1", "category": "main", "insert_after": "A"},
            {"name": "S1", "category": "snack", "insert_after": "B"},
        ]
    })
    assert [m.name for m in detail.meals] == ["M1", "S1"]
    assert detail.meals[0].category == DiningCategory.MAIN
    assert detail.meals[1].category == DiningCategory.SNACK


def test_unknown_attraction_in_order_is_ignored():
    ctx = _ctx([_attr("A"), _attr("B")])
    detail = rule_assemble_day_timeline(
        ctx, overrides={"attractions_order": ["X", "A", "Y", "B"]}
    )
    assert [a.name for a in detail.attractions] == ["A", "B"]


def test_hotel_appears_at_start_and_end_of_timeline():
    hotel = Hotel(name="H1", address="酒店地址",
                  location=Location(longitude=116.4, latitude=39.9))
    ctx = _ctx([_attr("A")], hotel=hotel)
    detail = rule_assemble_day_timeline(ctx, overrides=None)
    timeline = detail.timeline_order
    assert timeline[0]["kind"] == "hotel"
    assert timeline[-1]["kind"] == "hotel"


from unittest.mock import patch, AsyncMock

from app.agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
from app.models.schemas import DayDetail, WeatherInfo


@pytest.mark.asyncio
async def test_narrative_projects_saved_facts_without_model():
    detail = DayDetail(day_index=0, date="2026-06-01", attractions=[_attr("A")])
    with patch("app.services.llm_service.get_llm", side_effect=AssertionError("no model")):
        text = await write_day_narrative_llm(detail, free_text_input="晴天，已预约成功")
    assert "A" in text and "已预约成功" not in text
    assert detail.description_source == "itinerary_facts_v1"
    assert "当日天气尚未获取" in "；".join(detail.pending_confirmations)


@pytest.mark.asyncio
async def test_narrative_refresh_is_deterministic_and_keeps_arrangement():
    detail = DayDetail(day_index=0, date="2026-06-01", attractions=[_attr("A")])
    before = detail.model_dump(exclude={"description", "description_source", "pending_confirmations"})
    first = await write_day_narrative_llm(detail)
    assert await write_day_narrative_llm(detail) == first
    assert detail.model_dump(exclude={"description", "description_source", "pending_confirmations"}) == before


def test_removed_attractions_are_filtered_before_ordering():
    ctx = _ctx([_attr("A"), _attr("B"), _attr("C")])
    detail = rule_assemble_day_timeline(
        ctx,
        overrides={
            "attractions_order": ["C", "B", "A"],
            "removed_attraction_names": ["B"],
        },
    )
    assert [a.name for a in detail.attractions] == ["C", "A"]
    assert detail.removed_attraction_names == ["B"]
    timeline_names = [item["ref_name"] for item in detail.timeline_order]
    assert "B" not in timeline_names


def test_locked_attractions_only_keep_present_names():
    ctx = _ctx([_attr("A"), _attr("B")])
    detail = rule_assemble_day_timeline(
        ctx,
        overrides={
            "locked_attraction_names": ["A", "X", "A"],
            "removed_attraction_names": ["B"],
        },
    )
    assert detail.locked_attraction_names == ["A"]
