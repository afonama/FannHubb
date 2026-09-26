"""Local file storage for avatar uploads (and any future media).

Files land under ``MEDIA_ROOT`` and are served by FastAPI's StaticFiles mount at
``/media``. This is deliberately the simplest thing that works for a demo: it
avoids pre-signed object-storage plumbing. Swap ``save_avatar`` for an S3/Azure
Blob call in production - the route and schema do not change.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.logging_config import get_logger

logger = get_logger(__name__)

ALLOWED_AVATAR_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_CHUNK_SIZE = 64 * 1024


def media_root() -> Path:
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def avatar_dir() -> Path:
    path = media_root() / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def avatar_public_path(filename: str) -> str:
    """Relative URL the frontend can use directly (``/media/avatars/x.png``)."""
    return f"/media/avatars/{filename}"


def local_path_for_url(url: Optional[str]) -> Optional[Path]:
    """Map ``/media/avatars/x.png`` back to a filesystem path, if it is local."""
    if not url or not url.startswith("/media/"):
        return None
    relative = url.removeprefix("/media/").lstrip("/")
    candidate = (media_root() / relative).resolve()
    root = media_root().resolve()
    # Guard against traversal via a crafted stored URL.
    if not str(candidate).startswith(str(root)):
        return None
    return candidate


async def save_avatar(user_id: int, upload: UploadFile) -> tuple[str, int]:
    """Validate and persist an avatar image; returns ``(public_url, bytes_written)``."""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise AppError(
            f"Unsupported image type '{content_type}'. Allowed: {', '.join(sorted(ALLOWED_AVATAR_TYPES))}",
            code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            details={"allowed": sorted(ALLOWED_AVATAR_TYPES)},
        )

    extension = ALLOWED_AVATAR_TYPES[content_type]
    # Generated name: never trust the client filename (path traversal / collisions).
    filename = f"user_{user_id}_{uuid.uuid4().hex[:12]}{extension}"
    destination = avatar_dir() / filename

    written = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(_CHUNK_SIZE):
                written += len(chunk)
                if written > settings.media_max_upload_bytes:
                    raise AppError(
                        f"Avatar exceeds the {settings.media_max_upload_bytes} byte limit",
                        code=ErrorCode.PAYLOAD_TOO_LARGE,
                        details={"max_bytes": settings.media_max_upload_bytes},
                    )
                handle.write(chunk)
    except AppError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:  # pragma: no cover - disk failures
        destination.unlink(missing_ok=True)
        logger.error("avatar_write_failed", extra={"error": str(exc), "user_id": user_id})
        raise AppError("Could not store the uploaded file", code=ErrorCode.INTERNAL_ERROR) from exc
    finally:
        await upload.close()

    if written == 0:
        destination.unlink(missing_ok=True)
        raise AppError("Uploaded file is empty", code=ErrorCode.VALIDATION_ERROR)

    public_url = avatar_public_path(filename)
    logger.info(
        "avatar_stored",
        extra={"user_id": user_id, "filename": filename, "bytes": written, "content_type": content_type},
    )
    return public_url, written


def delete_local_media(url: Optional[str]) -> bool:
    """Best-effort cleanup of a previously uploaded local file."""
    path = local_path_for_url(url)
    if path is None or not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:  # pragma: no cover
        logger.warning("avatar_delete_failed", extra={"path": str(path)})
        return False
