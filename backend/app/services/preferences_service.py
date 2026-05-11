"""用户偏好持久化服务"""

import json
from typing import Optional
from sqlalchemy import select
from datetime import datetime

from ..database import async_session
from ..models.db_models import UserPreferenceRecord
from ..models.schemas import UserPreference
from ..logger import get_logger

logger = get_logger(__name__)


async def load_preferences(user_id: str) -> Optional[UserPreference]:
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferenceRecord)
            .where(UserPreferenceRecord.user_id == user_id)
            .order_by(UserPreferenceRecord.updated_at.desc())
        )
        record = result.scalar_one_or_none()
        if not record:
            return None
        try:
            data = json.loads(record.preference_data)
            return UserPreference(**data)
        except Exception as e:
            logger.warning(f"加载用户偏好失败(user_id={user_id}): {e}")
            return None


async def save_preferences(user_id: str, preferences: UserPreference, source: str = "inferred", confidence: float = 0.5) -> UserPreferenceRecord:
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferenceRecord)
            .where(UserPreferenceRecord.user_id == user_id)
            .order_by(UserPreferenceRecord.updated_at.desc())
        )
        record = result.scalar_one_or_none()

        pref_dict = preferences.model_dump()
        pref_json = json.dumps(pref_dict, ensure_ascii=False)

        if record:
            record.preference_data = pref_json
            record.source = source
            record.confidence = confidence
            record.updated_at = datetime.utcnow()
        else:
            record = UserPreferenceRecord(
                user_id=user_id,
                preference_data=pref_json,
                source=source,
                confidence=confidence,
            )
            session.add(record)

        await session.commit()
        await session.refresh(record)
        logger.info(f"用户偏好已保存: user_id={user_id}, source={source}")
        return record


async def delete_preferences(user_id: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return False
        await session.delete(record)
        await session.commit()
        logger.info(f"用户偏好已删除: user_id={user_id}")
        return True


def merge_preferences(existing: UserPreference, extracted: dict) -> UserPreference:
    """合并偏好：新偏好与旧偏好加权融合"""
    merged = existing.model_copy()

    for key, new_values in extracted.items():
        if key.startswith("preferred_") and isinstance(new_values, list):
            existing_values = getattr(merged, key, [])
            if isinstance(existing_values, list):
                seen = set(existing_values)
                for v in new_values:
                    if v not in seen:
                        existing_values.append(v)
                        seen.add(v)
                setattr(merged, key, existing_values)

    if "preferred_attractions_per_day" in extracted:
        new_val = extracted["preferred_attractions_per_day"]
        old_val = merged.preferred_attractions_per_day
        if merged.total_trips > 0:
            merged.preferred_attractions_per_day = round(
                (old_val * merged.total_trips + new_val) / (merged.total_trips + 1)
            )
        else:
            merged.preferred_attractions_per_day = new_val

    if "preferred_meal_price_range" in extracted:
        new_range = extracted["preferred_meal_price_range"]
        if len(new_range) == 2:
            old_range = merged.preferred_meal_price_range
            merged.preferred_meal_price_range = [
                round((old_range[0] + new_range[0]) / 2),
                round((old_range[1] + new_range[1]) / 2),
            ]

    if "preferred_hotel_price_range" in extracted:
        new_range = extracted["preferred_hotel_price_range"]
        if len(new_range) == 2:
            old_range = merged.preferred_hotel_price_range
            merged.preferred_hotel_price_range = [
                round((old_range[0] + new_range[0]) / 2),
                round((old_range[1] + new_range[1]) / 2),
            ]

    return merged


def format_preference_hint(prefs: UserPreference) -> str:
    """将偏好格式化为提示文本"""
    hints = []
    if prefs.preferred_hotel_types:
        hints.append(f"用户历史偏好酒店类型: {', '.join(prefs.preferred_hotel_types)}")
    if prefs.preferred_cuisines:
        hints.append(f"用户历史偏好菜系: {', '.join(prefs.preferred_cuisines)}")
    if prefs.preferred_attraction_categories:
        hints.append(f"用户历史偏好景点类型: {', '.join(prefs.preferred_attraction_categories)}")
    if prefs.budget_range and len(prefs.budget_range) == 2:
        hints.append(f"用户历史预算范围: {prefs.budget_range[0]}-{prefs.budget_range[1]}元")
    if prefs.cities_visited:
        hints.append(f"用户曾去过: {', '.join(prefs.cities_visited[-5:])}")
    if prefs.preferred_attractions_per_day:
        hints.append(f"用户偏好每天游览{prefs.preferred_attractions_per_day}个景点")
    if hints:
        return "【用户历史偏好参考】\n" + "\n".join(hints)
    return ""
