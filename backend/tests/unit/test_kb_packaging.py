from __future__ import annotations

import tarfile
from pathlib import Path

from scripts import package_kb, seed_kb


def test_package_fails_closed_when_assets_are_incomplete(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(package_kb, "_corpus_csvs", lambda: [])
    monkeypatch.setattr(package_kb, "_model_cache_files", lambda: (None, []))
    monkeypatch.setattr(package_kb, "_hf_schema_model", lambda: (None, []))
    monkeypatch.setattr(
        package_kb,
        "installed_kb_issues",
        lambda **_kwargs: ["missing engine database"],
    )
    monkeypatch.setattr(package_kb, "_SCHEMA_CACHE", tmp_path / "missing-cache.json")

    result = package_kb.build_bundle(tmp_path / "bundle.tar.gz", dry_run=True)

    assert result == 1


def test_package_allows_explicit_development_only_incomplete_bundle(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(package_kb, "_corpus_csvs", lambda: [])
    monkeypatch.setattr(package_kb, "_model_cache_files", lambda: (None, []))
    monkeypatch.setattr(package_kb, "_hf_schema_model", lambda: (None, []))
    monkeypatch.setattr(
        package_kb,
        "installed_kb_issues",
        lambda **_kwargs: ["missing engine database"],
    )
    monkeypatch.setattr(package_kb, "_SCHEMA_CACHE", tmp_path / "missing-cache.json")

    result = package_kb.build_bundle(
        tmp_path / "bundle.tar.gz",
        dry_run=True,
        allow_incomplete=True,
    )

    assert result == 0


def test_seed_rejects_incomplete_bundle_before_extraction(tmp_path: Path) -> None:
    payload = tmp_path / "placeholder.txt"
    payload.write_text("incomplete", encoding="utf-8")
    bundle = tmp_path / "incomplete.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        archive.add(payload, arcname=payload.name)

    assert seed_kb.seed(bundle, force=False) == 1
