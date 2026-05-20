"""草稿（骨架/详细分离）API 路由"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...agents.langgraph_agent.graph import get_trip_planner_agent
from ...agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from ...agents.langgraph_agent.assemble.route import compute_day_route
from ...agents.langgraph_agent.assemble.budget import compute_day_budget
from ...agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
from ...services import trip_draft_service
from ...models.schemas import PlanFromSelectionsRequest

router = APIRouter(prefix="/trip/draft", tags=["trip_draft"])


@router.post(
    "/from-selections/stream",
    summary="从 Discover 勾选结果生成草稿骨架（SSE）",
)
async def create_draft_from_selections(req: PlanFromSelectionsRequest):
    async def event_generator():
        agent = get_trip_planner_agent()
        try:
            selected = [a.model_dump() for a in req.selected_attractions]
            day_assign = None
            if req.day_assignments:
                day_assign = [[a.model_dump() for a in day] for day in req.day_assignments]
            async for event in agent.plan_from_selections_stream(
                request=req.request,
                selected_attractions=selected,
                day_assignments=day_assign,
                weather_info=req.weather_info,
                user_id=req.user_id,
            ):
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error = json.dumps(
                {"type": "error", "message": f"骨架生成失败: {str(e)}", "progress": 0},
                ensure_ascii=False,
            )
            yield f"data: {error}\n\n"

    async def heartbeat_wrapper():
        async for chunk in event_generator():
            yield chunk
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        heartbeat_wrapper(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


from ...models.schemas import (
    TripDraftPayload, TripRequest, MacroPlan, DraftDayContext,
    DayDetail, DiningPoolDay, WeatherInfo, Attraction, Hotel, Location,
    DayEditRequest,
)


def _load_payload(record) -> TripDraftPayload:
    """ORM record → TripDraftPayload"""
    request = TripRequest.model_validate_json(record.request_json)
    macro_plan = MacroPlan.model_validate_json(record.macro_plan_json)
    clusters_data = json.loads(record.clusters_data_json)
    hotels_by_day = json.loads(record.hotels_by_day_json)
    dining_pool_raw = json.loads(record.dining_pool_json)
    weather_info_raw = json.loads(record.weather_info_json)
    days_detail_raw = json.loads(record.days_detail_json)

    days: list[DraftDayContext] = []
    for idx in range(request.travel_days):
        ds = macro_plan.days[idx] if idx < len(macro_plan.days) else None
        cluster = clusters_data[idx] if idx < len(clusters_data) else []
        attractions = []
        for c in cluster:
            loc = None
            if c.get("longitude") and c.get("latitude"):
                loc = Location(longitude=c["longitude"], latitude=c["latitude"])
            attractions.append(Attraction(
                name=c.get("name", ""), address=c.get("address", ""),
                visit_duration=120, description="", location=loc,
            ))
        hotel = None
        if idx < len(hotels_by_day) and hotels_by_day[idx]:
            h = hotels_by_day[idx][0]
            hotel_kwargs = {k: v for k, v in h.items() if k in Hotel.model_fields}
            if h.get("location") and isinstance(h["location"], dict):
                hotel_kwargs["location"] = Location(**h["location"])
            hotel = Hotel(**hotel_kwargs)
        pool = DiningPoolDay()
        if idx < len(dining_pool_raw):
            pool = DiningPoolDay.model_validate(dining_pool_raw[idx])
        weather_obj = None
        for w in weather_info_raw:
            if isinstance(w, dict) and w.get("date") == (ds.date if ds else ""):
                weather_obj = WeatherInfo.model_validate(w)
                break
        days.append(DraftDayContext(
            day_index=idx, date=ds.date if ds else "",
            attraction_names=ds.attraction_names if ds else [],
            attractions=attractions, hotel=hotel,
            dining_pool=pool, weather=weather_obj,
        ))

    days_detail = []
    for d in days_detail_raw:
        if d is None:
            days_detail.append(None)
        else:
            days_detail.append(DayDetail.model_validate(d))

    weather_list = [WeatherInfo.model_validate(w)
                    for w in weather_info_raw if isinstance(w, dict)]

    return TripDraftPayload(
        draft_id=record.id, status=record.status,
        request=request, city=macro_plan.city, macro_plan=macro_plan,
        days=days, days_detail=days_detail,
        weather_info=weather_list,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.get("/{draft_id}", response_model=TripDraftPayload, summary="读取草稿完整内容")
async def get_draft(draft_id: str):
    record = await trip_draft_service.get_draft(draft_id)
    if record is None:
        raise HTTPException(404, detail="draft 不存在")
    return _load_payload(record)


@router.delete("/{draft_id}", summary="删除草稿")
async def delete_draft(draft_id: str):
    ok = await trip_draft_service.delete_draft(draft_id)
    if not ok:
        raise HTTPException(404, detail="draft 不存在")
    return {"success": True}


class DayDetailResponse(BaseModel):
    draft_id: str
    day_index: int
    day_detail: DayDetail


def _ensure_editable(record):
    if record is None:
        raise HTTPException(404, detail="draft 不存在")
    if record.status == "finalized":
        raise HTTPException(409, detail="draft 已 finalized 不可修改")


def _get_day_context_from_record(record, day_index: int) -> DraftDayContext:
    payload = _load_payload(record)
    if day_index < 0 or day_index >= len(payload.days):
        raise HTTPException(409, detail=f"day_index 越界 (max={len(payload.days) - 1})")
    return payload.days[day_index]


@router.post("/{draft_id}/day/{day_index}/assemble", response_model=DayDetailResponse,
             summary="展开某天：规则装配 + 路线 + LLM 叙述")
async def assemble_day(
    draft_id: str, day_index: int,
    overrides: DayEditRequest, force: bool = Query(False),
):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)

    existing_days = json.loads(record.days_detail_json)
    if (not force) and existing_days[day_index] is not None and \
       existing_days[day_index].get("is_assembled"):
        cached = DayDetail.model_validate(existing_days[day_index])
        return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=cached)

    request = TripRequest.model_validate_json(record.request_json)
    override_dict = overrides.model_dump(exclude_none=True)
    detail = rule_assemble_day_timeline(ctx, overrides=override_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    detail.description = await write_day_narrative_llm(
        detail, weather=ctx.weather,
        free_text_input=request.free_text_input or "",
        city=request.city,
    )
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)
