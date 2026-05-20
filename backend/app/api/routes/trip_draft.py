"""草稿（骨架/详细分离）API 路由"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...agents.langgraph_agent.graph import get_trip_planner_agent
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
