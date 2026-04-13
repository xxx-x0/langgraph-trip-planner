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


async def save_trip(plan: TripPlan, request: Optional[TripRequest] = None) -> TripRecord:
    async with async_session() as session:
        plan_dict = plan.model_dump() if hasattr(plan, 'model_dump') else plan.dict()
        request_dict = None
        if request:
            request_dict = request.model_dump() if hasattr(request, 'model_dump') else request.dict()

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
