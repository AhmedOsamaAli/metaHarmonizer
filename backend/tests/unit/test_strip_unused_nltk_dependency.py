from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "strip_unused_nltk_dependency.py"
SPEC = importlib.util.spec_from_file_location("strip_unused_nltk_dependency", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _wheel(
    tmp_path: Path,
    source: str,
    requirement: str = "nltk",
) -> Path:
    wheel = tmp_path / "example-1.0.0-py3-none-any.whl"
    metadata_name = "example-1.0.0.dist-info/METADATA"
    record_name = "example-1.0.0.dist-info/RECORD"
    metadata = (
        "Metadata-Version: 2.1\n"
        "Name: example\n"
        "Version: 1.0.0\n"
        f"Requires-Dist: {requirement}\n"
        "Requires-Dist: requests>=2\n"
    ).encode()
    with ZipFile(wheel, "w") as archive:
        archive.writestr("example/__init__.py", source)
        archive.writestr(metadata_name, metadata)
        archive.writestr(
            record_name,
            f"{metadata_name},sha256=old,{len(metadata)}\n{record_name},,\n",
        )
    return wheel


def test_strip_removes_metadata_and_updates_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "PROJECT_SOURCE_ROOTS", ())
    wheel = _wheel(tmp_path, "VALUE = 1\n")

    assert MODULE.strip_unused_dependency(wheel)
    MODULE.verify_dependency_absent(wheel)

    with ZipFile(wheel) as archive:
        metadata_name = "example-1.0.0.dist-info/METADATA"
        metadata = archive.read(metadata_name)
        rows = list(
            csv.reader(
                io.StringIO(archive.read("example-1.0.0.dist-info/RECORD").decode("utf-8"))
            )
        )
    assert b"Requires-Dist: nltk" not in metadata
    assert b"Requires-Dist: requests>=2" in metadata
    metadata_row = next(row for row in rows if row[0] == metadata_name)
    digest = base64.urlsafe_b64encode(hashlib.sha256(metadata).digest()).rstrip(b"=").decode()
    assert metadata_row == [metadata_name, f"sha256={digest}", str(len(metadata))]


def test_strip_refuses_when_engine_references_nltk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "PROJECT_SOURCE_ROOTS", ())
    wheel = _wheel(tmp_path, "import nltk\n")

    with pytest.raises(ValueError, match="referenced at runtime"):
        MODULE.strip_unused_dependency(wheel)


@pytest.mark.parametrize(
    "requirement",
    [
        "NLTK>=3.9",
        'nltk[corpus]~=3.9; python_version >= "3.10"',
        "nltk @ https://example.invalid/nltk.whl",
    ],
)
def test_strip_recognizes_pep508_dependency_forms(
    tmp_path: Path,
    monkeypatch,
    requirement: str,
) -> None:
    monkeypatch.setattr(MODULE, "PROJECT_SOURCE_ROOTS", ())
    wheel = _wheel(tmp_path, "VALUE = 1\n", requirement)

    assert MODULE.strip_unused_dependency(wheel)
    MODULE.verify_dependency_absent(wheel)


def test_default_wheel_is_independent_of_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert MODULE._default_wheel().parent == MODULE.VENDOR_DIR
