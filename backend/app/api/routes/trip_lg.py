"""旅行规划API路由 (LangGraph版本)

重构说明:
- 原始路由(trip.py)使用 trip_planner_agent (旧HelloAgents框架Agent)
- 本路由使用 langgraph_agent (LangGraph工作流Agent)
- LangGraph Agent通过并行节点搜索景点/天气/酒店，再规划路线，最后生成计划
- 所有服务调用均为异步
- 新增 SSE 流式端点 /plan/stream，实时推送节点执行进度
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse
)
from ...agents.langgraph_agent import get_trip_planner_agent

router = APIRouter(prefix="/trip", tags=["旅行规划"])


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
        print(f"{'='*60}\n")

        agent = get_trip_planner_agent()

        print("🚀 开始LangGraph协作生成旅行计划...")
        trip_plan = await agent.plan_trip(request)

        print("✅ LangGraph旅行计划生成成功，准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan
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

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get(
    "/health",
    summary="健康检查",
    description="检查LangGraph旅行规划服务是否正常"
)
async def health_check():
    try:
        agent = get_trip_planner_agent()

        return {
            "status": "healthy",
            "service": "trip-planner-langgraph",
            "agent_type": "LangGraphTripPlanner",
            "mcp_adapter": "langchain-mcp-adapters",
            "graph_nodes": [
                "search_poi",
                "search_weather",
                "search_hotel",
                "gather_search",
                "cluster_attractions",
                "search_food",
                "plan_route",
                "generate_plan"
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
