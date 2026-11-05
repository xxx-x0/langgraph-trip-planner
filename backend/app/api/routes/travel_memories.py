"""Local single-user travel memories. No implicit planning or preference writes."""
import asyncio
import re
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...models.travel_memory import CreateMemory, EditMemory, TrashMemory, RestoreConfirm
from ...services import travel_memories as svc, memory_media as media, memory_backup as backup

router = APIRouter(prefix="/travel-records", tags=["旅行记录"])


@router.get("")
async def listing():
    return await svc.listing()


@router.get("/cities")
async def cities(q: str = Query(default="", max_length=100)):
    return svc.cities(q)


@router.get("/sources")
async def sources(q: str = Query(default="", max_length=100), offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100)):
    return await svc.sources(q, offset, limit)


@router.get("/sources/{kind}/{source_id}")
async def source(kind: str, source_id: str):
    return await svc.source_detail(kind, source_id)


@router.get("/backup")
async def export_backup():
    path = await backup.export()
    return FileResponse(path, media_type="application/zip", filename="travel-memories-" + svc.now()[:10] + ".zip",
                        background=BackgroundTask(path.unlink, missing_ok=True), headers={"Cache-Control": "no-store"})


@router.post("/restore/preview")
async def preview_restore(file: UploadFile = File(...)):
    await asyncio.to_thread(backup.cleanup)
    path = backup.work_dir() / (uuid4().hex + ".zip")
    try:
        size = 0
        with path.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > backup.MAX_BACKUP_BYTES:
                    raise HTTPException(413, "备份最多512 MB")
                output.write(chunk)
        return await backup.preview(path)
    except BaseException:
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/restore/confirm")
async def confirm_restore(body: RestoreConfirm):
    return await backup.restore(body.token, body.conflicts)


@router.post("")
async def create(body: CreateMemory):
    return await svc.create(body)


@router.get("/{record_id}")
async def get(record_id: str):
    return await svc.get(record_id)


@router.put("/{record_id}")
async def update(record_id: str, body: EditMemory):
    return await svc.update(record_id, body)


@router.patch("/{record_id}/trash")
async def trash(record_id: str, body: TrashMemory):
    return await svc.trash(record_id, body.revision, body.deleted)


@router.post("/{record_id}/photos")
async def upload_photo(record_id: str, file: UploadFile = File(...), revision: int = Form(..., ge=1), photo_id: str = Form(...)):
    try:
        if not re.fullmatch(r"[a-f0-9]{32}", photo_id):
            raise HTTPException(422, "照片上传标识无效")
        data = await file.read(media.MAX_PHOTO_BYTES + 1)
        return await svc.upload(record_id, revision, photo_id, file.filename, data)
    finally:
        await file.close()


@router.get("/{record_id}/photos/{photo_id}")
async def photo(record_id: str, photo_id: str, preview: bool = False, download: bool = False):
    path, item = await svc.photo_file(record_id, photo_id, preview)
    return FileResponse(path, media_type="image/jpeg" if preview else item["media_type"],
                        filename=item["filename"] if download else None,
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
