"""行程历史 CRUD 服务"""

import json
from typing import List, Optional, Tuple
from sqlalchemy import select, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models.db_models import TripRecord
from ..models.schemas import TripPlan, TripRequest
from ..logger import get_logger

logger = get_logger(__name__)


def build_trip_record(plan: TripPlan, request: Optional[TripRequest] = None) -> TripRecord:
    from ..agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
    plan = refresh_trip_descriptions(plan.model_copy(deep=True))
    plan_dict = plan.model_dump(mode="json")
    request_dict = None
    if request:
        request_dict = request.model_dump(mode="json") if hasattr(request, 'model_dump') else request.dict()

    total_cost = plan.budget.total if plan.budget else 0
    budget_limit = plan.budget.budget_limit if plan.budget else None
    companion_type = plan.companions.type if plan.companions else None
    companion_count = plan.companions.count if plan.companions else 1
    tags = ",".join(request.preferences) if request and request.preferences else None

    cover_image = None
    for day in plan.days:
        for attr in day.attractions:
            if attr.image_url:
                cover_image = attr.image_url
                break
        if cover_image:
            break

    title = f"{plan.city}{plan.days.__len__()}日游"

    record = TripRecord(
        title=title,
        city=plan.city,
        start_date=plan.start_date,
        end_date=plan.end_date,
        travel_days=len(plan.days),
        plan_data=json.dumps(plan_dict, ensure_ascii=False),
        request_data=json.dumps(request_dict, ensure_ascii=False) if request_dict else None,
        status="completed",
        budget_limit=budget_limit,
        total_cost=total_cost,
        companion_type=companion_type,
        companion_count=companion_count,
        tags=tags,
        cover_image=cover_image,
    )
    return record


async def save_trip(plan: TripPlan, request: Optional[TripRequest] = None) -> TripRecord:
    async with async_session() as session:
        record = build_trip_record(plan, request)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        logger.info(f"行程已保存: id={record.id}, title={record.title}")
        return record

async def get_trips(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
) -> Tuple[List[TripRecord], int]:
    async with async_session() as session:
        query = select(TripRecord).order_by(desc(TripRecord.created_at))
        count_query = select(func.count(TripRecord.id))

        if status:
            query = query.where(TripRecord.status == status)
            count_query = count_query.where(TripRecord.status == status)

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await session.execute(query)
        records = result.scalars().all()
        return list(records), total


async def get_trip_by_id(trip_id: int) -> Optional[TripRecord]:
    async with async_session() as session:
        result = await session.execute(select(TripRecord).where(TripRecord.id == trip_id))
        return result.scalar_one_or_none()


async def delete_trip(trip_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(TripRecord).where(TripRecord.id == trip_id))
        record = result.scalar_one_or_none()
        if not record:
            return False
        await session.delete(record)
        await session.commit()
        logger.info(f"行程已删除: id={trip_id}")
        return True


async def update_trip_status(trip_id: int, status: str) -> Optional[TripRecord]:
    async with async_session() as session:
        result = await session.execute(select(TripRecord).where(TripRecord.id == trip_id))
        record = result.scalar_one_or_none()
        if not record:
            return None
        record.status = status
        await session.commit()
        await session.refresh(record)
        return record


async def search_trips(keyword: str, page: int = 1, page_size: int = 10) -> Tuple[List[TripRecord], int]:
    async with async_session() as session:
        pattern = f"%{keyword}%"
        condition = TripRecord.title.ilike(pattern) | TripRecord.city.ilike(pattern) | TripRecord.tags.ilike(pattern)

        count_query = select(func.count(TripRecord.id)).where(condition)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = select(TripRecord).where(condition).order_by(desc(TripRecord.created_at)).offset(offset).limit(page_size)
        result = await session.execute(query)
        records = result.scalars().all()
        return list(records), total


def record_to_dict(record: TripRecord) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "city": record.city,
        "start_date": record.start_date,
        "end_date": record.end_date,
        "travel_days": record.travel_days,
        "status": record.status,
        "budget_limit": record.budget_limit,
        "total_cost": record.total_cost,
        "companion_type": record.companion_type,
        "companion_count": record.companion_count,
        "tags": record.tags.split(",") if record.tags else [],
        "cover_image": record.cover_image,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def project_saved_narratives(raw: dict) -> dict:
    """Read-only view projection; do not rewrite the original stored JSON or extra fields."""
    from ..agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
    if not isinstance(raw, dict):
        return None
    try:
        plan = refresh_trip_descriptions(TripPlan.model_validate(raw))
    except (ValueError, TypeError):
        raw["trip_tagline"] = ""
        raw["overall_suggestions"] = "旧记录缺少可核对安排，请以原始行程数据为参考。"
        raw["weather_summary"] = ""
        raw.pop("narrative_source", None)
        days = raw.get("days")
        for day in days if isinstance(days, list) else []:
            if isinstance(day, dict):
                day.pop("description_source", None)
                day["description"] = "旧记录缺少可核对安排，未展示旧版说明。"
        return raw
    for original, day in zip(raw.get("days", []), plan.days):
        original.update(description=day.description, description_source=day.description_source,
                        pending_confirmations=day.pending_confirmations, travel_window=day.travel_window,
                        overnight_stay=day.overnight_stay, timeline_schedule=day.timeline_schedule)
    if plan.budget:
        raw["budget"] = {**(raw.get("budget") or {}), **plan.budget.model_dump(mode="json")}
    raw.update(trip_tagline=plan.trip_tagline, overall_suggestions=plan.overall_suggestions,
               weather_summary=plan.weather_summary, narrative_source=plan.narrative_source)
    return raw
