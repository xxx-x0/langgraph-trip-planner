"""行程历史 API 路由"""

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...services import trip_history_service
from ...models.schemas import TripPlan, TripRequest, TripPlanResponse

router = APIRouter(prefix="/trips", tags=["行程历史"])


class TripStatusUpdate(BaseModel):
    status: str


class TripListResponse(BaseModel):
    success: bool
    data: list
    total: int
    page: int
    page_size: int


@router.get("", response_model=TripListResponse)
async def list_trips(
    status: Optional[str] = Query(None, description="筛选状态: completed/favorite/archived"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页数量"),
):
    records, total = await trip_history_service.get_trips(status=status, page=page, page_size=page_size)
    items = [trip_history_service.record_to_dict(r) for r in records]
    return TripListResponse(success=True, data=items, total=total, page=page, page_size=page_size)


@router.get("/search", response_model=TripListResponse)
async def search_trips(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    records, total = await trip_history_service.search_trips(keyword=keyword, page=page, page_size=page_size)
    items = [trip_history_service.record_to_dict(r) for r in records]
    return TripListResponse(success=True, data=items, total=total, page=page, page_size=page_size)


@router.get("/{trip_id}")
async def get_trip(trip_id: int):
    record = await trip_history_service.get_trip_by_id(trip_id)
    if not record:
        raise HTTPException(status_code=404, detail="行程不存在")
    result = trip_history_service.record_to_dict(record)
    try:
        result["plan"] = json.loads(record.plan_data)
    except (json.JSONDecodeError, TypeError):
        result["plan"] = None
    try:
        result["request"] = json.loads(record.request_data) if record.request_data else None
    except (json.JSONDecodeError, TypeError):
        result["request"] = None
    return {"success": True, "data": result}


@router.post("")
async def save_trip(body: dict):
    try:
        plan_data = body.get("plan")
        request_data = body.get("request")
        plan = TripPlan(**plan_data) if plan_data else None
        request = TripRequest(**request_data) if request_data else None
        if not plan:
            raise HTTPException(status_code=400, detail="缺少plan数据")
        record = await trip_history_service.save_trip(plan=plan, request=request)
        return {"success": True, "data": trip_history_service.record_to_dict(record), "message": "行程保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.delete("/{trip_id}")
async def delete_trip(trip_id: int):
    deleted = await trip_history_service.delete_trip(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="行程不存在")
    return {"success": True, "message": "行程已删除"}


@router.patch("/{trip_id}/status")
async def update_status(trip_id: int, body: TripStatusUpdate):
    if body.status not in ("completed", "favorite", "archived"):
        raise HTTPException(status_code=400, detail="无效状态，可选: completed/favorite/archived")
    record = await trip_history_service.update_trip_status(trip_id, body.status)
    if not record:
        raise HTTPException(status_code=404, detail="行程不存在")
    return {"success": True, "data": trip_history_service.record_to_dict(record)}
