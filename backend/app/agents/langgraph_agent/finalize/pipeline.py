"""草稿定稿；兼容历史观察仅参与保存，不作为下一次规划依据。"""
import json
import asyncio
from weakref import WeakValueDictionary
from typing import Tuple, Optional

from ....models.schemas import (
    TripRequest, MacroPlan, TripPlan, DayPlan, DayDetail, DraftDayContext,
    DiningPoolDay, Attraction, Hotel, Budget, WeatherInfo, Location,
)
from ....services import trip_draft_service
from ....services.journey_service import apply_context, conflicts
from ..assemble.timeline import rule_assemble_day_timeline
from ..assemble.route import compute_day_route
from ..assemble.budget import compute_day_budget, combine_budgets, parse_ticket_price as _parse_ticket_price
from ..assemble.schedule import schedule_day
from ..assemble.narrative import refresh_day_description, refresh_trip_descriptions

_finalize_locks = WeakValueDictionary()


async def _run_global_synthesizer(trip_plan: TripPlan, free_text: str) -> Tuple[str, str, str]:
    refresh_trip_descriptions(trip_plan)
    return trip_plan.trip_tagline, trip_plan.overall_suggestions, trip_plan.weather_summary


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


async def _run_extract_preferences(trip_plan: TripPlan, user_id: str) -> dict | None:
    """Extract only; persistence participates in the finalization transaction."""
    from ..nodes.preferences import extract_preferences_node
    state = {"trip_plan": trip_plan, "user_id": user_id, "extracted_preferences": None}
    state.update(await extract_preferences_node(state))
    return state.get("extracted_preferences")


def _day_detail_to_day_plan(detail: DayDetail, transportation: str, accommodation: str) -> DayPlan:
    return DayPlan(
        date=detail.date,
        day_index=detail.day_index,
        description=detail.description,
        trip_intent=detail.trip_intent,
        locked_attraction_names=detail.locked_attraction_names,
        pending_confirmations=detail.pending_confirmations,
        schedule_suggestion=detail.schedule_suggestion,
        travel_window=detail.travel_window, rest_periods=detail.rest_periods,
        description_source=detail.description_source,
        transportation=transportation,
        accommodation=accommodation,
        hotel=detail.hotel,
        attractions=detail.attractions,
        meals=detail.meals,
        route_segments=detail.route_segments,
        timeline_order=detail.timeline_order,
        day_start_time=detail.day_start_time,
        timeline_schedule=detail.timeline_schedule,
        meal_warnings=detail.meal_warnings,
        meal_adjustments=detail.meal_adjustments,
        overnight_stay=detail.overnight_stay,
    )


def _build_day_context(
    day_idx: int,
    macro_plan: MacroPlan,
    clusters_data: list,
    hotels_by_day: list,
    dining_pool: list,
    weather_info: list,
    default_day_start_time: str,
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
            address=c.get("address") or "",
            visit_duration=c.get("visit_minutes") or 120,
            description=c.get("description") or "",
            category=c.get("category") or "景点",
            rating=c.get("rating"),
            ticket_price=_parse_ticket_price(c.get("ticket_price")),
            image_url=c.get("image_url"),
            poi_id=c.get("poi_id") or "",
            open_hours=c.get("open_hours"),
            tel=c.get("tel"),
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
        day_start_time=default_day_start_time,
        overnight_stay=day_idx < macro_plan.total_days - 1,
    )


async def finalize_draft(draft_id: str, *, user_id: str) -> Tuple[TripPlan, int]:
    lock = _finalize_locks.get(draft_id)
    if lock is None:
        lock = asyncio.Lock()
        _finalize_locks[draft_id] = lock
    async with lock:
        return await _finalize_draft(draft_id, user_id=user_id)


async def _finalize_draft(draft_id: str, *, user_id: str) -> Tuple[TripPlan, int]:
    record = await trip_draft_service.get_draft(draft_id)
    if record is None:
        raise ValueError(f"draft {draft_id} 不存在")
    if record.status == "finalized":
        return await trip_draft_service.read_finalized_trip(record)

    request = TripRequest.model_validate_json(record.request_json)
    macro_plan = MacroPlan.model_validate_json(record.macro_plan_json)
    clusters_data = json.loads(record.clusters_data_json)
    hotels_by_day = json.loads(record.hotels_by_day_json)
    dining_pool = json.loads(record.dining_pool_json)
    weather_info = json.loads(record.weather_info_json)
    days_detail_raw = json.loads(record.days_detail_json)

    day_plans = []
    budgets = []
    for idx in range(request.travel_days):
        existing = days_detail_raw[idx] if idx < len(days_detail_raw) else None
        if existing is not None:
            detail = DayDetail.model_validate(existing)
            if not detail.route_segments:
                detail.route_segments = await compute_day_route(
                    detail, request.city, request.transportation
                )
        else:
            ctx = _build_day_context(
                idx, macro_plan, clusters_data, hotels_by_day, dining_pool,
                weather_info, request.default_day_start_time,
            )
            from ....services.recommendations import intent_for
            ctx.trip_intent = intent_for(request)
            apply_context(ctx,request)
            detail = rule_assemble_day_timeline(ctx, overrides=None)
            detail.route_segments = await compute_day_route(
                detail, request.city, request.transportation
            )

        from ....services.recommendations import intent_for
        detail.trip_intent = intent_for(request)
        detail.overnight_stay = idx < request.travel_days - 1
        apply_context(detail,request)
        detail.companion_count = request.companions.count if request.companions else 1
        raw_by_name = {c['name']: c for c in (clusters_data[idx] if idx < len(clusters_data) else [])}
        for attraction in detail.attractions:
            raw = raw_by_name.get(attraction.name)
            if attraction.ticket_price == 0 and raw and _parse_ticket_price(raw.get('ticket_price')) is None:
                attraction.ticket_price = None
        schedule_day(detail)
        problems = conflicts(detail)
        if problems: raise ValueError("与交通或休息安排冲突，请先调整第"+str(idx+1)+"天："+"；".join(problems))
        detail.day_budget = compute_day_budget(detail)
        refresh_day_description(detail, next((WeatherInfo.model_validate(w) for w in weather_info
                                            if isinstance(w, dict) and w.get("date") == detail.date), None))

        day_plans.append(_day_detail_to_day_plan(
            detail, request.transportation, request.accommodation
        ))
        budgets.append(detail.day_budget)

    weather_list = [WeatherInfo.model_validate(w) for w in weather_info if isinstance(w, dict)]

    trip_plan = TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=day_plans,
        weather_info=weather_list,
        overall_suggestions="",
        budget=combine_budgets(budgets, request.budget),
        companions=request.companions,
        journey=request.journey,
    )

    tagline, suggestions, summary = await _run_global_synthesizer(
        trip_plan, request.free_text_input or ""
    )
    trip_plan.trip_tagline = tagline
    trip_plan.overall_suggestions = suggestions
    trip_plan.weather_summary = summary

    extracted = await _run_extract_preferences(trip_plan, user_id)
    return await trip_draft_service.persist_finalized_trip(
        draft_id, trip_plan, request, record.days_detail_json, extracted, expected_request=record.request_json
    )
