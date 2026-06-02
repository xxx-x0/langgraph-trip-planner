import json
from unittest.mock import patch, AsyncMock

import pytest

from app.database import init_db
from app.services import trip_draft_service
from app.agents.langgraph_agent.finalize.pipeline import finalize_draft
from app.models.schemas import (
    TripRequest, MacroPlan, DaySkeleton, Attraction, Hotel,
    DayDetail, Location, DiningPoolDay,
)


def _sample_request():
    return TripRequest(
        city="北京", start_date="2026-06-01", end_date="2026-06-02",
        travel_days=2, transportation="公共交通", accommodation="经济型酒店",
    )


def _sample_macro():
    return MacroPlan(
        city="北京", total_days=2,
        days=[
            DaySkeleton(day_index=0, date="2026-06-01", attraction_names=["A"]),
            DaySkeleton(day_index=1, date="2026-06-02", attraction_names=["B"]),
        ],
    )


@pytest.mark.asyncio
async def test_finalize_assembles_missing_days_and_writes_trip_history():
    await init_db()
    draft_id = await trip_draft_service.create_draft(
        user_id="u1", request=_sample_request(),
        selected_attractions=[],
        macro_plan=_sample_macro(),
        clusters_data=[
            [{"name": "A", "longitude": 116.4, "latitude": 39.9}],
            [{"name": "B", "longitude": 116.5, "latitude": 39.95}],
        ],
        hotels_by_day=[[], []],
        dining_pool=[DiningPoolDay().model_dump(mode="json"),
                     DiningPoolDay().model_dump(mode="json")],
        weather_info=[],
    )
    # 用户只展开了第 0 天
    await trip_draft_service.patch_day_detail(
        draft_id, 0,
        DayDetail(
            day_index=0, date="2026-06-01",
            attractions=[Attraction(name="A", address="", visit_duration=120,
                                    description="",
                                    location=Location(longitude=116.4, latitude=39.9))],
            is_assembled=True,
        ),
    )

    fake_trip_record = type("Rec", (), {"id": 777})()

    with patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer",
        new=AsyncMock(return_value=("行程标语", "总建议", "晴间多云")),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_extract_and_save_preferences",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.save_trip",
        new=AsyncMock(return_value=fake_trip_record),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.compute_day_route",
        new=AsyncMock(return_value=[]),
    ):
        trip_plan, trip_id = await finalize_draft(draft_id, user_id="u1")

    assert trip_id == 777
    assert trip_plan.city == "北京"
    assert len(trip_plan.days) == 2
    assert trip_plan.trip_tagline == "行程标语"
    assert trip_plan.weather_summary == "晴间多云"
    # draft 已标记 finalized
    record = await trip_draft_service.get_draft(draft_id)
    assert record.status == "finalized"
    assert record.finalized_trip_id == 777


@pytest.mark.asyncio
async def test_finalize_rejects_already_finalized():
    await init_db()
    draft_id = await trip_draft_service.create_draft(
        user_id="u1", request=_sample_request(),
        selected_attractions=[], macro_plan=_sample_macro(),
        clusters_data=[], hotels_by_day=[],
        dining_pool=[DiningPoolDay().model_dump(mode="json")] * 2,
        weather_info=[],
    )
    await trip_draft_service.mark_finalized(draft_id, trip_id=1)

    with pytest.raises(ValueError, match="已 finalized"):
        await finalize_draft(draft_id, user_id="u1")


@pytest.mark.asyncio
async def test_finalize_preserves_timeline_order_and_day_start_time():
    await init_db()
    draft_id = await trip_draft_service.create_draft(
        user_id="u1",
        request=_sample_request(),
        selected_attractions=[],
        macro_plan=_sample_macro(),
        clusters_data=[[], []],
        hotels_by_day=[[], []],
        dining_pool=[DiningPoolDay().model_dump(mode="json")] * 2,
        weather_info=[],
    )
    await trip_draft_service.patch_day_detail(
        draft_id,
        0,
        DayDetail(
            day_index=0,
            date="2026-06-01",
            day_start_time="09:20",
            timeline_order=[
                {"kind": "attraction", "ref_name": "A"},
                {"kind": "meal", "ref_name": "自选正餐"},
            ],
            attractions=[
                Attraction(
                    name="A",
                    address="",
                    visit_duration=120,
                    description="",
                ),
            ],
            is_assembled=True,
        ),
    )
    fake_trip_record = type("Rec", (), {"id": 778})()

    with patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_global_synthesizer",
        new=AsyncMock(return_value=("", "", "")),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline._run_extract_and_save_preferences",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.save_trip",
        new=AsyncMock(return_value=fake_trip_record),
    ), patch(
        "app.agents.langgraph_agent.finalize.pipeline.compute_day_route",
        new=AsyncMock(return_value=[]),
    ):
        trip_plan, _ = await finalize_draft(draft_id, user_id="u1")

    assert trip_plan.days[0].day_start_time == "09:20"
    assert trip_plan.days[0].timeline_order == [
        {"kind": "attraction", "ref_name": "A"},
        {"kind": "meal", "ref_name": "自选正餐"},
    ]


from app.agents.langgraph_agent.finalize.pipeline import _parse_ticket_price


@pytest.mark.parametrize("raw,expected", [
    ("60", 60),
    ("免费", 0),
    (None, 0),
    ("￥80起", 80),
    (120, 120),
    ("", 0),
])
def test_parse_ticket_price(raw, expected):
    assert _parse_ticket_price(raw) == expected
