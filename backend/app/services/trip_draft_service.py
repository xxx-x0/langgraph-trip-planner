"""草稿 CRUD 服务"""
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models.db_models import TripDraft
from ..models.schemas import (
    TripRequest, MacroPlan, DayDetail, DiscoveredAttraction,
    DiningPoolDay, WeatherInfo,
)
from ..logger import get_logger

logger = get_logger(__name__)


def _dump_pydantic_list(items: List[Any]) -> str:
    """把 List[BaseModel] 或 List[dict] 序列化为 JSON 文本"""
    out = []
    for it in items:
        if hasattr(it, "model_dump"):
            out.append(it.model_dump(mode="json"))
        elif hasattr(it, "dict"):
            out.append(it.dict())
        else:
            out.append(it)
    return json.dumps(out, ensure_ascii=False, default=str)


async def create_draft(
    *,
    user_id: str,
    request: TripRequest,
    selected_attractions: List[Any],
    macro_plan: MacroPlan,
    clusters_data: List[Any],
    hotels_by_day: List[Any],
    dining_pool: List[DiningPoolDay] | List[dict],
    weather_info: List[WeatherInfo] | List[dict],
) -> str:
    draft_id = uuid.uuid4().hex
    travel_days = request.travel_days
    days_detail_init = [None] * travel_days

    record = TripDraft(
        id=draft_id,
        user_id=user_id,
        status="skeleton",
        request_json=request.model_dump_json(),
        selected_attractions_json=_dump_pydantic_list(selected_attractions),
        macro_plan_json=macro_plan.model_dump_json(),
        clusters_data_json=json.dumps(clusters_data, ensure_ascii=False, default=str),
        hotels_by_day_json=json.dumps(hotels_by_day, ensure_ascii=False, default=str),
        dining_pool_json=_dump_pydantic_list(dining_pool),
        weather_info_json=_dump_pydantic_list(weather_info),
        days_detail_json=json.dumps(days_detail_init),
    )
    async with async_session() as session:
        session.add(record)
        await session.commit()
    logger.info(f"草稿已创建: id={draft_id}, user={user_id}, days={travel_days}")
    return draft_id


async def get_draft(draft_id: str) -> Optional[TripDraft]:
    async with async_session() as session:
        return await session.get(TripDraft, draft_id)


async def patch_day_detail(
    draft_id: str, day_index: int, day_detail: DayDetail
) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        days = json.loads(record.days_detail_json)
        if day_index < 0 or day_index >= len(days):
            raise IndexError(f"day_index {day_index} out of range (len={len(days)})")
        days[day_index] = day_detail.model_dump(mode="json")
        record.days_detail_json = json.dumps(days, ensure_ascii=False, default=str)
        await session.commit()


async def update_synthesizer_fields(
    draft_id: str, *, trip_tagline: str, overall_suggestions: str, weather_summary: str
) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        record.trip_tagline = trip_tagline
        record.overall_suggestions = overall_suggestions
        record.weather_summary = weather_summary
        await session.commit()


async def mark_finalized(draft_id: str, *, trip_id: int) -> None:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        record.status = "finalized"
        record.finalized_trip_id = trip_id
        record.finalized_at = datetime.utcnow()
        await session.commit()


async def delete_draft(draft_id: str) -> bool:
    async with async_session() as session:
        record = await session.get(TripDraft, draft_id)
        if record is None:
            return False
        await session.delete(record)
        await session.commit()
        return True


async def delete_expired(*, days: int = 30) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session() as session:
        stmt = (
            delete(TripDraft)
            .where(TripDraft.updated_at < cutoff)
            .where(TripDraft.status != "finalized")
        )
        result = await session.execute(stmt)
        await session.commit()
        deleted = result.rowcount or 0
        if deleted > 0:
            logger.info(f"TTL 清理: 删除了 {deleted} 个过期草稿")
        return deleted
