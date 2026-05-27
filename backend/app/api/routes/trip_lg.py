"""旅行规划API路由 (LangGraph版本)

重构说明:
- 使用 langgraph_agent (LangGraph工作流Agent)
- LangGraph Agent通过并行节点搜索景点/天气/酒店，再规划路线，最后生成计划
- 所有服务调用均为异步
- SSE 流式端点 /plan/stream，实时推送节点执行进度
- 景点发现端点 /discover/stream，流式返回景点供用户选择
- 基于选择的规划端点 /plan/from-selections/stream
- 偏好管理端点 /preferences，支持跨会话偏好记忆

韧性增强:
- 结构化错误响应（区分 MCP/LLM/解析错误）
- 降级方案标记（is_fallback + warnings）
- SSE 心跳保活
- 健康检查含 MCP 连接状态
"""

import json
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse,
    UserPreferenceResponse,
    UserPreference,
    ManualSearchRequest,
    PlanFromSelectionsRequest,
    PreviewDayAssignmentRequest,
    PreviewDayAssignmentResponse,
    DayDurationInfo,
    DiscoveredAttraction,
    LoadMoreAttractionsRequest,
    LoadMoreAttractionsResponse,
)
from ...agents.langgraph_agent import get_trip_planner_agent, NonRetryableError
from ...agents.langgraph_agent.utils.duration import estimate_durations_batch
from ...agents.langgraph_agent.utils.geo import (
    _cluster_attractions_by_proximity,
    _order_cluster_by_tsp,
    _rebalance_by_duration,
)
from ...agents.langgraph_agent.nodes.discovery import _fetch_attractions_batch
from ...services.langchain_amap_tools import get_langchain_amap_service
from ...services.preferences_service import load_preferences, save_preferences, delete_preferences

router = APIRouter(prefix="/trip", tags=["旅行规划"])
discover_router = APIRouter(prefix="/discover", tags=["景点发现"])

logger = logging.getLogger(__name__)


def _classify_http_error(e: Exception) -> int:
    if isinstance(e, NonRetryableError):
        msg = str(e).lower()
        if "authentication" in msg or "api key" in msg or "401" in msg or "403" in msg:
            return 401
        if "400" in msg or "参数" in msg:
            return 400
        if "404" in msg or "not found" in msg:
            return 404
    return 500


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求，使用LangGraph多智能体协作生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求 (LangGraph):")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"   交通: {request.transportation}")
        print(f"   住宿: {request.accommodation}")
        print(f"   偏好: {request.preferences}")
        print(f"   预算: {request.budget if request.budget else '不限'}")
        print(f"   同伴: {request.companions}")
        print(f"{'='*60}\n")

        agent = get_trip_planner_agent()

        print("🚀 开始LangGraph协作生成旅行计划...")
        trip_plan = await agent.plan_trip(request)

        print("✅ LangGraph旅行计划生成成功，准备返回响应\n")

        is_fallback = trip_plan is not None and "数据来源受限" in (
            trip_plan.overall_suggestions or ""
        )
        warnings = []
        if is_fallback:
            warnings.append("部分数据获取受限，已使用降级方案生成计划")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan,
            is_fallback=is_fallback,
            warnings=warnings,
        )

    except NonRetryableError as e:
        status_code = _classify_http_error(e)
        print(f"❌ 生成旅行计划失败(不可重试): {str(e)}")
        raise HTTPException(
            status_code=status_code,
            detail=f"生成旅行计划失败: {str(e)}"
        )
    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


@router.post(
    "/plan/stream",
    summary="流式生成旅行计划",
    description="使用SSE实时推送LangGraph各节点执行进度，最终返回完整旅行计划"
)
async def plan_trip_stream(request: TripRequest):
    async def event_generator():
        agent = get_trip_planner_agent()
        try:
            async for event in agent.plan_trip_stream(request):
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error_event = json.dumps({
                "type": "error",
                "message": f"流式生成失败: {str(e)}",
                "progress": 0
            }, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

    async def heartbeat_wrapper():
        async def inner():
            async for chunk in event_generator():
                yield chunk
        async for chunk in inner():
            yield chunk
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        heartbeat_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post(
    "/discover/stream",
    summary="流式景点发现",
    description="搜索并流式返回大量景点供用户选择，同时返回天气和酒店信息"
)
async def discover_attractions_stream(request: TripRequest):
    async def event_generator():
        agent = get_trip_planner_agent()
        try:
            async for event in agent.discover_attractions_stream(request):
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error_event = json.dumps({
                "type": "error",
                "message": f"景点发现失败: {str(e)}",
                "progress": 0
            }, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

    async def heartbeat_wrapper():
        async for chunk in event_generator():
            yield chunk
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        heartbeat_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post(
    "/discover/search",
    summary="手动搜索景点",
    description="在目标城市范围内搜索景点，用于用户手动添加"
)
async def search_attraction_manual(req: ManualSearchRequest):
    try:
        from ...agents.langgraph_agent.utils.parsing import _extract_poi_names
        service = get_langchain_amap_service()
        search_tool = await service.get_tool("maps_text_search")
        if not search_tool:
            raise HTTPException(status_code=503, detail="高德搜索服务不可用")

        from ...agents.langgraph_agent.exceptions import _invoke_tool_with_retry
        search_result = await _invoke_tool_with_retry(
            search_tool,
            {"keywords": req.keywords, "city": req.city},
            max_retries=2,
            per_attempt_timeout=15.0,
        )
        result_str = str(search_result)
        poi_list = _extract_poi_names(result_str)

        attractions = []
        for poi in poi_list[:10]:
            attr = {
                "name": poi.get("name", ""),
                "description": poi.get("type", ""),
                "address": poi.get("address", ""),
                "category": "景点",
                "rating": None,
                "ticket_price": None,
                "image_url": None,
                "location": None,
                "poi_id": poi.get("id"),
            }
            if poi.get("location"):
                loc = poi["location"]
                if isinstance(loc, str) and "," in loc:
                    lng, lat = loc.split(",")
                    try:
                        attr["location"] = {"longitude": float(lng), "latitude": float(lat)}
                    except ValueError:
                        pass
                elif isinstance(loc, dict):
                    attr["location"] = loc
            if poi.get("rating"):
                try:
                    attr["rating"] = float(poi["rating"])
                except (ValueError, TypeError):
                    pass
            if poi.get("cost"):
                attr["ticket_price"] = str(poi["cost"])
            if poi.get("photo"):
                attr["image_url"] = poi["photo"]
            attractions.append(attr)

        return {"success": True, "data": attractions}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 手动搜索景点失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post(
    "/plan/from-selections/stream",
    summary="基于用户选择的景点流式规划",
    description="接收用户选中的景点和可选的日程分配，流式生成完整行程计划"
)
async def plan_from_selections_stream(req: PlanFromSelectionsRequest):
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
            error_event = json.dumps({
                "type": "error",
                "message": f"规划失败: {str(e)}",
                "progress": 0
            }, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

    async def heartbeat_wrapper():
        async for chunk in event_generator():
            yield chunk
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        heartbeat_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post(
    "/plan/preview-day-assignment",
    response_model=PreviewDayAssignmentResponse,
    summary="智能日程分配预览",
    description="LLM 批量估时 + 地理聚类，返回每天的景点分配与估时（不持久化）"
)
async def preview_day_assignment(req: PreviewDayAssignmentRequest):
    selected = [a.model_dump() for a in req.selected_attractions]

    if not selected:
        return PreviewDayAssignmentResponse(day_assignments=[], day_durations=[])

    # 1. LLM 批量估时（失败自动降级）
    durations = await estimate_durations_batch(selected)

    # 2. 几何聚类（仅对有坐标的景点）
    geo_attrs = []
    no_coord_attrs = []
    for attr in selected:
        loc = attr.get("location") or {}
        lon = loc.get("longitude")
        lat = loc.get("latitude")
        if lon and lat:
            geo_attrs.append({"name": attr["name"], "longitude": lon, "latitude": lat})
        else:
            no_coord_attrs.append(attr)

    if geo_attrs:
        clusters = _cluster_attractions_by_proximity(geo_attrs, req.travel_days)
        clusters = _rebalance_by_duration(clusters, durations, max_minutes=480)
    else:
        # 无坐标兜底：均分
        from math import ceil
        per_day = max(ceil(len(selected) / req.travel_days), 1)
        clusters = []
        for d in range(req.travel_days):
            clusters.append([{"name": a["name"]} for a in selected[d * per_day:(d + 1) * per_day]])
        # 兜底路径已把所有景点放入 clusters，避免下方再次追加
        no_coord_attrs = []

    # 把无坐标景点平均派发到当前天数最少的 cluster
    for attr in no_coord_attrs:
        shortest = min(range(len(clusters)), key=lambda i: len(clusters[i])) if clusters else 0
        if not clusters:
            clusters = [[] for _ in range(req.travel_days)]
        clusters[shortest].append({"name": attr["name"]})

    # 3. 还原成完整 DiscoveredAttraction（带 visit_minutes）
    name_to_attr = {a["name"]: a for a in selected}
    day_assignments = []
    day_durations = []
    for idx, cluster in enumerate(clusters):
        day_attrs = []
        total = 0
        for c in cluster:
            full = dict(name_to_attr.get(c["name"], {"name": c["name"]}))
            mins = durations.get(c["name"], 90)
            full["visit_minutes"] = mins
            total += mins
            day_attrs.append(DiscoveredAttraction(**full))
        warning = "当天偏紧" if total > 480 else None
        day_assignments.append(day_attrs)
        day_durations.append(DayDurationInfo(day_index=idx, total_minutes=total, warning=warning))

    return PreviewDayAssignmentResponse(
        day_assignments=day_assignments,
        day_durations=day_durations,
    )


@router.get(
    "/preferences/{user_id}",
    response_model=UserPreferenceResponse,
    summary="获取用户偏好",
    description="获取指定用户的旅行偏好数据"
)
async def get_user_preferences(user_id: str):
    try:
        preferences = await load_preferences(user_id)
        if not preferences:
            return UserPreferenceResponse(
                success=True,
                message="暂无偏好数据",
                data=None,
            )
        return UserPreferenceResponse(
            success=True,
            message="偏好数据获取成功",
            data=preferences,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取偏好失败: {str(e)}"
        )


@router.put(
    "/preferences/{user_id}",
    response_model=UserPreferenceResponse,
    summary="更新用户偏好",
    description="更新指定用户的旅行偏好数据"
)
async def update_user_preferences(user_id: str, preferences: UserPreference):
    try:
        preferences.user_id = user_id
        await save_preferences(user_id, preferences, source="explicit", confidence=1.0)
        return UserPreferenceResponse(
            success=True,
            message="偏好更新成功",
            data=preferences,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"更新偏好失败: {str(e)}"
        )


@router.delete(
    "/preferences/{user_id}",
    summary="删除用户偏好",
    description="删除指定用户的旅行偏好数据"
)
async def delete_user_preferences(user_id: str):
    try:
        deleted = await delete_preferences(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="偏好数据不存在")
        return {"success": True, "message": "偏好删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"删除偏好失败: {str(e)}"
        )


@router.get(
    "/health",
    summary="健康检查",
    description="检查LangGraph旅行规划服务是否正常"
)
async def health_check():
    try:
        agent = get_trip_planner_agent()
        mcp_service = get_langchain_amap_service()
        mcp_healthy = await mcp_service.health_check()

        return {
            "status": "healthy" if mcp_healthy else "degraded",
            "service": "trip-planner-langgraph",
            "agent_type": "LangGraphTripPlanner",
            "mcp_adapter": "langchain-mcp-adapters",
            "mcp_connected": mcp_healthy,
            "graph_nodes": [
                "search_attractions",
                "search_weather",
                "search_hotel",
                "gather_search",
                "cluster_attractions",
                "search_food",
                "plan_route",
                "macro_planner",
                "day_plan_subgraph",
                "reduce_assemble",
                "global_synthesizer",
                "extract_preferences",
                "save_preferences",
            ],
            "features": {
                "discovery_flow": True,
                "preference_memory": True,
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )


@discover_router.post(
    "/load_more",
    response_model=LoadMoreAttractionsResponse,
    summary="加载更多景点",
    description="基于城市继续搜索景点，排除已展示的名字。返回新一批 batch_size 个。"
)
async def load_more_attractions(req: LoadMoreAttractionsRequest):
    try:
        items = await _fetch_attractions_batch(
            city=req.city,
            exclude_names=set(req.exclude_names),
            batch_size=req.batch_size,
            categories=req.categories or None,
        )
        return LoadMoreAttractionsResponse(attractions=items)
    except Exception:
        logger.exception("load_more_attractions failed")
        raise HTTPException(status_code=500, detail="加载更多失败，请稍后重试")
