from __future__ import annotations

from app.engine_adapter import _ontology, kb_assets
from app.routers import health


def test_ontology_readiness_is_disabled_for_mock_engine(monkeypatch) -> None:
    monkeypatch.setenv("ENGINE_IMPL", "mock")
    monkeypatch.setenv("ONTOLOGY_ENGINE", "1")

    assert health._check_ontology_kb() == (True, "disabled")


def test_ontology_readiness_reports_missing_assets(monkeypatch) -> None:
    monkeypatch.setattr(kb_assets, "runtime_engine_required", lambda: True)
    monkeypatch.setattr(_ontology, "runtime_asset_issues", lambda: ["missing FAISS index"])

    ok, message = health._check_ontology_kb()

    assert not ok
    assert message == "error: incomplete (1 required asset(s) missing)"
