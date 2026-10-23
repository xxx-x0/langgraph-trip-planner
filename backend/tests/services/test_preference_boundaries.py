"""Generated observations must not overwrite deliberately saved user choices."""
import uuid

import pytest
from sqlalchemy import select

from app.database import async_session, init_db
from app.models.db_models import UserPreferenceRecord
from app.models.schemas import TripRequest, UserPreference
from app.services import preferences_service
from app.agents.langgraph_agent.nodes.preferences import save_preferences_node


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["finalization_transaction", "legacy_graph"])
async def test_observations_leave_explicit_record_unchanged(writer):
    await init_db()
    user = "explicit-" + uuid.uuid4().hex
    preferred = UserPreference(user_id=user, preferred_cuisines=["明确选择的菜系"], total_trips=7,
                               preferred_hotel_types=["经济型酒店"])
    saved = await preferences_service.save_preferences(user, preferred, source="explicit", confidence=1)
    before = (saved.preference_data, saved.source, saved.confidence, saved.updated_at)
    observation = {"preferred_cuisines": ["模型生成的菜系"], "preferred_attractions_per_day": 9}
    if writer == "finalization_transaction":
        async with async_session() as session:
            await preferences_service.apply_extracted_preferences(session, user, observation, "新城市")
            await session.commit()
    else:
        await save_preferences_node({"user_id": user, "extracted_preferences": observation,
            "request": TripRequest(city="新城市", start_date="2026-10-15", end_date="2026-10-15",
                                   travel_days=1, transportation="公共交通", accommodation="经济型酒店")})
    async with async_session() as session:
        after = (await session.execute(select(UserPreferenceRecord).where(
            UserPreferenceRecord.user_id == user))).scalar_one()
        assert (after.preference_data, after.source, after.confidence, after.updated_at) == before


def test_merging_inactive_observations_does_not_mutate_loaded_record():
    existing = UserPreference(user_id="test", preferred_cuisines=["旧观察"], cities_visited=["旧城市"])
    merged = preferences_service.merge_preferences(existing, {"preferred_cuisines": ["新观察"]})
    assert merged.preferred_cuisines == ["旧观察", "新观察"]
    assert existing.preferred_cuisines == ["旧观察"]
