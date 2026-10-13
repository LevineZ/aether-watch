from __future__ import annotations

import io
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.config import settings


@lru_cache(maxsize=1)
def client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    c = client()
    found = c.bucket_exists(settings.minio_bucket)
    if not found:
        c.make_bucket(settings.minio_bucket)


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    ensure_bucket()
    client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def get_bytes(key: str) -> bytes:
    response = client().get_object(settings.minio_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def exists(key: str) -> bool:
    try:
        client().stat_object(settings.minio_bucket, key)
        return True
    except S3Error:
        return False
