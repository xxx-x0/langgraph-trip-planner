"""SQLAlchemy ORM 模型"""

from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, Index
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
