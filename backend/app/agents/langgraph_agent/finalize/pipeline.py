"""定稿流水线：草稿 → TripPlan → 全局综合 + 偏好提取 → trip_history"""
import json
from typing import Tuple, Optional

from ....models.schemas import (
    TripRequest, MacroPlan, TripPlan, DayPlan, DayDetail, DraftDayContext,
    DiningPoolDay, Attraction, Hotel, Budget, WeatherInfo, Location,
)
from ....services import trip_draft_service
from ....services.trip_history_service import save_trip
from ..assemble.timeline import rule_assemble_day_timeline
from ..assemble.route import compute_day_route
from ..assemble.budget import compute_day_budget


async def _run_global_synthesizer(trip_plan: TripPlan, free_text: str) -> Tuple[str, str, str]:
    """复用旧 global_synthesizer_node 的核心 LLM 调用，返回 (tagline, suggestions, summary)"""
    from ..nodes.generate import global_synthesizer_node, _generate_weather_summary_fallback
    state = {
        "trip_plan": trip_plan,
        "request": _make_pseudo_request(trip_plan, free_text),
        "weather_info": "",
    }
    try:
        result = await global_synthesizer_node(state)
        plan = result.get("trip_plan") or trip_plan
        return plan.trip_tagline, plan.overall_suggestions, plan.weather_summary
    except Exception as e:
        print(f"⚠️ global_synthesizer 失败，使用兜底: {e}")
        return "", "", _generate_weather_summary_fallback(trip_plan)


def _make_pseudo_request(plan: TripPlan, free_text: str):
    return TripRequest(
        city=plan.city,
        start_date=plan.start_date,
        end_date=plan.end_date,
        travel_days=len(plan.days),
        transportation="公共交通",
        accommodation="经济型酒店",
        free_text_input=free_text,
    )


async def _run_extract_and_save_preferences(trip_plan: TripPlan, user_id: str) -> None:
    """复用旧 extract_preferences_node + save_preferences_node"""
    from ..nodes.preferences import extract_preferences_node, save_preferences_node
    state = {"trip_plan": trip_plan, "user_id": user_id, "extracted_preferences": None}
    state.update(await extract_preferences_node(state))
    await save_preferences_node(state)


def _day_detail_to_day_plan(detail: DayDetail, transportation: str, accommodation: str) -> DayPlan:
    return DayPlan(
        date=detail.date,
        day_index=detail.day_index,
        description=detail.description,
        transportation=transportation,
        accommodation=accommodation,
        hotel=detail.hotel,
        attractions=detail.attractions,
        meals=detail.meals,
        route_segments=detail.route_segments,
    )


def _build_day_context(
    day_idx: int,
    macro_plan: MacroPlan,
    clusters_data: list,
    hotels_by_day: list,
    dining_pool: list,
    weather_info: list,
) -> DraftDayContext:
    day_skeleton = macro_plan.days[day_idx]
    cluster = clusters_data[day_idx] if day_idx < len(clusters_data) else []
    attractions = []
    for c in cluster:
        loc = None
        if c.get("longitude") and c.get("latitude"):
            loc = Location(longitude=c["longitude"], latitude=c["latitude"])
        attractions.append(Attraction(
            name=c["name"],
            address=c.get("address", ""),
            visit_duration=120,
            description="",
            location=loc,
        ))
    hotel: Optional[Hotel] = None
    if day_idx < len(hotels_by_day) and hotels_by_day[day_idx]:
        h = hotels_by_day[day_idx][0]
        hotel_kwargs = {k: h[k] for k in h.keys() if k in Hotel.model_fields}
        if h.get("location") and isinstance(h["location"], dict):
            hotel_kwargs["location"] = Location(**h["location"])
        hotel = Hotel(**hotel_kwargs)

    pool = DiningPoolDay()
    if day_idx < len(dining_pool):
        pool = DiningPoolDay.model_validate(dining_pool[day_idx])

    weather_obj = None
    if day_idx < len(weather_info):
        w = weather_info[day_idx]
        if isinstance(w, dict):
            weather_obj = WeatherInfo.model_validate(w)

    return DraftDayContext(
        day_index=day_idx,
        date=day_skeleton.date,
        attraction_names=day_skeleton.attraction_names,
        attractions=attractions,
        hotel=hotel,
        dining_pool=pool,
        weather=weather_obj,
    )


async def finalize_draft(draft_id: str, *, user_id: str) -> Tuple[TripPlan, int]:
    record = await trip_draft_service.get_draft(draft_id)
    if record is None:
        raise ValueError(f"draft {draft_id} 不存在")
    if record.status == "finalized":
        raise ValueError(f"draft {draft_id} 已 finalized")

    request = TripRequest.model_validate_json(record.request_json)
    macro_plan = MacroPlan.model_validate_json(record.macro_plan_json)
    clusters_data = json.loads(record.clusters_data_json)
    hotels_by_day = json.loads(record.hotels_by_day_json)
    dining_pool = json.loads(record.dining_pool_json)
    weather_info = json.loads(record.weather_info_json)
    days_detail_raw = json.loads(record.days_detail_json)

    day_plans = []
    total_budget = Budget()
    for idx in range(request.travel_days):
        existing = days_detail_raw[idx] if idx < len(days_detail_raw) else None
        if existing is not None:
            detail = DayDetail.model_validate(existing)
            if not detail.route_segments:
                detail.route_segments = await compute_day_route(
                    detail, request.city, request.transportation
                )
            if detail.day_budget is None:
                detail.day_budget = compute_day_budget(detail)
        else:
            ctx = _build_day_context(
                idx, macro_plan, clusters_data, hotels_by_day, dining_pool, weather_info
            )
            detail = rule_assemble_day_timeline(ctx, overrides=None)
            detail.route_segments = await compute_day_route(
                detail, request.city, request.transportation
            )
            detail.day_budget = compute_day_budget(detail)

        day_plans.append(_day_detail_to_day_plan(
            detail, request.transportation, request.accommodation
        ))
        b = detail.day_budget
        total_budget = Budget(
            total_attractions=total_budget.total_attractions + b.total_attractions,
            total_hotels=total_budget.total_hotels + b.total_hotels,
            total_meals=total_budget.total_meals + b.total_meals,
            total_transportation=total_budget.total_transportation + b.total_transportation,
            total=total_budget.total + b.total,
            budget_limit=request.budget,
        )

    weather_list = [WeatherInfo.model_validate(w) for w in weather_info if isinstance(w, dict)]

    trip_plan = TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=day_plans,
        weather_info=weather_list,
        overall_suggestions="",
        budget=total_budget,
        companions=request.companions,
    )

    tagline, suggestions, summary = await _run_global_synthesizer(
        trip_plan, request.free_text_input or ""
    )
    trip_plan.trip_tagline = tagline
    trip_plan.overall_suggestions = suggestions
    trip_plan.weather_summary = summary

    await _run_extract_and_save_preferences(trip_plan, user_id)

    trip_record = await save_trip(trip_plan, request=request)
    await trip_draft_service.mark_finalized(draft_id, trip_id=trip_record.id)
    await trip_draft_service.update_synthesizer_fields(
        draft_id,
        trip_tagline=tagline,
        overall_suggestions=suggestions,
        weather_summary=summary,
    )

    return trip_plan, trip_record.id
