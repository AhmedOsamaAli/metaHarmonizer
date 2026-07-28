"""
engine_adapter — the single seam between dashboard code and any ML engine.

Public API::

    from app.engine_adapter import get_engine, EngineProtocol

    def my_route(engine: EngineProtocol = Depends(get_engine)):
        rows = engine.harmonize_schema(raw_df, curated_df, csv_path=path)

The concrete implementation is chosen by the ``ENGINE_IMPL`` env var:

    ENGINE_IMPL=metaharmonizer (default — pip-installed upstream package)
    ENGINE_IMPL=mock           (fast deterministic fake; for tests)

See ``backend/app/engine_adapter/README.md`` for the developer guide
and the full design.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from .protocol import EngineProtocol
from ._ontology import is_ontology_field
from .types import (
    Alternative,
    EngineHealth,
    LLMSuggestion,
    MappingRow,
    OntologyMappingRow,
    Stage,
)

logger = logging.getLogger(__name__)


__all__ = [
    "EngineProtocol",
    "get_engine",
    "reset_engine_cache",
    "is_ontology_field",
    "Alternative",
    "EngineHealth",
    "LLMSuggestion",
    "MappingRow",
    "OntologyMappingRow",
    "Stage",
]


@lru_cache(maxsize=1)
def _build_engine(impl: str) -> EngineProtocol:
    """Construct the chosen adapter exactly once per process."""
    impl = (impl or "metaharmonizer").lower().strip()
    if impl == "mock":
        from .mock_impl import MockEngineAdapter

        logger.info("engine_adapter: using MockEngineAdapter")
        return MockEngineAdapter()
    if impl == "metaharmonizer":
        from .metaharmonizer_impl import MetaHarmonizerAdapter

        logger.info("engine_adapter: using MetaHarmonizerAdapter (pip-installed)")
        return MetaHarmonizerAdapter()
    raise ValueError(
        f"Unknown ENGINE_IMPL={impl!r}. Use one of: metaharmonizer, mock."
    )


def get_engine() -> EngineProtocol:
    """
    FastAPI dependency. Returns the singleton adapter for this process.

    Tests can override per-request via::

        app.dependency_overrides[get_engine] = lambda: MockEngineAdapter()
    """
    return _build_engine(os.getenv("ENGINE_IMPL", "metaharmonizer"))


def reset_engine_cache() -> None:
    """Drop the singleton — useful in tests that switch ``ENGINE_IMPL`` at runtime."""
    _build_engine.cache_clear()
