"""Bounded ZIP backup, non-destructive preview/restore, no archive extraction."""
import asyncio
import hashlib
import json
import re
import stat
import time
import zipfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from ..database import async_session
from ..models.travel_memory import BackupManifest, TravelMemoryRow
from . import memory_media as media
from . import travel_memories as svc

MAX_BACKUP_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
PREVIEW_TTL = 3600


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def work_dir() -> Path:
    folder = media.storage_root() / "transfers"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cleanup():
    for path in work_dir().iterdir():
        if re.fullmatch(r"[a-f0-9]{32}\.(zip|json)", path.name) and path.stat().st_mtime < time.time() - PREVIEW_TTL:
            path.unlink(missing_ok=True)


def _export(records):
    if len(records) > 2000:
        raise HTTPException(413, "记录数量超过本版2000条备份上限，未生成部分备份；请保留整个数据目录")
    manifest = BackupManifest.model_validate(dict(format="lets-go-travel-memories", version=1,
                                                   exported_at=svc.now(), records=records))
    photos = {p.sha256 for r in manifest.records for p in r.document.photos}
    raw = manifest.model_dump_json().encode()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise HTTPException(413, "记录规模超过本版备份上限，请保留整个数据目录并联系维护者扩容")
    path = work_dir() / (uuid4().hex + ".zip")
    try:
        total = len(raw)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("manifest.json", raw)
            for sha in sorted(photos):
                data = media.checked_original(sha)
                total += len(data)
                if total > MAX_BACKUP_BYTES - 1024 * 1024:
                    raise HTTPException(413, "备份超过512 MB上限；本次未生成部分备份，请保留整个数据目录")
                archive.writestr("media/" + sha, data)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


async def export():
    records = await svc.listing()
    await asyncio.to_thread(cleanup)
    return await asyncio.to_thread(_export, records)


def inspect_archive(path):
    """Validate every byte and relationship before staging a restorable preview."""
    try:
        if path.stat().st_size > MAX_BACKUP_BYTES:
            raise HTTPException(413, "备份最多512 MB")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 10001 or len(names) != len(set(names)):
                raise ValueError("重复文件或文件数量过多")
            if any(i.flag_bits & 1 or stat.S_ISLNK(i.external_attr >> 16) or i.is_dir() for i in infos):
                raise ValueError("不支持加密文件、目录或链接")
            if any(n != "manifest.json" and not re.fullmatch(r"media/[a-f0-9]{64}", n) for n in names):
                raise ValueError("备份包含非预期路径")
            if sum(i.file_size for i in infos) > MAX_BACKUP_BYTES:
                raise ValueError("解压后的备份过大")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise ValueError("清单过大")
            manifest = BackupManifest.model_validate_json(archive.read(manifest_info))
            if len({r.id for r in manifest.records}) != len(manifest.records):
                raise ValueError("备份记录标识重复")
            expected = {p.sha256 for r in manifest.records for p in r.document.photos}
            if set(names) != {"manifest.json"} | {"media/" + h for h in expected}:
                raise ValueError("照片缺失或存在未关联文件")
            metadata = {}
            for sha in expected:
                info = archive.getinfo("media/" + sha)
                if info.file_size > media.MAX_PHOTO_BYTES:
                    raise ValueError("单张照片过大")
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() != sha:
                    raise ValueError("照片校验失败")
                metadata[sha], _ = media.inspect_image(data)
            for r in manifest.records:
                for p in r.document.photos:
                    if any(getattr(p, key) != metadata[p.sha256][key] for key in ("media_type", "width", "height", "size")):
                        raise ValueError("照片元数据与原件不符")
            return manifest
    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, RuntimeError, ValidationError):
        raise HTTPException(422, "备份无效、损坏或版本不支持；没有修改任何记录") from None


def proposed(manifest, existing):
    current = {r["id"]: r for r in existing}
    items = []
    for entry in manifest.records:
        payload = entry.document.model_dump(mode="json")
        old = current.get(entry.id)
        copy_id = uuid5(NAMESPACE_URL, "travel-memory-restore:" + entry.id + ":" + svc.digest(payload)).hex
        status = "new" if not old else ("identical" if old["document"] == payload else "conflict")
        if status == "conflict" and copy_id in current:
            status = "already_restored"
        items.append(dict(id=entry.id, title=payload["title"], deleted=payload["deleted"], status=status,
                          copy_id=copy_id, photos=len(payload["photos"])))
    return items


async def preview(path):
    manifest = await asyncio.to_thread(inspect_archive, path)
    existing = await svc.listing()
    items = proposed(manifest, existing)
    token = path.stem
    media.atomic_file(work_dir() / (token + ".json"), svc.dump(dict(
        basis=svc.digest(existing), created=time.time(), sha256=await asyncio.to_thread(file_digest, path)
    )).encode())
    repairs = 0
    for sha in {p.sha256 for r in manifest.records for p in r.document.photos}:
        try:
            await asyncio.to_thread(media.checked_original, sha)
        except HTTPException:
            repairs += 1
    return dict(token=token, items=items, photo_files_to_restore=repairs,
                counts={k: sum(i["status"] == k for i in items) for k in ("new", "identical", "conflict", "already_restored")},
                expires_in_seconds=PREVIEW_TTL)


def install_archive_media(path, manifest):
    with zipfile.ZipFile(path) as archive:
        for sha in {p.sha256 for r in manifest.records for p in r.document.photos}:
            data = archive.read("media/" + sha)
            _, thumbnail = media.inspect_image(data)
            # Exact content hashes allow explicit recovery of missing/corrupt local originals.
            target = media.blob_path(sha)
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                media.atomic_file(target, data)
            media.atomic_file(media.blob_path(sha, True), thumbnail)


async def restore(token, conflicts):
    path = work_dir() / (token + ".zip")
    meta_path = work_dir() / (token + ".json")
    if not path.is_file() or not meta_path.is_file():
        raise HTTPException(409, "恢复预览已过期，请重新选择备份")
    meta = json.loads(meta_path.read_text())
    if meta["created"] < time.time() - PREVIEW_TTL:
        raise HTTPException(409, "恢复预览已过期，请重新预览")
    if await asyncio.to_thread(file_digest, path) != meta["sha256"]:
        raise HTTPException(409, "待恢复文件已变化，请重新选择备份")
    if "completed" in meta:
        if conflicts != meta["conflicts"]:
            raise HTTPException(409, "这次恢复已完成，请重新预览后选择其他处理方式")
        return meta["completed"]
    manifest = await asyncio.to_thread(inspect_archive, path)
    async with async_session() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        rows = (await session.execute(select(TravelMemoryRow).order_by(TravelMemoryRow.updated_at.desc(), TravelMemoryRow.id))).scalars().all()
        existing = [svc.response(r) for r in rows]
        if svc.digest(existing) != meta["basis"]:
            raise HTTPException(409, "预览后本机记录已改变，请重新预览；已有内容未被覆盖")
        items = proposed(manifest, existing)
        await asyncio.to_thread(install_archive_media, path, manifest)
        added, copied = 0, 0
        for entry, item in zip(manifest.records, items):
            if item["status"] not in ("new", "conflict") or (item["status"] == "conflict" and conflicts == "skip"):
                continue
            payload = entry.document.model_dump(mode="json")
            is_copy = item["status"] == "conflict"
            if is_copy:
                payload["title"] = payload["title"][:150] + "（恢复副本）"
            session.add(TravelMemoryRow(id=item["copy_id"] if is_copy else entry.id, revision=1,
                                        document_json=svc.dump(payload), created_at=entry.created_at.isoformat(),
                                        updated_at=svc.now() if is_copy else entry.updated_at.isoformat()))
            copied += int(is_copy)
            added += int(not is_copy)
        await session.commit()
    result = dict(added=added, copied=copied, skipped=len(items) - added - copied)
    # A durable receipt makes a lost confirmation response safe to retry.
    meta.update(completed=result, conflicts=conflicts)
    media.atomic_file(meta_path, svc.dump(meta).encode())
    return result
