import pytest
from sqlalchemy import inspect

from app.database import engine, init_db
from app.models.db_models import TripDraft


@pytest.mark.asyncio
async def test_trip_draft_table_created_by_init_db():
    await init_db()
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "trip_drafts" in tables


@pytest.mark.asyncio
async def test_trip_draft_columns_match_orm():
    async with engine.connect() as conn:
        columns = await conn.run_sync(lambda c: inspect(c).get_columns("trip_drafts"))
    col_names = {c["name"] for c in columns}
    expected = {
        "id", "user_id", "status",
        "request_json", "selected_attractions_json",
        "macro_plan_json", "clusters_data_json",
        "hotels_by_day_json", "dining_pool_json",
        "weather_info_json", "days_detail_json",
        "trip_tagline", "overall_suggestions", "weather_summary",
        "finalized_trip_id",
        "created_at", "updated_at", "finalized_at",
    }
    assert expected.issubset(col_names), f"缺字段: {expected - col_names}"
