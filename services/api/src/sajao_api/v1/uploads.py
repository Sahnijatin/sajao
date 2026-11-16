"""Resumable uploads of capture media, straight from the phone to object storage.

The API never receives the file. It plans the upload, hands out short-lived
signed URLs for each part, and joins the parts when the phone is done. After
a dropped connection the phone asks which parts arrived and sends the rest.
"""

import asyncio
import math
import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from sajao_api.auth import Principal, current_user
from sajao_api.errors import ApiError
from sajao_api.storage import ObjectStorage, UploadedPart, UploadNotFoundError

router = APIRouter(prefix="/uploads", tags=["uploads"])

MIB = 1024 * 1024
PART_SIZE_BYTES = 5 * MIB  # The smallest part size S3-compatible stores accept.
URL_EXPIRES_IN_SECONDS = 15 * 60

MediaKind = Literal["photo", "video", "data"]
# Allowed content types and the file extension each is stored under.
CONTENT_TYPES: dict[MediaKind, dict[str, str]] = {
    "photo": {
        "image/jpeg": "jpg",
        "image/heic": "heic",
        "image/png": "png",
        "image/webp": "webp",
    },
    "video": {"video/mp4": "mp4", "video/quicktime": "mov"},
    # A scan's capture package besides images and video: the sensor log (JSON
    # lines), planes (JSON), and the depth file and scene mesh (binary).
    "data": {
        "application/x-ndjson": "jsonl",
        "application/json": "json",
        "application/octet-stream": "bin",
    },
}
# Photos are resized on the phone to about 1600 px, so these are generous.
# A scan video runs from the first frame to Done at full camera resolution.
MAX_SIZE_BYTES: dict[MediaKind, int] = {"photo": 20 * MIB, "video": 512 * MIB, "data": 100 * MIB}

_KEY = re.compile(
    r"^(?P<owner>[0-9a-f-]{36})/[0-9a-f]{32}\.(?:jpg|heic|png|webp|mp4|mov|jsonl|json|bin)$"
)


def is_owned_key(key: str, user_id: str) -> bool:
    """True when `key` is a stored object key that belongs to `user_id`."""
    match = _KEY.match(key)
    return match is not None and match["owner"] == user_id


_KIND_BY_EXTENSION: dict[str, MediaKind] = {
    extension: kind for kind, types in CONTENT_TYPES.items() for extension in types.values()
}


class CreateUpload(BaseModel):
    kind: MediaKind
    content_type: str
    size_bytes: int = Field(gt=0)


class UploadRef(BaseModel):
    key: str = Field(max_length=128)
    upload_id: str = Field(min_length=1, max_length=1024)


class ResumeUpload(UploadRef):
    size_bytes: int = Field(gt=0)


class Part(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    size_bytes: int = Field(ge=0)
    etag: str = Field(min_length=1, max_length=256)


class CompleteUpload(UploadRef):
    parts: list[Part] = Field(min_length=1, max_length=10_000)


class PartUrl(BaseModel):
    part_number: int
    url: str


class UploadPlan(BaseModel):
    key: str
    upload_id: str
    part_size_bytes: int
    part_count: int
    uploaded: list[Part]
    """Parts the store already has. Empty for a new upload."""
    parts: list[PartUrl]
    """Signed URLs for the parts still to send: PUT each part's bytes to its URL."""
    url_expires_in_seconds: int


class CompletedUpload(BaseModel):
    key: str
    size_bytes: int


def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage | None = request.app.state.storage
    if storage is None:
        raise ApiError(503, "uploads_unavailable", "Uploads are not available right now.")
    return storage


def _owned_key(key: str, user: Principal) -> str:
    # One answer for "malformed" and "someone else's": never reveal which keys exist.
    if not is_owned_key(key, user.user_id):
        raise ApiError(404, "upload_not_found", "This upload does not exist.")
    return key


def _part_count(size_bytes: int) -> int:
    return max(1, math.ceil(size_bytes / PART_SIZE_BYTES))


def _check_size(kind: MediaKind, size_bytes: int) -> None:
    if size_bytes > MAX_SIZE_BYTES[kind]:
        raise ApiError(413, "file_too_large", "This file is too large to upload.")


async def _plan(
    storage: ObjectStorage, key: str, upload_id: str, size_bytes: int, uploaded: list[UploadedPart]
) -> UploadPlan:
    count = _part_count(size_bytes)
    done = {part.part_number for part in uploaded}
    missing = [number for number in range(1, count + 1) if number not in done]
    urls = await asyncio.gather(
        *(
            asyncio.to_thread(storage.sign_part, key, upload_id, number, URL_EXPIRES_IN_SECONDS)
            for number in missing
        )
    )
    return UploadPlan(
        key=key,
        upload_id=upload_id,
        part_size_bytes=PART_SIZE_BYTES,
        part_count=count,
        uploaded=[Part(**vars(part)) for part in uploaded if part.part_number <= count],
        parts=[PartUrl(part_number=n, url=url) for n, url in zip(missing, urls, strict=True)],
        url_expires_in_seconds=URL_EXPIRES_IN_SECONDS,
    )


User = Annotated[Principal, Depends(current_user)]
Storage = Annotated[ObjectStorage, Depends(get_storage)]


@router.post("", operation_id="createUpload", status_code=201)
async def create_upload(body: CreateUpload, user: User, storage: Storage) -> UploadPlan:
    """Plan a new upload and get signed URLs for its parts."""
    extension = CONTENT_TYPES[body.kind].get(body.content_type)
    if extension is None:
        raise ApiError(415, "unsupported_media_type", "This kind of file cannot be uploaded.")
    _check_size(body.kind, body.size_bytes)
    key = f"{user.user_id}/{uuid.uuid4().hex}.{extension}"
    upload_id = await asyncio.to_thread(storage.create_upload, key, body.content_type)
    return await _plan(storage, key, upload_id, body.size_bytes, [])


@router.post("/resume", operation_id="resumeUpload")
async def resume_upload(body: ResumeUpload, user: User, storage: Storage) -> UploadPlan:
    """After a dropped connection: which parts arrived, and fresh URLs for the rest."""
    key = _owned_key(body.key, user)
    _check_size(_KIND_BY_EXTENSION[key.rsplit(".", 1)[1]], body.size_bytes)
    try:
        uploaded = await asyncio.to_thread(storage.list_parts, key, body.upload_id)
    except UploadNotFoundError:
        raise ApiError(404, "upload_not_found", "This upload does not exist.") from None
    return await _plan(storage, key, body.upload_id, body.size_bytes, uploaded)


@router.post("/complete", operation_id="completeUpload")
async def complete_upload(body: CompleteUpload, user: User, storage: Storage) -> CompletedUpload:
    """Join the uploaded parts into the stored file."""
    key = _owned_key(body.key, user)
    parts = [UploadedPart(part.part_number, part.size_bytes, part.etag) for part in body.parts]
    try:
        size = await asyncio.to_thread(storage.complete_upload, key, body.upload_id, parts)
    except (UploadNotFoundError, KeyError):
        raise ApiError(404, "upload_not_found", "This upload does not exist.") from None
    # The declared size was only a plan. Enforce the limit on what really arrived.
    if size > MAX_SIZE_BYTES[_KIND_BY_EXTENSION[key.rsplit(".", 1)[1]]]:
        await asyncio.to_thread(storage.delete, key)
        raise ApiError(413, "file_too_large", "This file is too large to upload.")
    return CompletedUpload(key=key, size_bytes=size)
