"""草稿（骨架/详细分离）API 路由"""
import asyncio
import json
import hashlib
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import SystemMessage, HumanMessage

from ...agents.langgraph_agent.graph import get_trip_planner_agent
from ...agents.langgraph_agent.assemble.timeline import rule_assemble_day_timeline
from ...agents.langgraph_agent.assemble.route import compute_day_route
from ...agents.langgraph_agent.assemble.budget import compute_day_budget
from ...agents.langgraph_agent.assemble.schedule import schedule_day
from ...agents.langgraph_agent.assemble.narrative import write_day_narrative_llm
from ...agents.langgraph_agent.exceptions import _invoke_llm_with_retry
from ...agents.langgraph_agent.finalize.pipeline import finalize_draft
from ...services import trip_draft_service
from ...agents.langgraph_agent.assemble.meals import saved_meals as _saved_meals, repair_deleted_anchors, normalize_ai_meals, meal_plan_violations
from ...services.external_calls import ExternalServiceError, FailureKind, operation_deadline
from ...services.llm_service import get_llm
from ...models.schemas import PlanFromSelectionsRequest

router = APIRouter(prefix="/trip/draft", tags=["trip_draft"])


def _parse_ticket_price(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else 0


async def _save_day_detail(draft_id, day_index, detail, *, expected_day, expected_request):
    try:
        await trip_draft_service.patch_day_detail(draft_id, day_index, detail, expected_day=expected_day, expected_request=expected_request)
    except trip_draft_service.DraftChangedDuringFinalize as error:
        raise HTTPException(409, detail=str(error)) from error


@router.post(
    "/from-selections/stream",
    summary="从 Discover 勾选结果生成草稿骨架（SSE）",
)
async def create_draft_from_selections(req: PlanFromSelectionsRequest):
    async def event_generator():
        agent = get_trip_planner_agent()
        try:
            fingerprint = hashlib.sha256(json.dumps(req.model_dump(mode='json', exclude={'request_id'}),
                                                   sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            async with trip_draft_service.creation_request(req.user_id, req.request_id, fingerprint):
                existing = await trip_draft_service.find_created_draft(req.user_id, req.request_id, fingerprint)
                if existing:
                    event = {'type':'complete', 'draft_id':existing.id, 'message':'已恢复保存的草稿', 'progress':100}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
                selected = [a.model_dump() for a in req.selected_attractions]
                day_assign = None
                if req.day_assignments:
                    day_assign = [[a.model_dump() for a in day] for day in req.day_assignments]
                async for event in agent.plan_from_selections_stream(
                    request=req.request, selected_attractions=selected, day_assignments=day_assign,
                    weather_info=req.weather_info, user_id=req.user_id,
                ):
                    data = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"data: {data}\n\n"
        except Exception as e:
            error = json.dumps(
                {"type": "error", "message": f"骨架生成失败: {str(e)}", "progress": 0,
                 "step": getattr(e, 'operation', 'planning'), "retryable": getattr(e, 'retryable', False)},
                ensure_ascii=False,
            )
            yield f"data: {error}\n\n"

    async def heartbeat_wrapper():
        async for chunk in event_generator():
            yield chunk

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
                name=c.get("name", ""),
                address=c.get("address", ""),
                visit_duration=c.get("visit_minutes") or c.get("visit_duration") or 120,
                description=c.get("description") or "",
                category=c.get("category") or "景点",
                rating=c.get("rating"),
                poi_id=c.get("poi_id") or "",
                image_url=c.get("image_url"),
                ticket_price=_parse_ticket_price(c.get("ticket_price")),
                open_hours=c.get("open_hours"),
                tel=c.get("tel"),
                location=loc,
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
            day_start_time=request.default_day_start_time,
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
        draft_id=record.id, status=record.status, finalized_trip_id=record.finalized_trip_id,
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


def _unique_names(names: Optional[list[str]]) -> list[str]:
    if not names:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _build_edit_overrides(
    *,
    order: Optional[list[str]],
    meals: Optional[list[dict]],
    day_start_time: Optional[str],
    locked_names: Optional[list[str]],
    removed_names: Optional[list[str]],
) -> dict:
    overrides_dict = {}
    if order is not None:
        overrides_dict["attractions_order"] = _unique_names(order)
    if meals is not None:
        overrides_dict["meals"] = meals
    if day_start_time is not None:
        overrides_dict["day_start_time"] = day_start_time
    if locked_names is not None:
        overrides_dict["locked_attraction_names"] = _unique_names(locked_names)
    if removed_names is not None:
        overrides_dict["removed_attraction_names"] = _unique_names(removed_names)
    return overrides_dict


def _preserve_locked_positions(
    *,
    base_order: list[str],
    proposed_order: list[str],
    locked_names: list[str],
) -> list[str]:
    """Keep locked attractions at their current indices while accepting AI order for the rest."""
    base_order = _unique_names(base_order)
    locked = {name for name in locked_names if name in base_order}
    unlocked_base = [name for name in base_order if name not in locked]
    proposed_valid = [
        name for name in _unique_names(proposed_order)
        if name in unlocked_base and name not in locked
    ]
    for name in unlocked_base:
        if name not in proposed_valid:
            proposed_valid.append(name)

    result: list[str] = []
    next_unlocked = iter(proposed_valid)
    for name in base_order:
        if name in locked:
            result.append(name)
        else:
            result.append(next(next_unlocked))
    return result


def _merge_day_edit(
    ctx: DraftDayContext, current: Optional[DayDetail], edit: DayEditRequest
) -> dict:
    """Merge explicit edits with the saved day before validating protected slots."""
    removed = _unique_names(
        edit.removed_attraction_names if edit.removed_attraction_names is not None
        else current.removed_attraction_names if current else []
    )
    locked = _unique_names(
        edit.locked_attraction_names if edit.locked_attraction_names is not None
        else current.locked_attraction_names if current else []
    )
    if set(removed) & set(locked):
        raise HTTPException(409, detail="删除锁定景点前请先解锁")

    available = {a.name for a in ctx.attractions if a.name not in set(removed)}
    # Deletion compacts the saved slots; explicit restores join at the end.
    base_order = [a.name for a in (current.attractions if current else ctx.attractions)
                  if a.name in available]
    base_order += [a.name for a in ctx.attractions
                   if a.name in available and a.name not in base_order]
    proposed = _preserve_locked_positions(
        base_order=base_order,
        proposed_order=edit.attractions_order if edit.attractions_order is not None else base_order,
        locked_names=[],
    )
    protected = [name for name in (current.locked_attraction_names if current else [])
                 if name in locked]
    if proposed != _preserve_locked_positions(
        base_order=base_order, proposed_order=proposed, locked_names=protected
    ):
        raise HTTPException(409, detail="移动锁定景点前请先解锁")

    meals = edit.meals if edit.meals is not None else _saved_meals(current) if current else None
    adjustments = []
    if meals is not None:
        # Browser may choose identity/position, but provider facts come from saved candidates.
        sources = {c.name:c.model_dump(mode='json') for cat in type(ctx.dining_pool).model_fields for c in getattr(ctx.dining_pool,cat)}
        sources.update({m.name:m.model_dump(mode='json') for m in current.meals} if current else {})
        meals = [{**sources[m['name']], **{k:v for k,v in m.items() if k in {'insert_after','schedule_mode','preferred_slot','type'}}}
                 if m.get('name') in sources else m for m in meals]
    if meals is not None:
        meals, adjustments = repair_deleted_anchors(meals, current, proposed)
    overrides = _build_edit_overrides(
        order=proposed, meals=meals,
        day_start_time=edit.day_start_time or (current.day_start_time if current else None) or ctx.day_start_time,
        locked_names=locked, removed_names=removed,
    )
    overrides['meal_adjustments'] = adjustments
    return overrides


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
    current = DayDetail.model_validate(existing_days[day_index]) if existing_days[day_index] else None
    override_dict = _merge_day_edit(ctx, current, overrides)
    detail = rule_assemble_day_timeline(ctx, overrides=override_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    schedule_day(detail)
    detail.day_budget = compute_day_budget(detail)
    detail.description = await write_day_narrative_llm(
        detail, weather=ctx.weather,
        free_text_input=request.free_text_input or "",
        city=request.city,
    )
    await _save_day_detail(draft_id, day_index, detail, expected_day=existing_days[day_index], expected_request=record.request_json)
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

    overrides_dict = _merge_day_edit(ctx, current, edit)

    request = TripRequest.model_validate_json(record.request_json)
    detail = rule_assemble_day_timeline(ctx, overrides=overrides_dict or None)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    schedule_day(detail)
    if edit.meals is not None:
        from ...agents.langgraph_agent.assemble.schedule import opening_windows
        existing_names = {m.name for m in current.meals} if current else set()
        for meal in detail.meals:
            if meal.name in existing_names: continue
            if any(w in (meal.name+' '+(meal.open_hours or '')) for w in ('暂停营业','永久关闭','已歇业')):
                raise HTTPException(409, detail=f'{meal.name}已被来源标为停止营业，本次修改未保存')
            entry = next((x for x in detail.timeline_schedule if x.get('kind') == 'meal' and x.get('ref_name') == meal.name), None)
            windows = opening_windows(meal.open_hours)
            if entry and windows and not any(a <= entry['start_minutes'] and entry['end_minutes'] <= b for a,b in windows):
                raise HTTPException(409, detail=f'{meal.name}不适合当前用餐时间，请换一家或调整时间；本次修改未保存')
    detail.day_budget = compute_day_budget(detail)
    # 保留当前 description（recompute 不写 LLM）
    detail.description = current.description if current else ""
    await _save_day_detail(draft_id, day_index, detail, expected_day=existing_days[day_index], expected_request=record.request_json)
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
    await _save_day_detail(draft_id, day_index, detail, expected_day=existing_days[day_index], expected_request=record.request_json)
    return DayDetailResponse(draft_id=draft_id, day_index=day_index, day_detail=detail)


_AI_REARRANGE_SYSTEM = """你是单日行程优化专家。请从给定的餐饮候选池中给出一份当日最优组合。

严格约束：
1. 只能从候选池中挑餐厅，禁止编造名字
2. 输出 JSON，含 attractions_order (景点名顺序) 和 meals (含 category, name, insert_after, preferred_slot)；正餐preferred_slot为breakfast/lunch/dinner
3. category 必须是 main/snack/dessert/cafe/late_night 之一
4. insert_after 必须是 attractions_order 里的景点名（或 hotel_start / hotel_end）
5. 锁定景点必须保留，且不要改变它们在当前顺序里的位置
6. 已删除景点禁止出现在 attractions_order 或 insert_after 中
7. 保留当前已安排正餐的数量与餐次；不能把咖啡/小吃当作午餐或晚餐，不能默默删除已有正餐。不要额外补当前未安排的早餐等餐次
8. 只选择餐厅和位置，不编造价格、坐标、营业时间
9. 不要输出其他字段、不要 markdown、纯 JSON"""


@router.post("/{draft_id}/day/{day_index}/ai-rearrange", response_model=DayDetailResponse,
             summary="AI 重新安排某天")
async def ai_rearrange_day(draft_id: str, day_index: int, req: AIRearrangeRequest):
    try:
        async with operation_deadline(110):
            return await _ai_rearrange_day(draft_id, day_index, req)
    except TimeoutError:
        raise ExternalServiceError('llm', 'AI重排与用餐核对', FailureKind.TIMEOUT) from None


async def _ai_rearrange_day(draft_id: str, day_index: int, req: AIRearrangeRequest):
    record = await trip_draft_service.get_draft(draft_id)
    _ensure_editable(record)
    ctx = _get_day_context_from_record(record, day_index)
    request = TripRequest.model_validate_json(record.request_json)
    existing_days = json.loads(record.days_detail_json)
    current = (DayDetail.model_validate(existing_days[day_index])
               if existing_days[day_index] else None)
    removed_names = current.removed_attraction_names if current else []
    locked_names = current.locked_attraction_names if current else []
    base_attractions = current.attractions if current else [
        a for a in ctx.attractions if a.name not in set(removed_names)
    ]
    base_order = [a.name for a in base_attractions]

    base_detail = current or rule_assemble_day_timeline(ctx)
    pool_text = json.dumps(ctx.dining_pool.model_dump(mode='json'), ensure_ascii=False)
    meal_intent = json.dumps(_saved_meals(base_detail), ensure_ascii=False)
    attr_names = "、".join(base_order) or "（无）"
    locked_text = "、".join(locked_names) or "无"
    removed_text = "、".join(removed_names) or "无"
    hint = req.hint or ""

    prompt = f"""城市: {request.city}, 第 {day_index + 1} 天 ({ctx.date})

景点（可重排）: {attr_names}
锁定景点（必须保留当前位置）: {locked_text}
已删除景点（禁止加入）: {removed_text}
开始时间: {base_detail.day_start_time}
当前已安排用餐（保留正餐餐次与数量，不能漏掉）:
{meal_intent}
餐饮候选池（价格/坐标/营业时间沿用此事实）:
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
        parsed = DayEditRequest.model_validate(json.loads(raw))
    except ExternalServiceError:
        raise
    except Exception:
        raise HTTPException(422, detail="AI返回的安排格式无效，本次未保存，请重试") from None

    attractions_order = _preserve_locked_positions(
        base_order=base_order,
        proposed_order=parsed.attractions_order or base_order,
        locked_names=locked_names,
    )
    try:
        meals, adjustments = normalize_ai_meals(parsed.meals, base_detail, ctx, attractions_order)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error

    overrides = {
        "attractions_order": attractions_order,
        "meals": meals,
        "meal_adjustments": adjustments,
        "locked_attraction_names": locked_names,
        "removed_attraction_names": removed_names,
        "day_start_time": (
            current.day_start_time if current and current.day_start_time
            else ctx.day_start_time
        ),
    }
    detail = rule_assemble_day_timeline(ctx, overrides=overrides)
    detail.route_segments = await compute_day_route(
        detail, request.city, request.transportation
    )
    schedule_day(detail)
    problems = meal_plan_violations(detail, base_detail)
    if problems:
        # Reject a regression after actual route timing. Reuse the last saved itinerary,
        # checking its factual times; no second model request or unbounded optimization loop.
        detail = base_detail.model_copy(deep=True)
        detail.meal_adjustments = ['AI建议与已有用餐时段不兼容，已保留原景点顺序和餐厅。']
        if not detail.route_segments:
            detail.route_segments = await compute_day_route(detail, request.city, request.transportation)
        schedule_day(detail)
        if any(r.is_estimated for r in detail.route_segments):
            raise ExternalServiceError('amap', '路线计算', FailureKind.UNAVAILABLE)
        if meal_plan_violations(detail, base_detail):
            raise HTTPException(422, detail='无法保留已有正餐时段，本次重排未保存；请先核对开始时间、景点时长和用餐安排')
    detail.day_budget = compute_day_budget(detail)
    detail.description = current.description if current else ""
    await _save_day_detail(draft_id, day_index, detail, expected_day=existing_days[day_index], expected_request=record.request_json)
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
            err = {"type": "error", "message": f"定稿失败: {str(e)}",
                   "step": getattr(e, 'operation', 'finalize'), "retryable": getattr(e, 'retryable', False)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
