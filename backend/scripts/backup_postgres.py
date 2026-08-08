"""Encrypted PostgreSQL backup and restore for Cloudflare R2."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
import secrets
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import boto3
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.engine import URL, make_url

MAGIC = b"MHBK1\0"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
TIMESTAMP_RE = re.compile(r"-(\d{8}T\d{6}Z)\.dump\.enc$")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _database_url(value: str | None = None) -> URL:
    raw = value or _required_env("DATABASE_URL")
    return make_url(raw.replace("postgresql+asyncpg://", "postgresql://", 1))


def _postgres_env(url: URL) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": url.host or "localhost",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "postgres",
            "PGDATABASE": url.database or "postgres",
        }
    )
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def _load_key(path: Path) -> bytes:
    if not path.is_file():
        raise RuntimeError(f"backup encryption key not found: {path}")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError(f"backup encryption key must not be group/world accessible: {path}")
    encoded = path.read_text(encoding="ascii").strip()
    try:
        key = bytes.fromhex(encoded) if len(encoded) == 64 else base64.urlsafe_b64decode(encoded)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("backup encryption key is not valid hex/base64") from exc
    if len(key) != 32:
        raise RuntimeError("backup encryption key must decode to exactly 32 bytes")
    return key


def generate_key(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")


def encrypt_file(source: Path, destination: Path, key: bytes) -> str:
    nonce = secrets.token_bytes(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    digest = hashlib.sha256()
    with source.open("rb") as src, destination.open("wb") as dst:
        header = MAGIC + nonce
        dst.write(header)
        digest.update(header)
        while chunk := src.read(CHUNK_SIZE):
            encrypted = encryptor.update(chunk)
            dst.write(encrypted)
            digest.update(encrypted)
        final = encryptor.finalize()
        dst.write(final)
        digest.update(final)
        dst.write(encryptor.tag)
        digest.update(encryptor.tag)
    return digest.hexdigest()


def decrypt_file(source: Path, destination: Path, key: bytes) -> None:
    total_size = source.stat().st_size
    header_size = len(MAGIC) + NONCE_SIZE
    if total_size <= header_size + TAG_SIZE:
        raise RuntimeError("encrypted backup is truncated")
    with source.open("rb") as src:
        magic = src.read(len(MAGIC))
        if magic != MAGIC:
            raise RuntimeError("encrypted backup has an unknown format")
        nonce = src.read(NONCE_SIZE)
        src.seek(-TAG_SIZE, os.SEEK_END)
        tag = src.read(TAG_SIZE)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        remaining = total_size - header_size - TAG_SIZE
        src.seek(header_size)
        with destination.open("wb") as dst:
            while remaining:
                chunk = src.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise RuntimeError("encrypted backup is truncated")
                remaining -= len(chunk)
                dst.write(decryptor.update(chunk))
            dst.write(decryptor.finalize())


def _timestamp_from_key(key: str) -> datetime | None:
    match = TIMESTAMP_RE.search(key)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def retention_keys(keys: list[str]) -> set[str]:
    dated = [(key, _timestamp_from_key(key)) for key in keys]
    dated = [(key, stamp) for key, stamp in dated if stamp is not None]
    dated.sort(key=lambda item: item[1], reverse=True)
    keep: set[str] = set()
    buckets: tuple[tuple[int, Callable[[datetime], object]], ...] = (
        (7, lambda stamp: stamp.date()),
        (4, lambda stamp: stamp.isocalendar()[:2]),
        (12, lambda stamp: (stamp.year, stamp.month)),
    )
    for limit, bucket_of in buckets:
        seen = set()
        for key, stamp in dated:
            bucket = bucket_of(stamp)
            if bucket in seen:
                continue
            seen.add(bucket)
            keep.add(key)
            if len(seen) == limit:
                break
    return keep


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=_required_env("BACKUP_R2_ENDPOINT"),
        aws_access_key_id=_required_env("BACKUP_R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_required_env("BACKUP_R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _list_keys(client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def _prune(client, bucket: str, prefix: str) -> int:
    keys = _list_keys(client, bucket, prefix)
    keep = retention_keys(keys)
    stale = [key for key in keys if _timestamp_from_key(key) and key not in keep]
    for offset in range(0, len(stale), 1000):
        batch = stale[offset : offset + 1000]
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
    return len(stale)


def backup() -> str:
    database = _database_url()
    key_path = Path(
        os.getenv("BACKUP_ENCRYPTION_KEY_FILE", "/run/secrets/metaharmonizer-backup.key")
    )
    encryption_key = _load_key(key_path)
    bucket = _required_env("BACKUP_R2_BUCKET")
    prefix = os.getenv("BACKUP_PREFIX", "postgres/").strip("/") + "/"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_name = re.sub(r"[^A-Za-z0-9_.-]", "_", database.database or "postgres")
    database_prefix = f"{prefix}{db_name}/"
    object_key = f"{database_prefix}{db_name}-{stamp}.dump.enc"

    with tempfile.TemporaryDirectory(prefix="mh-backup-") as temp_dir:
        dump_path = Path(temp_dir) / "database.dump"
        encrypted_path = Path(temp_dir) / "database.dump.enc"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump_path)],
            env=_postgres_env(database),
            check=True,
        )
        sha256 = encrypt_file(dump_path, encrypted_path, encryption_key)
        client = _r2_client()
        client.upload_file(
            str(encrypted_path),
            bucket,
            object_key,
            ExtraArgs={
                "ContentType": "application/octet-stream",
                "Metadata": {"sha256": sha256, "encryption": "AES-256-GCM"},
            },
        )
        removed = _prune(client, bucket, database_prefix)
    print(f"uploaded s3://{bucket}/{object_key}; pruned={removed}")
    return object_key


def _same_database(first: URL, second: URL) -> bool:
    return (
        first.host or "localhost",
        first.port or 5432,
        first.database,
    ) == (
        second.host or "localhost",
        second.port or 5432,
        second.database,
    )


def restore(target_database_url: str, object_key: str | None, allow_production: bool) -> str:
    production = _database_url()
    target = _database_url(target_database_url)
    if _same_database(production, target) and not allow_production:
        raise RuntimeError("refusing to restore over the configured production database")

    key_path = Path(
        os.getenv("BACKUP_ENCRYPTION_KEY_FILE", "/run/secrets/metaharmonizer-backup.key")
    )
    encryption_key = _load_key(key_path)
    bucket = _required_env("BACKUP_R2_BUCKET")
    prefix = os.getenv("BACKUP_PREFIX", "postgres/").strip("/") + "/"
    db_name = re.sub(r"[^A-Za-z0-9_.-]", "_", production.database or "postgres")
    database_prefix = f"{prefix}{db_name}/"
    client = _r2_client()
    if object_key is None:
        candidates = [
            key
            for key in _list_keys(client, bucket, database_prefix)
            if _timestamp_from_key(key)
        ]
        if not candidates:
            raise RuntimeError("no PostgreSQL backups found in R2")
        object_key = max(candidates, key=lambda key: _timestamp_from_key(key) or datetime.min.replace(tzinfo=timezone.utc))

    with tempfile.TemporaryDirectory(prefix="mh-restore-") as temp_dir:
        encrypted_path = Path(temp_dir) / "database.dump.enc"
        dump_path = Path(temp_dir) / "database.dump"
        client.download_file(bucket, object_key, str(encrypted_path))
        decrypt_file(encrypted_path, dump_path, encryption_key)
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "--dbname",
                target.database or "postgres",
                str(dump_path),
            ],
            env=_postgres_env(target),
            check=True,
        )
        subprocess.run(
            ["psql", "--tuples-only", "--command", "SELECT version_num FROM alembic_version"],
            env=_postgres_env(target),
            check=True,
        )
    print(f"restored s3://{bucket}/{object_key} into {target.database}")
    return object_key


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen")
    keygen.add_argument("--key-file", type=Path, required=True)
    commands.add_parser("backup")
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--target-database-url", required=True)
    restore_parser.add_argument("--object-key")
    restore_parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()

    if args.command == "keygen":
        generate_key(args.key_file)
        print(f"created {args.key_file}")
    elif args.command == "backup":
        backup()
    else:
        restore(args.target_database_url, args.object_key, args.allow_production)


if __name__ == "__main__":
    main()