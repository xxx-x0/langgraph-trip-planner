"""User-owned memory aggregates, CAS writes and explicitly confirmed source imports."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from ..database import async_session
from ..models.db_models import TripRecord, TripDraft
from ..models.travel_memory import (CreateMemory, EditMemory, MemoryDocument,
                                   Photo, TravelMemoryRow, Visit)
from . import memory_media as media


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(dump(value).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def response(row: TravelMemoryRow) -> dict:
    return dict(id=row.id, revision=row.revision, created_at=row.created_at,
                updated_at=row.updated_at, document=json.loads(row.document_json))


def valid_document(value) -> MemoryDocument:
    try:
        return MemoryDocument.model_validate(value)
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(e["msg"] for e in exc.errors())[:600]) from None


async def require(session, record_id: str) -> TravelMemoryRow:
    row = await session.get(TravelMemoryRow, record_id)
    if not row:
        raise HTTPException(404, "旅行记录不存在")
    return row


def editable(row, revision):
    if row.revision != revision:
        raise HTTPException(409, "这份回忆已在别处更新，本次修改尚未保存；本机编辑仍保留，请核对最新版本")
    if json.loads(row.document_json)["deleted"]:
        raise HTTPException(409, "这份回忆已移入回收站，请先恢复")


def write_row(row, document, operation_id=None, operation_hash=None):
    row.document_json = dump(document.model_dump(mode="json"))
    row.revision += 1
    row.updated_at = now()
    row.operation_id = operation_id
    row.operation_hash = operation_hash


async def listing():
    async with async_session() as session:
        rows = (await session.execute(select(TravelMemoryRow).order_by(TravelMemoryRow.updated_at.desc(), TravelMemoryRow.id))).scalars().all()
        return [response(row) for row in rows]


async def get(record_id):
    async with async_session() as session:
        return response(await require(session, record_id))


CATALOG = Path(__file__).parent.parent / "data" / "memory_cities.json"


@lru_cache(maxsize=1)
def city_catalog():
    return json.loads(CATALOG.read_text())


def cities(query=""):
    entries = city_catalog()
    query = query.strip().casefold()
    matches = [c for c in entries if not query or query in " ".join([c["city"], c["region"], c["country"], c.get("search", "")]).casefold()]
    if query:
        matches.sort(key=lambda c: c["city"].casefold().removesuffix("市") != query.removesuffix("市"))
    return matches[:40]


def source_city(name, visit_id, start="", end=""):
    entry = next((c for c in cities(name.removesuffix("市")) if c["city"].removesuffix("市") == name.removesuffix("市")), {})
    # Plan dates are suggestions only. The create form starts with unknown actual dates.
    return dict(id=visit_id, city=entry.get("city", name), country=entry.get("country", ""),
                region=entry.get("region", ""), latitude=entry.get("latitude"), longitude=entry.get("longitude"),
                when={"precision": "unknown", "start": "", "end": ""}, planned_start=start, planned_end=end)


async def read_source(session, kind, source_id):
    if kind == "single":
        if not str(source_id).isdigit():
            raise HTTPException(404, "来源行程不存在")
        row = await session.get(TripRecord, int(source_id))
        if not row:
            raise HTTPException(404, "来源行程不存在")
        return dict(kind=kind, id=str(row.id), title=row.title,
                    basis=digest([row.title, row.city, row.start_date, row.end_date, row.plan_data]),
                    visits=[source_city(row.city, "single-city", row.start_date, row.end_date)])
    if kind == "multi":
        row = await session.get(TripDraft, source_id)
        if not row:
            raise HTTPException(404, "来源旅行不存在")
        document = json.loads(row.request_json)
        if document.get("kind") != "multi_city_v1" or document.get("status") != "saved":
            raise HTTPException(409, "请先保存整趟旅行版本，再补记实际经历")
        plan = document["plan"]
        return dict(kind=kind, id=row.id, title=plan["title"], basis=digest(document),
                    visits=[source_city(s["city"]["name"], s["id"], s["start_date"], s["end_date"]) for s in plan["stops"]])
    raise HTTPException(404, "未知的行程来源")


async def source_detail(kind, source_id):
    async with async_session() as session:
        return await read_source(session, kind, source_id)


async def sources(query="", offset=0, limit=30):
    # Read only: never touches planning graphs, preference services or source snapshots.
    async with async_session() as session:
        singles = (await session.execute(select(TripRecord).order_by(TripRecord.created_at.desc()))).scalars().all()
        multis = (await session.execute(select(TripDraft).where(TripDraft.status == "multi_saved"))).scalars().all()
        items = [dict(kind="single", id=str(r.id), title=r.title, cities=[r.city],
                      start=r.start_date, end=r.end_date, updated=str(r.updated_at)) for r in singles]
        for row in multis:
            d = json.loads(row.request_json)
            if d.get("kind") == "multi_city_v1" and d.get("status") == "saved":
                p = d["plan"]
                items.append(dict(kind="multi", id=row.id, title=p["title"], cities=[s["city"]["name"] for s in p["stops"]],
                                  start=p["start_date"], end=p["end_date"], updated=str(row.updated_at)))
        if query:
            items = [i for i in items if query.casefold() in (i["title"] + " ".join(i["cities"])).casefold()]
        items.sort(key=lambda i: i["updated"], reverse=True)
        return dict(items=items[offset:offset + limit], total=len(items))


async def create(body: CreateMemory):
    data = body.model_dump(mode="json", exclude={"id", "source", "confirmed_visit_ids"})
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        existing = await session.get(TravelMemoryRow, body.id)
        op_hash = digest(body.model_dump(mode="json"))
        if existing:
            if existing.operation_hash == op_hash:
                return response(existing)
            raise HTTPException(409, "这条记录已保存，请打开现有记录继续编辑")
        if body.source:
            source = await read_source(session, body.source.kind, body.source.id)
            if source["basis"] != body.source.basis:
                raise HTTPException(409, "来源计划已变化，请重新选择并核对实际到访")
            ids = set(body.confirmed_visit_ids)
            candidates = {v["id"]: v for v in source["visits"]}
            if not ids or not ids.issubset(candidates) or ids != {v.id for v in body.visits}:
                raise HTTPException(422, "请明确勾选实际去过的城市；未确认的城市不会进入足迹")
            if any(v.city != candidates[v.id]["city"] for v in body.visits):
                raise HTTPException(422, "所选城市与来源不符，请单独新增实际到访")
            data["source"] = {k: source[k] for k in ("kind", "id", "title", "basis")}
        document = valid_document(data)
        row = TravelMemoryRow(id=body.id, revision=1, document_json=dump(document.model_dump(mode="json")),
                              created_at=now(), updated_at=now(), operation_id=body.id, operation_hash=op_hash)
        session.add(row)
        await session.commit()
        return response(row)


async def update(record_id, body: EditMemory):
    op_hash = digest(body.model_dump(mode="json"))
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        row = await require(session, record_id)
        if row.operation_id == body.operation_id and row.operation_hash == op_hash:
            return response(row)
        editable(row, body.revision)
        previous = json.loads(row.document_json)
        photos = {p["id"]: p for p in previous["photos"]}
        if len({p.id for p in body.photos}) != len(body.photos) or {p.id for p in body.photos} != set(photos):
            raise HTTPException(409, "照片列表已变化，请刷新核对；移除照片请先移入照片回收站")
        data = body.model_dump(mode="json", exclude={"revision", "operation_id", "photos"})
        data.update(source=previous["source"], deleted=False,
                    photos=[{**photos[p.id], **p.model_dump(mode="json")} for p in body.photos])
        document = valid_document(data)
        write_row(row, document, body.operation_id, op_hash)
        await session.commit()
        return response(row)


async def trash(record_id, revision, deleted):
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        row = await require(session, record_id)
        doc = valid_document(json.loads(row.document_json))
        if doc.deleted == deleted:
            return response(row)
        if row.revision != revision:
            raise HTTPException(409, "记录已变化，请刷新后重试")
        doc.deleted = deleted
        write_row(row, doc)
        await session.commit()
        return response(row)


async def upload(record_id, revision, photo_id, filename, data):
    metadata, preview = await asyncio.to_thread(media.inspect_image, data)
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        row = await require(session, record_id)
        doc = valid_document(json.loads(row.document_json))
        existing = next((p for p in doc.photos if p.id == photo_id), None)
        if existing:
            if existing.sha256 != metadata["sha256"]:
                raise HTTPException(409, "上传标识已被其他照片使用")
            return response(row)
        editable(row, revision)
        if len(doc.photos) >= 500:
            raise HTTPException(422, "每次旅行最多500张照片（含回收站）")
        photo = Photo(id=photo_id, filename=media.safe_filename(filename), **metadata)
        await asyncio.to_thread(media.store_photo, data, metadata, preview)
        doc.photos.append(photo)
        if not doc.cover_photo_id:
            doc.cover_photo_id = photo.id
        write_row(row, doc)
        await session.commit()
        return response(row)


async def photo_file(record_id, photo_id, thumbnail):
    row = await get(record_id)
    photo = next((p for p in row["document"]["photos"] if p["id"] == photo_id), None)
    if not photo:
        raise HTTPException(404, "照片不存在")
    path = media.blob_path(photo["sha256"], thumbnail)
    if not path.is_file():
        if thumbnail and media.blob_path(photo["sha256"]).is_file():
            data = await asyncio.to_thread(media.checked_original, photo["sha256"])
            metadata, preview = await asyncio.to_thread(media.inspect_image, data)
            await asyncio.to_thread(media.store_photo, data, metadata, preview)
        else:
            raise HTTPException(404, "照片原件缺失，请从备份恢复")
    return path, photo
