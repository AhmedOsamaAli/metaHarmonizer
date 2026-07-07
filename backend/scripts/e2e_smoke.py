"""End-to-end smoke test against a REAL running stack.

Drives the full curator journey over HTTP against a live uvicorn server that is
wired to real Postgres, real Redis, the real metaharmonizer engine, and the
pre-built ontology KB:

    register (bootstrap admin) -> login -> upload CSV -> harmonize (schema +
    ontology, real engine + real KB) -> inspect schema mappings -> accept one ->
    inspect ontology mappings (proves real FAISS/KB retrieval) -> accept one ->
    export (cbioPortal + harmonized).

This is NOT a unit test; it talks to a server the caller must have started with
the right environment. Run via scripts/run_e2e_smoke.ps1 which provisions an
isolated DB, starts the server, and invokes this driver.

Exit code 0 = every stage passed; non-zero = a stage failed (details printed).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8099/api/v1"
# Default sample; override with E2E_CSV to stress-test other/bigger datasets.
_DEFAULT_CSV = Path(__file__).resolve().parents[2] / "metadata_samples" / "new_meta.csv"
CSV = Path(os.getenv("E2E_CSV", str(_DEFAULT_CSV)))
ADMIN_EMAIL = "admin@example.com"
# Fixed (not random) so re-runs against a persisted DB still authenticate.
ADMIN_PW = "DemoPortal2026!"


def _log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"[e2e] FAIL: {msg}", flush=True)
    sys.exit(1)


def _req(c: httpx.Client, method: str, url: str, *, tries: int = 6, **kw) -> httpx.Response:
    """HTTP call resilient to transient resets — the single-worker dev server's
    event loop can be briefly saturated by the inline job + outbound API calls,
    which aborts an in-flight read on Windows. Retry rather than fail the run."""
    last: Exception | None = None
    for i in range(tries):
        try:
            return c.request(method, url, **kw)
        except httpx.HTTPError as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


def main() -> int:
    if not CSV.exists():
        _fail(f"sample CSV not found: {CSV}")

    with httpx.Client(timeout=60.0) as c:
        # 1) Wait for the server to come up (cold model load can take a while).
        for _ in range(300):
            try:
                r = c.get("http://127.0.0.1:8099/health")
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            _fail("server did not become healthy on :8099")
        _log("server healthy")

        # 2) Register the bootstrap admin (auto-verified) + log in.
        r = c.post(
            f"{BASE}/auth/register",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PW, "name": "E2E Admin"},
        )
        if r.status_code not in (201, 409, 400, 403):
            _fail(f"register unexpected {r.status_code}: {r.text}")
        _log(f"register -> {r.status_code}")

        r = c.post(
            f"{BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
        )
        if r.status_code != 200:
            _fail(f"login failed {r.status_code}: {r.text}")
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        _log("login ok")

        # 3) Upload + harmonize (schema + ontology) with the real engine.
        with open(CSV, "rb") as fh:
            r = c.post(
                f"{BASE}/harmonize",
                headers=auth,
                files={"file": (CSV.name, fh, "text/csv")},
                data={"mode": "both"},
            )
        if r.status_code != 202:
            _fail(f"harmonize upload failed {r.status_code}: {r.text}")
        body = r.json()
        study_id = body["study_id"]
        _log(f"uploaded study_id={study_id} rows={body.get('row_count')} cols={body.get('column_count')}")

        # 4) Poll study status until terminal (real engine can take minutes).
        deadline = time.time() + 30 * 60
        status = None
        while time.time() < deadline:
            r = _req(c, "GET", f"{BASE}/studies/{study_id}", headers=auth)
            if r.status_code == 200:
                status = (r.json() or {}).get("status")
                _log(f"status={status}")
                if status in {"completed", "done", "ready", "review", "failed", "error"}:
                    break
            time.sleep(5)
        if status in {"failed", "error"}:
            _fail(f"harmonization job ended in status={status}")
        if status not in {"completed", "done", "ready", "review"}:
            _fail(f"harmonization did not finish in time (last status={status})")
        _log(f"harmonization finished: {status}")

        # 5) Schema mappings.
        r = c.get(f"{BASE}/mappings/{study_id}", headers=auth)
        if r.status_code != 200:
            _fail(f"get schema mappings failed {r.status_code}: {r.text}")
        mappings = r.json()
        if not mappings:
            _fail("no schema mappings returned")
        by_stage: dict[str, int] = {}
        for m in mappings:
            by_stage[m.get("stage", "?")] = by_stage.get(m.get("stage", "?"), 0) + 1
        _log(f"schema mappings: {len(mappings)} rows; by stage: {by_stage}")

        # 6) Accept one schema mapping.
        first = mappings[0]
        mid = first.get("id") or first.get("mapping_id")
        r = c.post(f"{BASE}/mappings/{mid}/accept", headers=auth)
        _log(f"accept schema mapping {mid} -> {r.status_code}")
        if r.status_code not in (200, 201):
            _fail(f"accept schema mapping failed {r.status_code}: {r.text}")

        # 7) Ontology mappings — proves real KB / FAISS retrieval.
        r = c.get(f"{BASE}/ontology/mappings/{study_id}", headers=auth)
        if r.status_code != 200:
            _fail(f"get ontology mappings failed {r.status_code}: {r.text}")
        onto = r.json()
        _log(f"ontology mappings: {len(onto)} rows")
        with_id = [o for o in onto if o.get("ontology_id")]
        sample = [
            f"{o.get('field_name')}:{o.get('raw_value')!r}->{o.get('ontology_term')}"
            f"({o.get('ontology_id')},{o.get('confidence_score')})"
            for o in with_id[:8]
        ]
        for s in sample:
            _log(f"  KB hit: {s}")
        if not with_id:
            _fail("ontology pass returned no ontology_id hits — KB retrieval not proven")
        _log(f"ontology hits with an ontology_id: {len(with_id)}/{len(onto)}")

        # 8) Accept one ontology mapping.
        oid = with_id[0].get("id") or with_id[0].get("mapping_id")
        if oid is not None:
            r = c.post(f"{BASE}/ontology/mappings/{oid}/accept", headers=auth)
            _log(f"accept ontology mapping {oid} -> {r.status_code}")

        # 9) Exports.
        for path in ("harmonized", "cbioportal"):
            r = c.get(f"{BASE}/export/{study_id}/{path}", headers=auth)
            if r.status_code != 200 or not r.content:
                _fail(f"export {path} failed {r.status_code} (len={len(r.content)})")
            out = Path(__file__).resolve().parent / f"e2e_export_{path}.csv"
            out.write_bytes(r.content)
            _log(f"export {path}: {len(r.content)} bytes -> {out.name}")

    _log("ALL STAGES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
