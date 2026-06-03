"""SQLAlchemy ORM 模型"""

from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class TripRecord(Base):
    __tablename__ = "trip_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[str] = mapped_column(String(20), nullable=False)
    end_date: Mapped[str] = mapped_column(String(20), nullable=False)
    travel_days: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_data: Mapped[str] = mapped_column(Text, nullable=False)
    request_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    budget_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost: Mapped[int] = mapped_column(Integer, default=0)
    companion_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    companion_count: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_trip_records_city", "city"),
        Index("idx_trip_records_status", "status"),
        Index("idx_trip_records_created_at", "created_at"),
    )


class UserPreferenceRecord(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    preference_data: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="inferred")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_preferences_user_id", "user_id"),
    )


class AttractionCache(Base):
    __tablename__ = "attractions_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    poi_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    amap_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    ticket_price: Mapped[str | None] = mapped_column(String(50), nullable=True)
    open_hours: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("city", "name", name="uq_attractions_city_name"),
        Index("idx_attractions_city", "city"),
        Index("idx_attractions_city_category", "city", "category"),
    )


class TripDraft(Base):
    """草稿表：保存骨架阶段产物 + 详细阶段渐进装配的每日 DayDetail"""
    __tablename__ = "trip_drafts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # uuid4 hex
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="skeleton")
    # skeleton / assembling / finalized / expired

    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    selected_attractions_json: Mapped[str] = mapped_column(Text, nullable=False)

    macro_plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    clusters_data_json: Mapped[str] = mapped_column(Text, nullable=False)
    hotels_by_day_json: Mapped[str] = mapped_column(Text, nullable=False)
    dining_pool_json: Mapped[str] = mapped_column(Text, nullable=False)
    weather_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    days_detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    trip_tagline: Mapped[str] = mapped_column(String(200), default="")
    overall_suggestions: Mapped[str] = mapped_column(Text, default="")
    weather_summary: Mapped[str] = mapped_column(String(200), default="")

    finalized_trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_drafts_user_status", "user_id", "status"),
        Index("idx_drafts_updated", "updated_at"),
    )
