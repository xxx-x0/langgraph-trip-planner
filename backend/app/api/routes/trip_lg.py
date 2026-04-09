"""旅行规划API路由 (LangGraph版本)

重构说明:
- 原始路由(trip.py)使用 trip_planner_agent (旧HelloAgents框架Agent)
- 本路由使用 langgraph_agent (LangGraph工作流Agent)
- LangGraph Agent通过并行节点搜索景点/天气/酒店，再规划路线，最后生成计划
- 所有服务调用均为异步
"""

from fastapi import APIRouter, HTTPException
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
                "plan_route",
                "generate_plan"
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
