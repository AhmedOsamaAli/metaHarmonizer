# `engine_adapter/` — developer guide

> **Read this first** if you are about to touch any ML-engine code,
> swap engines, write tests, or wire a new endpoint that needs the ML
> pipeline.

This package is the **only** place in the dashboard that knows which ML
engine is actually running. Routers, services, repositories and workers
talk to a small interface (`EngineProtocol`) and stay blissfully
ignorant. That decoupling is the whole point.

---

## 1. TL;DR

```python
from fastapi import Depends
from app.engine_adapter import EngineProtocol, get_engine

@router.post("/something")
def do_thing(engine: EngineProtocol = Depends(get_engine)):
    return engine.harmonize_schema(raw_df, curated_df, csv_path=path)
```

That's the entire contract. You never import `metaharmonizer`,
`src.*`, or `engine.src.*` outside this package. A pre-commit hook
([`scripts/check_engine_boundary.py`](../../../scripts/check_engine_boundary.py))
and the [`engine-boundary.yml`](../../../.github/workflows/engine-boundary.yml)
CI workflow enforce that rule.

---

## 2. What's in this folder?

```
backend/app/engine_adapter/
├── __init__.py             # get_engine() factory + public exports
├── protocol.py             # EngineProtocol  ← THE CONTRACT
├── types.py                # Pydantic DTOs (MappingRow, EngineHealth, …)
├── metaharmonizer_impl.py  # Wraps pip-installed upstream  (default)
├── mock_impl.py            # Fast deterministic fake  (tests)
└── README.md               # this file
```

| File                     | Purpose                                   | When you edit it                                         |
| ------------------------ | ----------------------------------------- | -------------------------------------------------------- |
| `protocol.py`            | The methods the rest of the app may call. | Adding a new capability.                                 |
| `types.py`               | Stable DTO shapes (Pydantic).             | Adding/changing a payload field.                         |
| `metaharmonizer_impl.py` | Wraps the upstream pip package.           | Upstream renames a field — fix `_to_dashboard_row` only. |
| `mock_impl.py`           | Used by every unit test.                  | Adding a new protocol method (must match shape).         |
| `__init__.py`            | Factory + cache.                          | Almost never — `get_engine()` is stable API.             |

---

## 3. Which adapter runs?

Selected at runtime by the **`ENGINE_IMPL`** environment variable:

| Value                      | Adapter                                                | When to use                                    |
| -------------------------- | ------------------------------------------------------ | ---------------------------------------------- |
| `metaharmonizer` (default) | `MetaHarmonizerAdapter` → `pip install metaharmonizer` | Normal operation.                              |
| `mock`                     | `MockEngineAdapter`                                    | Tests, local UI work without GPU/torch.        |

The upstream package looks for its schema files (`ncit_descendants.json`,
`field_value_dict.json`, optional alias dict) under
`$METAHARMONIZER_DATA_DIR/schema/`. If the env var is unset, the adapter
automatically points it at [`backend/data/`](../../data/), which ships
those files. To use a different bundle, set
`METAHARMONIZER_DATA_DIR=/some/path` before launching uvicorn.

```powershell
$env:ENGINE_IMPL = "mock"      # PowerShell
uvicorn app.main:app --reload
```

```bash
ENGINE_IMPL=mock uvicorn app.main:app --reload   # bash/zsh
```

The factory caches the chosen adapter for the process lifetime
(`@lru_cache`). Tests that flip `ENGINE_IMPL` mid-run should call
`reset_engine_cache()` from `app.engine_adapter`.

---

## 4. Common tasks

### 4.1 "I need a new method from the engine"

1. Add it to **`protocol.py`** with a docstring describing the input and the
   return shape (use the DTO types in `types.py`).
2. Implement it in **every** adapter (`metaharmonizer_impl.py`,
   `mock_impl.py`). The mock can return canned data; the real adapter
   wraps the upstream package.
3. Use it through `Depends(get_engine)` in your router or service.

If you forget any adapter, type-checking and the import-smoke test in
[`engine-boundary.yml`](../../../.github/workflows/engine-boundary.yml)
will catch it.

### 4.2 "Upstream renamed a field"

Open [`metaharmonizer_impl.py`](metaharmonizer_impl.py) and update
**`_to_dashboard_row`** (the translation function). That's the only
place in the codebase that knows upstream column names. Routers and
services see the stable dashboard shape and don't care.

### 4.3 "I want to write a unit test"

Use the mock — no torch, no internet:

```python
from fastapi.testclient import TestClient
from app.main import app
from app.engine_adapter import get_engine
from app.engine_adapter.mock_impl import MockEngineAdapter

app.dependency_overrides[get_engine] = lambda: MockEngineAdapter()
client = TestClient(app)

def test_harmonize_returns_one_row_per_column():
    with open("tests/fixtures/three_cols.csv", "rb") as f:
        r = client.post("/api/v1/harmonize", files={"file": ("x.csv", f, "text/csv")})
    assert r.status_code == 200
```

The mock runs in ~1 ms per call.

### 4.4 "I want to upgrade to a newer upstream SHA"

1. Rebuild the vendored wheel — see [`backend/vendor/README.md`](../../vendor/README.md) for the exact commands.
2. Move the new `.whl` into `backend/vendor/`, delete the old one, and update the filename in [`backend/requirements.txt`](../../requirements.txt) if the version bumped.
3. `pip install -r backend/requirements.txt --force-reinstall --no-deps ./vendor/metaharmonizer-<ver>-py3-none-any.whl`
4. Restart uvicorn and visit `http://localhost:8000/health/engine` —
   it should report `{"name": "metaharmonizer", "ok": true, "version": "…"}`.
5. Run a smoke harmonize against `metadata_samples/new_meta.csv`. If a
   field name changed upstream, fix `_to_dashboard_row` in
   [`metaharmonizer_impl.py`](metaharmonizer_impl.py) — that's the only
   file allowed to know upstream column names.

### 4.5 "I want to debug into the engine"

- For the upstream package: `pip install -e /path/to/local/MetaHarmonizer`
  (override the wheel install). Breakpoints in that checkout then work.
- Anywhere: drop a `logger.debug(...)` in the adapter and read the
  raw upstream output **before** the translation step.

The adapter is also the natural place to log every engine call for
replay or perf analysis.

### 4.6 "I want to swap the engine for a completely different model"

Write a new adapter:

```python
# backend/app/engine_adapter/my_engine_impl.py
class MyEngineAdapter:
    name = "my-engine"
    def harmonize_schema(self, raw_df, curated_df, *, csv_path=None): ...
    def map_values(self, raw_df, schema_mappings): ...
    def llm_match(self, csv_path, raw_column): ...
    def pre_warm(self): ...
    def health(self): ...
```

Register it in [`__init__.py`](__init__.py):

```python
if impl == "my-engine":
    from .my_engine_impl import MyEngineAdapter
    return MyEngineAdapter()
```

Set `ENGINE_IMPL=my-engine`. Done. No routers or services change.

---

## 5. The boundary rule

Outside `backend/app/engine_adapter/`, the following imports are
**forbidden**:

```python
import metaharmonizer
from metaharmonizer.anything import …
from src.anything import …          # legacy vendored layout
from engine.src.anything import …   # legacy vendored layout
```

Enforced by:

- `scripts/check_engine_boundary.py` (pre-commit + CI)
- `.pre-commit-config.yaml`
- `.github/workflows/engine-boundary.yml`

One allowance exists (see the script):

- `backend/tests/` — tests may import internals for white-box checks.

---

## 6. Migration status

| Step | What                                                     | Status |
| ---- | -------------------------------------------------------- | ------ |
| 1    | Seam created, routers go through `Depends(get_engine)`   | Done   |
| 2    | `MockEngineAdapter` available                            | Done   |
| 3    | `MetaHarmonizerAdapter` + opt-in `requirements.txt` line | Done   |
| 4    | Default flipped to `metaharmonizer`                      | Done   |
| 5    | `backend/engine/` and `backend/engine_upstream/` deleted | Done   |
| 6    | Pre-commit + CI                                          | Done   |

Migration complete. New work goes straight into
[`metaharmonizer_impl.py`](metaharmonizer_impl.py) or, for behaviour
changes, upstream at <https://github.com/shbrief/MetaHarmonizer>.

---

## 7. FAQ

**Q. Why isn't `ONTOLOGY_MAP` / `_STATIC_NCIT` behind the adapter?**
Those are dashboard-owned lookup tables, not engine output. They live
in [`app/services/harmonizer.py`](../services/harmonizer.py) and the
ontology router uses them directly. `MetaHarmonizerAdapter.map_values`
also delegates to `run_ontology_mapping` there so the API contract
stays unchanged. When upstream's `KnowledgeDb` (FAISS + SQLite) is
wired through `map_values`, those tables will be retired — see
proposal Section 1.4.4.

**Q. Why two adapters instead of one?**

- `metaharmonizer` is what runs in production and dev.
- `mock` is what gives us fast tests — no torch, no internet, ~1 ms/call.

Each is ~150 lines. The cost is trivial; the optionality is large.

**Q. Where do I report a bug in the upstream engine?**
https://github.com/shbrief/MetaHarmonizer/issues — and please mention
which SHA the dashboard is pinned to (see `backend/requirements.txt`).

---

## 8. See also

- [`scripts/check_engine_boundary.py`](../../../scripts/check_engine_boundary.py) — the rule, in code
- Upstream engine: <https://github.com/shbrief/MetaHarmonizer>
