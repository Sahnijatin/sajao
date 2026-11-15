"""Object storage for capture media, behind one small interface.

Clients never get a public URL or storage credentials. They upload and
download through short-lived signed URLs only. Uploads are multipart, so a
dropped connection costs one part, not the whole file.
"""

import threading
from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class UploadedPart:
    part_number: int
    size_bytes: int
    etag: str


class UploadNotFoundError(Exception):
    """The multipart upload does not exist: never started, completed, or expired."""


class ObjectStorage(Protocol):
    def create_upload(self, key: str, content_type: str) -> str:
        """Start a multipart upload and return its id."""
        ...

    def sign_part(self, key: str, upload_id: str, part_number: int, expires_in: int) -> str: ...

    def list_parts(self, key: str, upload_id: str) -> list[UploadedPart]: ...

    def complete_upload(self, key: str, upload_id: str, parts: list[UploadedPart]) -> int:
        """Join the parts into the object and return its size in bytes."""
        ...

    def abort_upload(self, key: str, upload_id: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def sign_download(self, key: str, expires_in: int) -> str: ...


_MISSING_UPLOAD = {"NoSuchUpload", "404", "NoSuchKey"}


class S3ObjectStorage:
    """Any S3-compatible store: Cloudflare R2 in the cloud, the Supabase stack locally."""

    def __init__(
        self, *, endpoint: str, region: str, bucket: str, access_key_id: str, secret_access_key: str
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=20,
            ),
        )

    def create_upload(self, key: str, content_type: str) -> str:
        response = self._client.create_multipart_upload(
            Bucket=self._bucket, Key=key, ContentType=content_type
        )
        upload_id: str = response["UploadId"]
        return upload_id

    def sign_part(self, key: str, upload_id: str, part_number: int, expires_in: int) -> str:
        url: str = self._client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
        )
        return url

    def list_parts(self, key: str, upload_id: str) -> list[UploadedPart]:
        parts: list[UploadedPart] = []
        marker = 0
        while True:
            try:
                page = self._client.list_parts(
                    Bucket=self._bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker
                )
            except ClientError as error:
                raise self._translate(error) from error
            parts += [
                UploadedPart(part["PartNumber"], part["Size"], part["ETag"])
                for part in page.get("Parts", [])
            ]
            if not page.get("IsTruncated"):
                return parts
            marker = page["NextPartNumberMarker"]

    def complete_upload(self, key: str, upload_id: str, parts: list[UploadedPart]) -> int:
        try:
            self._client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": part.part_number, "ETag": part.etag}
                        for part in sorted(parts, key=lambda part: part.part_number)
                    ]
                },
            )
        except ClientError as error:
            raise self._translate(error) from error
        size: int = self._client.head_object(Bucket=self._bucket, Key=key)["ContentLength"]
        return size

    def abort_upload(self, key: str, upload_id: str) -> None:
        try:
            self._client.abort_multipart_upload(Bucket=self._bucket, Key=key, UploadId=upload_id)
        except ClientError as error:
            raise self._translate(error) from error

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def sign_download(self, key: str, expires_in: int) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_in
        )
        return url

    @staticmethod
    def _translate(error: ClientError) -> Exception:
        code = error.response.get("Error", {}).get("Code", "")
        return UploadNotFoundError(code) if code in _MISSING_UPLOAD else error


class InMemoryObjectStorage:
    """A fake for tests. Signed URLs are placeholders; `put_part` stands in for the client."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._uploads: dict[tuple[str, str], dict[int, bytes]] = {}
        self.objects: dict[str, bytes] = {}
        self._next_id = 0

    def create_upload(self, key: str, content_type: str) -> str:
        with self._lock:
            self._next_id += 1
            upload_id = f"upload-{self._next_id}"
            self._uploads[(key, upload_id)] = {}
            return upload_id

    def sign_part(self, key: str, upload_id: str, part_number: int, expires_in: int) -> str:
        return f"https://storage.test/{key}?uploadId={upload_id}&partNumber={part_number}&signed=1"

    def put_part(self, key: str, upload_id: str, part_number: int, body: bytes) -> str:
        self._parts(key, upload_id)[part_number] = body
        return f'"etag-{part_number}-{len(body)}"'

    def list_parts(self, key: str, upload_id: str) -> list[UploadedPart]:
        return [
            UploadedPart(number, len(body), f'"etag-{number}-{len(body)}"')
            for number, body in sorted(self._parts(key, upload_id).items())
        ]

    def complete_upload(self, key: str, upload_id: str, parts: list[UploadedPart]) -> int:
        stored = self._parts(key, upload_id)
        body = b"".join(
            stored[part.part_number] for part in sorted(parts, key=lambda p: p.part_number)
        )
        with self._lock:
            del self._uploads[(key, upload_id)]
            self.objects[key] = body
        return len(body)

    def abort_upload(self, key: str, upload_id: str) -> None:
        self._parts(key, upload_id)
        with self._lock:
            del self._uploads[(key, upload_id)]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def sign_download(self, key: str, expires_in: int) -> str:
        return f"https://storage.test/{key}?signed=1"

    def _parts(self, key: str, upload_id: str) -> dict[int, bytes]:
        try:
            return self._uploads[(key, upload_id)]
        except KeyError:
            raise UploadNotFoundError(upload_id) from None
