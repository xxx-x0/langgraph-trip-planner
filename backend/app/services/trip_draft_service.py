"""草稿 CRUD 服务"""
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from weakref import WeakValueDictionary
from datetime import datetime, timedelta
from typing import List, Optional, Any

from sqlalchemy import select, delete, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models.db_models import TripDraft, TripRecord
from ..models.schemas import (
    TripRequest, MacroPlan, DayDetail, DiscoveredAttraction,
    DiningPoolDay, WeatherInfo, TripPlan,
)
from ..logger import get_logger

logger = get_logger(__name__)

_UNSET = object()

_creation = ContextVar('draft_creation', default=None)
_creation_locks = WeakValueDictionary()


@asynccontextmanager
async def creation_request(user_id, request_id, fingerprint):
    if not request_id:
        yield
        return
    key = (user_id, request_id)
    lock = _creation_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _creation_locks[key] = lock
    async with lock:
        token = _creation.set((request_id, fingerprint))
        try:
            yield
        finally:
            _creation.reset(token)


async def _find_creation(session, user_id, request_id, fingerprint):
    result = await session.execute(select(TripDraft).where(
        TripDraft.user_id == user_id,
        func.json_extract(TripDraft.request_json, '$._creation_request_id') == request_id))
    record = result.scalar_one_or_none()
    if record and json.loads(record.request_json).get('_creation_fingerprint') != fingerprint:
        raise ValueError('同一规划请求的输入已改变，请重新发起规划')
    return record


async def find_created_draft(user_id, request_id, fingerprint):
    if not request_id:
        return None
    async with async_session() as session:
        return await _find_creation(session, user_id, request_id, fingerprint)


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

    request_data = request.model_dump(mode='json')
    creation = _creation.get()
    if creation:
        request_data.update(_creation_request_id=creation[0], _creation_fingerprint=creation[1])
    record = TripDraft(
        id=draft_id,
        user_id=user_id,
        status="skeleton",
        request_json=json.dumps(request_data, ensure_ascii=False),
        selected_attractions_json=_dump_pydantic_list(selected_attractions),
        macro_plan_json=macro_plan.model_dump_json(),
        clusters_data_json=json.dumps(clusters_data, ensure_ascii=False, default=str),
        hotels_by_day_json=json.dumps(hotels_by_day, ensure_ascii=False, default=str),
        dining_pool_json=_dump_pydantic_list(dining_pool),
        weather_info_json=_dump_pydantic_list(weather_info),
        days_detail_json=json.dumps(days_detail_init),
    )
    async with async_session() as session:
        if creation:
            await session.execute(text('BEGIN IMMEDIATE'))
            existing = await _find_creation(session, user_id, *creation)
            if existing:
                return existing.id
        session.add(record)
        await session.commit()
    logger.info(f"草稿已创建: id={draft_id}, user={user_id}, days={travel_days}")
    return draft_id


async def get_draft(draft_id: str) -> Optional[TripDraft]:
    async with async_session() as session:
        return await session.get(TripDraft, draft_id)


async def patch_day_detail(
    draft_id: str, day_index: int, day_detail: DayDetail, *, expected_day: Any = _UNSET, expected_request: Any = _UNSET
) -> None:
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError(f"draft {draft_id} not found")
        if record.status == "finalized":
            raise DraftChangedDuringFinalize("草稿已定稿，本次修改未保存，请查看已保存行程")
        if expected_request is not _UNSET and record.request_json != expected_request:
            raise DraftChangedDuringFinalize("抵离交通已更新，本次结果未保存，请加载最新草稿")
        days = json.loads(record.days_detail_json)
        if day_index < 0 or day_index >= len(days):
            raise IndexError(f"day_index {day_index} out of range (len={len(days)})")
        if expected_day is not _UNSET and days[day_index] != expected_day:
            raise DraftChangedDuringFinalize("该天安排已被更新，本次结果未保存；请加载最新草稿后重试")
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


class DraftChangedDuringFinalize(ValueError):
    pass


async def read_finalized_trip(record: TripDraft) -> tuple[TripPlan, int]:
    async with async_session() as session:
        trip = await session.get(TripRecord, record.finalized_trip_id)
        if trip is None:
            raise ValueError("已定稿草稿的历史记录不存在，请检查或恢复历史记录")
        from ..agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
        return refresh_trip_descriptions(TripPlan.model_validate_json(trip.plan_data)), trip.id


async def persist_finalized_trip(draft_id: str, plan: TripPlan, request: TripRequest,
                                 expected_days_detail: str, extracted: dict | None, *, expected_request: str | None = None) -> tuple[TripPlan, int]:
    """One durable commit for history, draft and preferences, using existing tables."""
    from .trip_history_service import build_trip_record
    from ..agents.langgraph_agent.assemble.narrative import refresh_trip_descriptions
    from .preferences_service import apply_extracted_preferences
    async with async_session() as session:
        # SQLite's write reservation serializes the check and insert across workers.
        await session.execute(text("BEGIN IMMEDIATE"))
        record = await session.get(TripDraft, draft_id)
        if record is None:
            raise ValueError("草稿不存在")
        if record.status == "finalized":
            trip = await session.get(TripRecord, record.finalized_trip_id)
            if trip is None:
                raise ValueError("已定稿草稿的历史记录不存在")
            return refresh_trip_descriptions(TripPlan.model_validate_json(trip.plan_data)), trip.id
        if (expected_request is not None and record.request_json != expected_request) or record.days_detail_json != expected_days_detail:
            raise DraftChangedDuringFinalize("定稿期间草稿已更新，本次未保存；请核对最新草稿后重试")
        plan = refresh_trip_descriptions(plan.model_copy(deep=True))
        trip = build_trip_record(plan, request)
        session.add(trip)
        await session.flush()
        record.status = "finalized"
        record.finalized_trip_id = trip.id
        record.finalized_at = datetime.utcnow()
        record.trip_tagline = plan.trip_tagline
        record.overall_suggestions = plan.overall_suggestions
        record.weather_summary = plan.weather_summary
        await apply_extracted_preferences(session, record.user_id, extracted, request.city)
        await session.commit()
        return plan, trip.id


async def patch_dining_pool(draft_id, day_index, pool, *, expected_day, expected_pool, expected_request=None):
    """Refresh alternatives atomically; never replace the user's saved meals."""
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        record = await session.get(TripDraft, draft_id)
        if record is None or record.status == 'finalized':
            raise DraftChangedDuringFinalize('草稿已定稿或不存在，本次餐厅查询未保存')
        days = json.loads(record.days_detail_json)
        pools = json.loads(record.dining_pool_json)
        old_pool = pools[day_index] if day_index < len(pools) else {}
        if (expected_request is not None and record.request_json != expected_request) or days[day_index] != expected_day or old_pool != expected_pool:
            raise DraftChangedDuringFinalize('安排或备选已更新，本次餐厅查询未保存；请重新查询')
        while len(pools) <= day_index: pools.append({})
        pools[day_index] = pool
        record.dining_pool_json = json.dumps(pools, ensure_ascii=False)
        await session.commit()


async def replace_journey(draft_id, request, expected_request, expected_days, *, details=None):
    async with async_session() as session:
        await session.execute(text('BEGIN IMMEDIATE'))
        record = await session.get(TripDraft, draft_id)
        if record is None or record.status == 'finalized' or record.request_json != expected_request or record.days_detail_json != expected_days:
            raise DraftChangedDuringFinalize('草稿已变化，本次交通修改未保存，请重新预览')
        data=json.loads(record.request_json)
        data['journey']=request.journey.model_dump(mode='json') if request.journey else None
        if details is not None:
            record.days_detail_json=json.dumps([d.model_dump(mode='json') if d else None for d in details],ensure_ascii=False)
        record.request_json=json.dumps(data,ensure_ascii=False)
        await session.commit()
