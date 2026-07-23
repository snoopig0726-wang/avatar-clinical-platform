from __future__ import annotations

import base64
from datetime import timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.config.settings import Settings


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes, mime_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def get_url(self, key: str, mime_type: str) -> str: ...
    def delete(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> int: ...


class LocalObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.local_image_dir).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid object key")
        return path

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        del mime_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def get_url(self, key: str, mime_type: str) -> str:
        content = self._path(key).read_bytes()
        return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True

    def delete_prefix(self, prefix: str) -> int:
        directory = self._path(prefix)
        if not directory.exists() or not directory.is_dir():
            return 0
        files = [item for item in directory.rglob("*") if item.is_file()]
        for item in files:
            item.unlink()
        for item in sorted(directory.rglob("*"), reverse=True):
            if item.is_dir():
                item.rmdir()
        directory.rmdir()
        return len(files)


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        from minio import Minio

        self.settings = settings
        internal = urlparse(settings.s3_endpoint)
        public = urlparse(settings.s3_public_endpoint)
        self.client = Minio(
            internal.netloc,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=internal.scheme == "https",
            region=settings.s3_region,
        )
        self.public_client = Minio(
            public.netloc,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=public.scheme == "https",
            region=settings.s3_region,
        )
        self.bucket = settings.s3_bucket
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        from io import BytesIO

        self.client.put_object(
            self.bucket,
            key,
            BytesIO(content),
            length=len(content),
            content_type=mime_type,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_url(self, key: str, mime_type: str) -> str:
        del mime_type
        return self.public_client.presigned_get_object(
            self.bucket,
            key,
            expires=timedelta(seconds=self.settings.image_url_ttl_seconds),
        )

    def delete(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = getattr(exc, "code", None) or getattr(response, "code", None)
            if code in {"NoSuchKey", "NoSuchObject", "NoSuchFile"}:
                return False
            raise
        self.client.remove_object(self.bucket, key)
        return True

    def delete_prefix(self, prefix: str) -> int:
        names = [
            item.object_name
            for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        ]
        for name in names:
            self.client.remove_object(self.bucket, name)
        return len(names)


def get_object_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_provider == "local":
        return LocalObjectStorage(settings)
    if settings.storage_provider == "s3":
        return S3ObjectStorage(settings)
    raise RuntimeError("unsupported storage provider")
