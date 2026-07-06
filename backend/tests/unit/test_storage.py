"""Unit tests for the blob-storage abstraction (local backend + selection)."""

from __future__ import annotations

from pathlib import Path

from app.core.storage import LocalStorage, S3Storage, get_storage


def test_local_storage_round_trip(tmp_path):
    base = tmp_path / "store"
    src = tmp_path / "src.csv"
    src.write_text("a,b\n1,2\n")
    st = LocalStorage(base=base)

    st.store("study1.csv", src)
    assert st.exists("study1.csv")
    with st.local("study1.csv") as p:
        assert Path(p).read_text() == "a,b\n1,2\n"

    st.delete("study1.csv")
    assert not st.exists("study1.csv")


def test_local_storage_store_is_noop_when_already_in_place(tmp_path):
    base = tmp_path / "store"
    base.mkdir()
    f = base / "study2.csv"
    f.write_text("x")
    st = LocalStorage(base=base)
    st.store("study2.csv", f)  # src == dst → must not fail/duplicate
    assert f.read_text() == "x"


def test_local_storage_accepts_legacy_absolute_path(tmp_path):
    legacy = tmp_path / "old_abs.csv"
    legacy.write_text("y")
    st = LocalStorage(base=tmp_path / "store")
    assert st.exists(str(legacy))
    with st.local(str(legacy)) as p:
        assert Path(p) == legacy


def test_get_storage_selects_backend(monkeypatch):
    import app.core.storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "object_store_url", "file:///app/data/objects", raising=False)
    get_storage.cache_clear()
    assert isinstance(get_storage(), LocalStorage)

    monkeypatch.setattr(storage_mod.settings, "object_store_url", "s3://my-bucket", raising=False)
    monkeypatch.setattr(storage_mod.settings, "r2_bucket", None, raising=False)
    get_storage.cache_clear()
    assert isinstance(get_storage(), S3Storage)

    get_storage.cache_clear()
