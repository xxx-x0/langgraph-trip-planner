"""User-confirmed memories are independent of plans and inferred preferences."""
from datetime import date, datetime
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def new_id() -> str:
    return uuid4().hex


class TravelMemoryRow(Base):
    __tablename__ = "travel_memories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    document_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class MemoryDate(MemoryModel):
    precision: Literal["unknown", "year", "month", "day"] = "unknown"
    start: str = Field(default="", max_length=10)
    end: str = Field(default="", max_length=10)

    @model_validator(mode="after")
    def dates(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if self.precision == "unknown":
            if self.start or self.end:
                raise ValueError("日期不确定时请留空，不会补造日期")
            return self
        length = {"year": 4, "month": 7, "day": 10}[self.precision]
        for value in (self.start, self.end or self.start):
            if len(value) != length:
                raise ValueError("请按所选精度填写日期")
            parsed = date.fromisoformat(value + {"year": "-01-01", "month": "-01", "day": ""}[self.precision])
            if parsed.year < 1900 or value > today.isoformat()[:length]:
                raise ValueError("旅行记录只记录已经发生的经历；日期须在1900年至今天之间")
        if self.end and self.end < self.start:
            raise ValueError("结束日期不能早于开始日期")
        return self


class Visit(MemoryModel):
    id: str = Field(default_factory=new_id, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    city: str = Field(min_length=1, max_length=100)
    country: str = Field(default="中国", max_length=100)
    region: str = Field(default="", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    when: MemoryDate = Field(default_factory=MemoryDate)

    @model_validator(mode="after")
    def coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("请同时填写经纬度，或一起留空稍后定位")
        return self


class Moment(MemoryModel):
    id: str = Field(default_factory=new_id, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=20000)
    place: str = Field(default="", max_length=200)
    visit_id: str | None = Field(default=None, max_length=64)
    when: MemoryDate = Field(default_factory=MemoryDate)
    deleted: bool = False


class PhotoEdit(MemoryModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    caption: str = Field(default="", max_length=2000)
    moment_id: str | None = Field(default=None, max_length=64)
    deleted: bool = False
    focal_x: float = Field(default=50, ge=0, le=100)
    focal_y: float = Field(default=50, ge=0, le=100)


class Photo(PhotoEdit):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str = Field(min_length=1, max_length=200)
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    size: int = Field(gt=0, le=20 * 1024 * 1024)
    width: int = Field(gt=0, le=30000)
    height: int = Field(gt=0, le=30000)


class SourceRef(MemoryModel):
    kind: Literal["single", "multi"]
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(max_length=200)
    basis: str = Field(pattern=r"^[a-f0-9]{64}$")


class MemoryDocument(MemoryModel):
    title: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=20000)
    when: MemoryDate = Field(default_factory=MemoryDate)
    visits: list[Visit] = Field(min_length=1, max_length=100)
    moments: list[Moment] = Field(default_factory=list, max_length=1000)
    photos: list[Photo] = Field(default_factory=list, max_length=500)
    cover_photo_id: str | None = Field(default=None, max_length=32)
    source: SourceRef | None = None
    deleted: bool = False

    @model_validator(mode="after")
    def references(self):
        for values in (self.visits, self.moments, self.photos):
            if len({v.id for v in values}) != len(values):
                raise ValueError("记录中的标识不能重复")
        visits = {v.id for v in self.visits}
        moments = {m.id for m in self.moments}
        if any(m.visit_id and m.visit_id not in visits for m in self.moments):
            raise ValueError("回忆关联的城市不存在，请先调整关联")
        if any(p.moment_id and p.moment_id not in moments for p in self.photos):
            raise ValueError("照片关联的片段不存在，请先调整关联")
        if self.cover_photo_id and not any(p.id == self.cover_photo_id and not p.deleted for p in self.photos):
            raise ValueError("封面须选择未删除的照片")
        if not self.title:
            self.title = "、".join(dict.fromkeys(v.city for v in self.visits))[:140] + "的记忆"
        return self


class MemoryInput(MemoryModel):
    title: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=20000)
    when: MemoryDate = Field(default_factory=MemoryDate)
    visits: list[Visit] = Field(min_length=1, max_length=100)
    moments: list[Moment] = Field(default_factory=list, max_length=1000)


class CreateMemory(MemoryInput):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source: SourceRef | None = None
    confirmed_visit_ids: list[str] = Field(default_factory=list, max_length=100)


class EditMemory(MemoryInput):
    revision: int = Field(ge=1)
    operation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    photos: list[PhotoEdit] = Field(default_factory=list, max_length=500)
    cover_photo_id: str | None = Field(default=None, max_length=32)


class MemoryRevision(MemoryModel):
    revision: int = Field(ge=1)


class TrashMemory(MemoryRevision):
    deleted: bool


class BackupRecord(MemoryModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    document: MemoryDocument


class BackupManifest(MemoryModel):
    format: Literal["lets-go-travel-memories"]
    version: Literal[1]
    exported_at: datetime
    records: list[BackupRecord] = Field(max_length=2000)


class RestoreConfirm(MemoryModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    conflicts: Literal["copy", "skip"] = "copy"
