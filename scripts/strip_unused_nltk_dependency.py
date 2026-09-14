#!/usr/bin/env python3
"""Remove the vendored engine's declared but unused NLTK dependency."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import os
import re
import sys
from email.message import Message
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
from zipfile import BadZipFile, ZipFile

DEPENDENCY = "nltk"
DEPENDENCY_REFERENCE = re.compile(r"\bnltk\b", re.IGNORECASE)
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SOURCE_ROOTS = (
    REPO_ROOT / "backend/app",
    REPO_ROOT / "mcp/src",
    REPO_ROOT / "mcp/tests",
)
VENDOR_DIR = REPO_ROOT / "backend/vendor"
WHEEL_GLOB = "metaharmonizer-*.whl"


def _default_wheel() -> Path:
    wheels = sorted(VENDOR_DIR.glob(WHEEL_GLOB))
    if len(wheels) != 1:
        raise ValueError(
            f"expected exactly one {WHEEL_GLOB} under {VENDOR_DIR.as_posix()}, "
            f"found {len(wheels)}"
        )
    return wheels[0]


def _project_references() -> list[str]:
    references: list[str] = []
    for root in PROJECT_SOURCE_ROOTS:
        if not root.is_dir():
            raise ValueError(f"expected project source directory is missing: {root.as_posix()}")
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if DEPENDENCY_REFERENCE.search(text):
                references.append(path.relative_to(REPO_ROOT).as_posix())
    return references


def _wheel_contents(wheel: Path) -> tuple[list, dict[str, bytes], str, str]:
    try:
        with ZipFile(wheel) as archive:
            infos = archive.infolist()
            contents = {info.filename: archive.read(info.filename) for info in infos}
    except (BadZipFile, OSError) as exc:
        raise ValueError(f"could not inspect {wheel.as_posix()}: {exc}") from exc

    metadata = [name for name in contents if name.endswith(".dist-info/METADATA")]
    records = [name for name in contents if name.endswith(".dist-info/RECORD")]
    if len(metadata) != 1 or len(records) != 1:
        raise ValueError(
            f"{wheel.as_posix()} must contain exactly one METADATA and one RECORD file"
        )
    return infos, contents, metadata[0], records[0]


def _wheel_references(wheel: Path, contents: dict[str, bytes]) -> list[str]:
    references: list[str] = []
    for name, payload in contents.items():
        if not name.endswith(".py"):
            continue
        text = payload.decode("utf-8", errors="replace")
        if DEPENDENCY_REFERENCE.search(text):
            references.append(f"{wheel.as_posix()}!/{name}")
    return references


def _metadata_message(metadata: bytes) -> Message:
    return BytesParser(policy=compat32).parsebytes(metadata)


def _canonical_requirement_name(requirement: str) -> str:
    match = REQUIREMENT_NAME.match(requirement)
    if not match:
        raise ValueError(f"could not parse Requires-Dist value: {requirement!r}")
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _metadata_dependencies(metadata: bytes) -> list[str]:
    requirements = _metadata_message(metadata).get_all("Requires-Dist", [])
    return [
        requirement
        for requirement in requirements
        if _canonical_requirement_name(requirement) == DEPENDENCY
    ]


def _without_dependency(metadata: bytes) -> bytes:
    message = _metadata_message(metadata)
    requirements = message.get_all("Requires-Dist", [])
    retained = [
        requirement
        for requirement in requirements
        if _canonical_requirement_name(requirement) != DEPENDENCY
    ]
    del message["Requires-Dist"]
    for requirement in retained:
        message["Requires-Dist"] = requirement
    return message.as_bytes(policy=compat32)


def _record_hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def strip_unused_dependency(wheel: Path) -> bool:
    infos, contents, metadata_name, record_name = _wheel_contents(wheel)
    references = _project_references() + _wheel_references(wheel, contents)
    if references:
        joined = "\n  ".join(references)
        raise ValueError(
            f"{DEPENDENCY} is referenced at runtime; keep it as a direct dependency:\n  {joined}"
        )

    dependencies = _metadata_dependencies(contents[metadata_name])
    if not dependencies:
        return False

    contents[metadata_name] = _without_dependency(contents[metadata_name])

    rows = list(csv.reader(io.StringIO(contents[record_name].decode("utf-8"))))
    metadata_rows = [row for row in rows if row[0] == metadata_name]
    record_rows = [row for row in rows if row[0] == record_name]
    if len(metadata_rows) != 1 or len(record_rows) != 1:
        raise ValueError("wheel RECORD must contain exactly one METADATA and one self entry")
    metadata_rows[0][1:] = [
        _record_hash(contents[metadata_name]),
        str(len(contents[metadata_name])),
    ]
    record_rows[0][1:] = ["", ""]
    record_buffer = io.StringIO(newline="")
    csv.writer(record_buffer, lineterminator="\n").writerows(rows)
    contents[record_name] = record_buffer.getvalue().encode("utf-8")

    temporary = wheel.with_name(f".{wheel.name}.tmp")
    try:
        with ZipFile(temporary, "w") as archive:
            for info in infos:
                archive.writestr(info, contents[info.filename])
        os.replace(temporary, wheel)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def verify_dependency_absent(wheel: Path) -> None:
    _, contents, metadata_name, _ = _wheel_contents(wheel)
    references = _project_references() + _wheel_references(wheel, contents)
    dependencies = _metadata_dependencies(contents[metadata_name])
    problems = [*references, *dependencies]
    if problems:
        joined = "\n  ".join(problems)
        raise ValueError(
            f"{DEPENDENCY} must not be referenced or declared by the vendored engine:\n  {joined}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument(
        "--strip",
        action="store_true",
        help="remove the dependency after proving the engine does not reference it",
    )
    args = parser.parse_args(argv)
    try:
        wheel = args.wheel or _default_wheel()
        changed = strip_unused_dependency(wheel) if args.strip else False
        verify_dependency_absent(wheel)
    except ValueError as exc:
        print(f"unused-{DEPENDENCY}-dependency: {exc}", file=sys.stderr)
        return 1

    action = "removed and verified" if changed else "verified absent"
    print(f"unused-{DEPENDENCY}-dependency: {action} in {wheel.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
