"""Blob storage abstraction — one seam for uploaded files and exports.

Two backends, chosen by ``OBJECT_STORE_URL``:

- ``file://…``  → :class:`LocalStorage` (dev / single-host self-host). Files live
  under the shared ``data/uploads`` volume, so the API and worker containers see
  the same files.
- ``s3://bucket`` → :class:`S3Storage` (hosted / multi-replica). Files live in an
  S3-compatible bucket (AWS S3 or Cloudflare R2), so no container owns state and
  the app scales horizontally.

The engine needs a real local path, so every read goes through :meth:`Storage.local`,
which yields a local file (the real one for ``file://``; a temp download for S3,
cleaned up on exit). ``file_path`` in the DB stores the object *key*, not an
absolute path — with a fallback so any legacy absolute path still resolves.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Protocol

from app.core.settings import settings

# Repo-relative uploads dir: backend/data/uploads (→ /app/data/uploads in the
# container, backed by the shared `uploads` volume).
_LOCAL_BASE = Path(__file__).resolve().parents[2] / "data" / "uploads"


class Storage(Protocol):
    scheme: str

    def store(self, key: str, src: Path) -> None: ...
    def local(self, key: str) -> "Iterator[Path]": ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Files on a local (shared) filesystem under a base directory."""

    scheme = "file"

    def __init__(self, base: Path = _LOCAL_BASE):
        self.base = base

    def _resolve(self, key: str) -> Path:
        # Back-compat: a legacy absolute path is used as-is.
        p = Path(key)
        if p.is_absolute():
            return p
        return self.base / key

    def store(self, key: str, src: Path) -> None:
        dst = self._resolve(key)
        if src.resolve() == dst.resolve():
            return  # already in place
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    @contextmanager
    def local(self, key: str) -> Iterator[Path]:
        yield self._resolve(key)

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()


class S3Storage:
    """Files in an S3-compatible bucket (AWS S3 / Cloudflare R2)."""

    scheme = "s3"

    def __init__(self, bucket: str, *, endpoint: str | None, key: str | None, secret: str | None):
        self.bucket = bucket
        self._endpoint = endpoint
        self._key = key
        self._secret = secret

    def _client(self):
        try:
            import boto3  # lazy: only needed when object storage is S3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OBJECT_STORE_URL is s3:// but boto3 is not installed."
            ) from exc
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._key,
            aws_secret_access_key=self._secret,
            region_name="auto",
        )

    def store(self, key: str, src: Path) -> None:
        self._client().upload_file(str(src), self.bucket, key)

    @contextmanager
    def local(self, key: str) -> Iterator[Path]:
        tmp = Path(tempfile.mkdtemp(prefix="mh_obj_")) / Path(key).name
        try:
            self._client().download_file(self.bucket, key, str(tmp))
            yield tmp
        finally:
            shutil.rmtree(tmp.parent, ignore_errors=True)

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client().head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    url = settings.object_store_url or ""
    if url.startswith("s3://"):
        bucket = url[len("s3://"):].split("/", 1)[0] or settings.r2_bucket
        if not bucket:
            raise RuntimeError("OBJECT_STORE_URL is s3:// but no bucket is configured.")
        return S3Storage(
            bucket,
            endpoint=settings.object_store_endpoint,
            key=settings.r2_key,
            secret=settings.r2_secret,
        )
    return LocalStorage()
