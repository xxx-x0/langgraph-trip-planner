"""草稿（骨架/详细分离）API 路由"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import SystemMessage, HumanMessage

from ...agents.langgraph_agent.graph import get_trip_planner_agent
from ...agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from ...agents.langgraph_agent.assemble.route import compute_day_route
from ...agents.langgraph_agent.assemble.budget import compute_day_budget
from ...agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
from ...agents.langgraph_agent.exceptions import _invoke_llm_with_retry
from ...agents.langgraph_agent.finalize.pipeline import finalize_draft
from ...services import trip_draft_service
from ...services.llm_service import get_llm
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
    DayEditRequest, AIRearrangeRequest,
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


@router.post("/{draft_id}/day/{day_index}/recompute", response_model=DayDetailResponse,
             summary="重算某天：规则装配 + amap 路线（无 LLM）")
async def recompute_day(draft_id: str, day_index: int, edit: DayEditRequest):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)

    # 取当前 day_detail 作为"保留意图"的源
    existing_days = json.loads(record.days_detail_json)
    current = (DayDetail.model_validate(existing_days[day_index])
               if existing_days[day_index] else None)

    # 合并 overrides：未传字段沿用当前 day_detail
    final_order = edit.attractions_order
    if final_order is None and current:
        final_order = [a.name for a in current.attractions]
    final_meals = edit.meals
    if final_meals is None and current:
        final_meals = [m.model_dump(mode="json") for m in current.meals]
        # 默认把每个 meal 锚回中点景点之后，避免位置漂移
        if final_meals and final_order:
            mid = max(len(final_order) // 2 - 1, 0)
            for m in final_meals:
                m.setdefault("insert_after", final_order[mid] if final_order else "")

    overrides_dict = {}
    if final_order is not None:
        overrides_dict["attractions_order"] = final_order
    if final_meals is not None:
        overrides_dict["meals"] = final_meals

    request = TripRequest.model_validate_json(record.request_json)
    detail = rule_assemble_day_timeline(ctx, overrides=overrides_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    # 保留当前 description（recompute 不写 LLM）
    detail.description = current.description if current else ""
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)


@router.post("/{draft_id}/day/{day_index}/narrative", response_model=DayDetailResponse,
             summary="重写当日叙述文案（仅刷新 description）")
async def rewrite_narrative(draft_id: str, day_index: int):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)
    request = TripRequest.model_validate_json(record.request_json)
    existing_days = json.loads(record.days_detail_json)
    if existing_days[day_index] is None:
        raise HTTPException(409, detail="该天尚未 assemble，无法重写文案")
    detail = DayDetail.model_validate(existing_days[day_index])
    detail.description = await write_day_narrative_llm(
        detail, weather=ctx.weather,
        free_text_input=request.free_text_input or "",
        city=request.city,
    )
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)


_AI_REARRANGE_SYSTEM = """你是单日行程优化专家。请从给定的餐饮候选池中给出一份当日最优组合。

严格约束：
1. 只能从候选池中挑餐厅，禁止编造名字
2. 输出 JSON，含 attractions_order (景点名顺序) 和 meals (含 category, name, insert_after, estimated_cost)
3. category 必须是 main/snack/dessert/cafe/late_night 之一
4. insert_after 必须是 attractions_order 里的景点名（或 hotel_start / hotel_end）
5. 不要输出其他字段、不要 markdown、纯 JSON"""


@router.post("/{draft_id}/day/{day_index}/ai-rearrange", response_model=DayDetailResponse,
             summary="AI 重新安排某天")
async def ai_rearrange_day(draft_id: str, day_index: int, req: AIRearrangeRequest):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)
    request = TripRequest.model_validate_json(record.request_json)

    pool_summary = []
    for cat, items in ctx.dining_pool.model_dump().items():
        if items:
            names = "、".join(it["name"] for it in items[:5])
            pool_summary.append(f"  {cat}: {names}")
    pool_text = "\n".join(pool_summary) or "（候选池为空）"

    attr_names = "、".join(a.name for a in ctx.attractions) or "（无）"
    hint = req.hint or ""

    prompt = f"""城市: {request.city}, 第 {day_index + 1} 天 ({ctx.date})

景点（可重排）: {attr_names}
餐饮候选池:
{pool_text}

用户提示: {hint or '无'}

请输出 JSON。"""

    llm = get_llm()
    try:
        resp = await _invoke_llm_with_retry(
            llm, [SystemMessage(content=_AI_REARRANGE_SYSTEM),
                  HumanMessage(content=prompt)],
        )
        raw = (resp.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
    except Exception as e:
        raise HTTPException(422, detail=f"AI 暂不可用: {str(e)[:120]}")

    overrides = {
        "attractions_order": parsed.get("attractions_order") or [a.name for a in ctx.attractions],
        "meals": parsed.get("meals") or [],
    }
    detail = rule_assemble_day_timeline(ctx, overrides=overrides)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    detail.day_budget = compute_day_budget(detail)
    # description 保留当前（用户可手动 narrative 刷新）
    existing_days = json.loads(record.days_detail_json)
    if existing_days[day_index]:
        detail.description = existing_days[day_index].get("description", "")
    await trip_draft_service.patch_day_detail(draft_id, day_index, detail)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)


@router.post("/{draft_id}/finalize", summary="定稿草稿 → 写 trip_history (SSE)")
async def finalize_draft_endpoint(draft_id: str):
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type':'progress','step':'preparing','message':'整理行程...'}, ensure_ascii=False)}\n\n"
            record = await trip_draft_service.get_draft(draft_id)
            if record is None:
                yield f"data: {json.dumps({'type':'error','message':'draft 不存在'}, ensure_ascii=False)}\n\n"
                return
            if record.status == "finalized":
                yield f"data: {json.dumps({'type':'error','message':'draft 已 finalized'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type':'progress','step':'synthesizer','message':'生成总体建议...'}, ensure_ascii=False)}\n\n"
            trip_plan, trip_id = await finalize_draft(draft_id, user_id=record.user_id)
            yield f"data: {json.dumps({'type':'progress','step':'saving','message':'写入历史...'}, ensure_ascii=False)}\n\n"

            payload = {
                "type": "complete",
                "trip_id": trip_id,
                "trip_plan": trip_plan.model_dump(mode="json"),
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            err = {"type": "error", "message": f"finalize 失败: {str(e)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
