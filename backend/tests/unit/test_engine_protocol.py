"""Engine-adapter conformance.

Every adapter must satisfy ``EngineProtocol`` so an upstream engine bump that
drops or renames a contract method is caught here (in CI) instead of at runtime
in the ontology/LLM path. ``@runtime_checkable`` on the protocol is otherwise
never exercised by the suite.
"""

from __future__ import annotations

import pytest

from app.engine_adapter.mock_impl import MockEngineAdapter
from app.engine_adapter.protocol import EngineProtocol

# The five methods routers/services/workers call through the adapter seam.
_REQUIRED = ("harmonize_schema", "map_values", "llm_match", "pre_warm", "health")


def _assert_methods(cls: type) -> None:
    for method in _REQUIRED:
        assert callable(getattr(cls, method, None)), f"{cls.__name__} is missing {method}()"


def test_mock_adapter_class_implements_protocol_methods() -> None:
    _assert_methods(MockEngineAdapter)


def test_mock_adapter_instance_satisfies_runtime_protocol() -> None:
    assert isinstance(MockEngineAdapter(), EngineProtocol)


def test_real_adapter_class_implements_protocol_methods() -> None:
    # Class-level check only: importing the class is cheap, but we never
    # instantiate the real engine here (that loads torch/models). Method
    # presence is enough to catch a dropped/renamed contract method on a bump.
    try:
        from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter
    except Exception as exc:  # noqa: BLE001 — engine wheel not installed (mock-only env)
        pytest.skip(f"metaharmonizer engine not importable: {exc}")
    _assert_methods(MetaHarmonizerAdapter)
