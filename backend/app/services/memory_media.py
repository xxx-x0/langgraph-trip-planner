"""Immutable original photos; derived previews never replace the user's file."""
import hashlib
import io
import os
import re
import tempfile
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from ..database import DATA_DIR

MAX_PHOTO_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def storage_root() -> Path:
    root = Path(os.environ.get("TRAVEL_MEMORY_STORAGE_DIR", DATA_DIR / "travel-memory-media"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def blob_path(digest: str, thumbnail: bool = False) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise HTTPException(400, "照片标识无效")
    return storage_root() / "objects" / digest[:2] / (digest + (".jpg" if thumbnail else ".original"))


def inspect_image(data: bytes) -> tuple[dict, bytes]:
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "单张照片须小于20 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in MIME:
                    raise HTTPException(415, "请上传 JPEG、PNG 或 WebP 照片；HEIC 请先导出为 JPEG")
                if original.width * original.height > MAX_PIXELS or max(original.size) > 30000:
                    raise HTTPException(413, "照片像素过大，请先导出较小副本（最多4000万像素）")
                if getattr(original, "n_frames", 1) != 1:
                    raise HTTPException(415, "请上传静态照片，动图可先导出一帧")
                mime = MIME[original.format]
                original.load()
                oriented = ImageOps.exif_transpose(original)
                width, height = oriented.size
                oriented.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                preview = Image.new("RGB", rgba.size, "white")
                preview.paste(rgba, mask=rgba.getchannel("A"))
                output = io.BytesIO()
                preview.save(output, "JPEG", quality=88, optimize=True)
        return dict(sha256=hashlib.sha256(data).hexdigest(), media_type=mime,
                    width=width, height=height, size=len(data)), output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(415, "照片无法解码或文件已损坏；原记录没有改变") from None


def atomic_file(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name:
            Path(name).unlink(missing_ok=True)


def store_photo(data: bytes, metadata: dict, preview: bytes):
    digest = metadata["sha256"]
    original = blob_path(digest)
    if not original.exists():
        atomic_file(original, data)
    elif hashlib.sha256(original.read_bytes()).hexdigest() != digest:
        raise HTTPException(409, "本机照片文件校验失败，请先保留备份并恢复照片")
    if not blob_path(digest, True).exists():
        atomic_file(blob_path(digest, True), preview)


def checked_original(digest: str) -> bytes:
    path = blob_path(digest)
    if not path.is_file() or path.stat().st_size > MAX_PHOTO_BYTES:
        raise HTTPException(409, "照片原件缺失，未生成不完整备份；请先恢复原件")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise HTTPException(409, "照片原件校验失败，未生成不完整备份")
    return data


def safe_filename(filename: str | None) -> str:
    name = (filename or "photo").replace("\\", "/").split("/")[-1]
    return "".join(c for c in name if ord(c) >= 32 and ord(c) != 127)[:200] or "photo"
