"""Self-cleaning production audit against a deployed MetaHarmonizer instance."""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import secrets
import time
import uuid
import zipfile
from dataclasses import dataclass, field

import httpx
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.storage import get_storage
from app.db.models import JobRun, Mapping, OntologyMapping, Study, User
from app.db.session import SessionLocal


class AuditFailure(RuntimeError):
    pass


@dataclass
class AuditReport:
    passed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def pass_(self, name: str, detail: str = "") -> None:
        self.passed.append(name)
        print(f"[PASS] {name}{': ' + detail if detail else ''}", flush=True)

    def skip(self, name: str, detail: str) -> None:
        self.skipped.append(name)
        print(f"[SKIP] {name}: {detail}", flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditFailure(message)


def checked(response: httpx.Response, expected: int | tuple[int, ...] = 200) -> httpx.Response:
    statuses = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in statuses:
        body = response.text[:500]
        raise AuditFailure(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}, expected {statuses}: {body}"
        )
    return response


async def create_audit_users() -> tuple[User, str, User, str]:
    suffix = uuid.uuid4().hex[:12]
    admin_password = secrets.token_urlsafe(24)
    curator_password = secrets.token_urlsafe(24)
    async with SessionLocal() as db:
        admin = User(
            email=f"production-audit-admin-{suffix}@example.com",
            name="Production Audit Admin",
            role="admin",
            password_hash=hash_password(admin_password),
            is_active=True,
            email_verified=True,
            approved=True,
        )
        curator = User(
            email=f"production-audit-curator-{suffix}@example.com",
            name="Production Audit Curator",
            role="curator",
            password_hash=hash_password(curator_password),
            is_active=True,
            email_verified=True,
            approved=True,
        )
        db.add_all([admin, curator])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(curator)
        return admin, admin_password, curator, curator_password


async def cleanup(user_ids: list[int], study_id: str | None, file_key: str | None) -> None:
    async with SessionLocal() as db:
        if study_id:
            await db.execute(delete(Study).where(Study.id == study_id))
            await db.execute(delete(JobRun).where(JobRun.study_id == study_id))
        if user_ids:
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    if file_key:
        get_storage().delete(file_key)


async def login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    response = checked(
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "remember": False},
        )
    )
    payload = response.json()
    require(payload.get("access_token"), "login returned no access token")
    return payload


async def run(origin: str) -> AuditReport:
    report = AuditReport()
    admin: User | None = None
    curator: User | None = None
    study_id: str | None = None
    file_key: str | None = None
    sample = (
        "participant_id,biopsy_location,diagnosis,treatment_name\n"
        "P001,lung,CRC,chemotherapy\n"
        "P002,liver,IBD,radiotherapy\n"
        "P003,lung,CRC,chemotherapy\n"
    ).encode()

    try:
        admin, admin_password, curator, curator_password = await create_audit_users()
        async with httpx.AsyncClient(base_url=origin.rstrip("/"), timeout=180.0) as client:
            health = checked(await client.get("/healthz")).json()
            ready = checked(await client.get("/readyz")).json()
            require(health == {"status": "ok"}, f"unexpected liveness payload: {health}")
            require(ready.get("ready") is True, f"deployment not ready: {ready}")
            report.pass_("liveness and dependency readiness")

            home = checked(await client.get("/"))
            require("MetaHarmonizer" in home.text, "SPA root does not contain the app shell")
            require(home.headers.get("strict-transport-security"), "HSTS header missing")
            require(home.headers.get("content-security-policy"), "CSP header missing")
            report.pass_("HTTPS app shell and security headers")

            admin_login = await login(client, admin.email, admin_password)
            token = admin_login["access_token"]
            auth = {"Authorization": f"Bearer {token}"}
            me = checked(await client.get("/api/v1/auth/me", headers=auth)).json()
            require(me["id"] == admin.id and me["role"] == "admin", "admin identity mismatch")
            sessions = checked(await client.get("/api/v1/auth/sessions", headers=auth)).json()
            require(len(sessions) >= 1, "login session was not persisted")
            report.pass_("JWT login, identity, and sessions")

            config = checked(await client.get("/api/v1/config")).json()
            if config.get("llm_enabled"):
                report.pass_("LLM feature configuration")
            else:
                report.skip("Gemini LLM rematch", "GEMINI_API_KEY is not configured")

            token_created = checked(
                await client.post("/api/v1/tokens", headers=auth, json={"scope": "read"}),
                201,
            ).json()
            api_token = token_created["token"]
            token_auth = {"Authorization": f"Bearer {api_token}"}
            checked(await client.get("/api/v1/auth/me", headers=token_auth))
            listed_tokens = checked(await client.get("/api/v1/tokens", headers=auth)).json()
            require(any(row["id"] == token_created["id"] for row in listed_tokens), "API token not listed")
            checked(await client.delete(f"/api/v1/tokens/{token_created['id']}", headers=auth), 204)
            report.pass_("personal API token lifecycle")

            for path in (
                "/api/v1/schema-versions",
                "/api/v1/target-schemas",
                "/api/v1/ontology/snapshots",
                "/api/v1/admin/users",
                "/api/v1/admin/schema-versions",
                "/api/v1/admin/schema-aliases",
                "/api/v1/admin/schema-fields",
                "/api/v1/admin/schema-aliases/entries",
            ):
                checked(await client.get(path, headers=auth))
            report.pass_("schema, ontology snapshot, and admin catalog reads")

            ticket = checked(await client.post("/api/v1/ws/ticket", headers=auth)).json()
            require(ticket.get("ticket"), "WebSocket ticket was not minted")
            report.pass_("WebSocket ticket minting")

            upload = checked(
                await client.post(
                    "/api/v1/harmonize",
                    headers=auth,
                    files={"file": ("production_audit.csv", sample, "text/csv")},
                    data={"mode": "both"},
                ),
                202,
            ).json()
            study_id = upload["study_id"]
            require(upload.get("row_count") == 3, f"upload row count wrong: {upload}")
            require(upload.get("column_count") == 4, f"upload column count wrong: {upload}")
            report.pass_("CSV upload and queued harmonization", study_id)

            deadline = time.monotonic() + 900
            status = "queued"
            while time.monotonic() < deadline:
                study_response = checked(
                    await client.get(f"/api/v1/studies/{study_id}", headers=auth)
                ).json()
                file_key = study_response.get("file_path")
                status = study_response["status"]
                if status in {"review", "failed", "error"}:
                    break
                await asyncio.sleep(2)
            require(status == "review", f"real engine ended in status {status}")
            job = checked(await client.get(f"/api/v1/jobs/{study_id}", headers=auth)).json()
            require(job.get("state") == "succeeded", f"job state is not succeeded: {job}")
            result = checked(await client.get(f"/api/v1/harmonize/{study_id}", headers=auth)).json()
            require(result.get("total") == 4, f"engine returned wrong schema count: {result.get('total')}")
            report.pass_("real queue worker and engine completion")

            curator_login = await login(client, curator.email, curator_password)
            curator_auth = {"Authorization": f"Bearer {curator_login['access_token']}"}
            hidden = await client.get(f"/api/v1/mappings/{study_id}", headers=curator_auth)
            require(hidden.status_code == 404, f"foreign curator received {hidden.status_code}, expected 404")
            report.pass_("cross-owner study isolation")

            mappings = checked(await client.get(f"/api/v1/mappings/{study_id}", headers=auth)).json()
            require(len(mappings) == 4, f"expected 4 schema mappings, got {len(mappings)}")
            by_column = {row["raw_column"]: row for row in mappings}
            require(set(by_column) == {"participant_id", "biopsy_location", "diagnosis", "treatment_name"}, "schema output columns differ from input")
            queue = checked(await client.get(f"/api/v1/mappings/{study_id}/review-queue", headers=auth)).json()
            require("stats" in queue and "items" in queue, "review queue shape invalid")
            context = checked(
                await client.get(
                    f"/api/v1/mappings/{study_id}/columns/biopsy_location/context",
                    headers=auth,
                )
            ).json()
            require(context["distinct_values"] == 2 and context["total_rows"] == 3, f"column context wrong: {context}")
            report.pass_("schema mappings, review queue, and column context")

            mapping_id = by_column["biopsy_location"]["id"]
            checked(
                await client.post(
                    f"/api/v1/mappings/{mapping_id}/edit",
                    headers=auth,
                    json={"new_field": "notes", "note": "production audit transition"},
                )
            )
            after_out = checked(
                await client.get(f"/api/v1/ontology/mappings/{study_id}", headers=auth)
            ).json()
            stale = [
                row for row in after_out
                if row["field_name"] == "body_site" and row["raw_value"] in {"lung", "liver"}
            ]
            require(not stale, f"stale body_site rows remained after field moved out: {stale}")

            checked(
                await client.post(
                    f"/api/v1/mappings/{mapping_id}/edit",
                    headers=auth,
                    json={"new_field": "body_site", "note": "production audit rerun"},
                )
            )
            async with SessionLocal() as db:
                mapping_row = await db.get(Mapping, mapping_id)
                require(mapping_row is not None, "synthetic schema mapping disappeared")
                mapping_row.status = "pending"
                mapping_row.reviewed_at = None
                mapping_row.reviewed_by = None
                await db.execute(
                    delete(OntologyMapping).where(
                        OntologyMapping.study_id == study_id,
                        OntologyMapping.field_name == "body_site",
                        OntologyMapping.raw_value.in_({"lung", "liver"}),
                    )
                )
                await db.commit()
            cleared = checked(
                await client.get(f"/api/v1/ontology/mappings/{study_id}", headers=auth)
            ).json()
            require(
                not [
                    row for row in cleared
                    if row["field_name"] == "body_site"
                    and row["raw_value"] in {"lung", "liver"}
                ],
                "synthetic ontology rows were not cleared before acceptance test",
            )
            checked(
                await client.post(f"/api/v1/mappings/{mapping_id}/accept", headers=auth)
            )
            ontology = checked(
                await client.get(f"/api/v1/ontology/mappings/{study_id}", headers=auth)
            ).json()
            body_rows = [
                row for row in ontology
                if row["field_name"] == "body_site" and row["raw_value"] in {"lung", "liver"}
            ]
            require({row["raw_value"] for row in body_rows} == {"lung", "liver"}, f"ontology rerun missed values: {body_rows}")
            require(all(row.get("ontology_term") and row.get("ontology_id") for row in body_rows), f"ontology rerun returned uncoded rows: {body_rows}")
            report.pass_("schema acceptance reruns real ontology mapping")

            remaining_ids = [row["id"] for row in mappings if row["id"] != mapping_id]
            batch = checked(
                await client.post(
                    "/api/v1/mappings/batch",
                    headers=auth,
                    json={"mapping_ids": remaining_ids, "action": "accepted"},
                )
            ).json()
            require(batch["updated"] == len(remaining_ids), f"batch update count wrong: {batch}")
            final_mappings = checked(
                await client.get(f"/api/v1/mappings/{study_id}", headers=auth)
            ).json()
            require(all(row["status"] == "accepted" for row in final_mappings), "not all schema mappings are accepted")
            report.pass_("schema edit and batch approval persistence")

            search = checked(
                await client.get("/api/v1/ontology/search", params={"query": "lung", "limit": 5})
            ).json()
            require(search and any(row.get("ontology_id") for row in search), "ontology search returned no coded results")
            suggestions = checked(
                await client.post(f"/api/v1/ontology/suggest/{study_id}", headers=auth)
            ).json()
            require("suggestions" in suggestions, "ontology suggestion payload invalid")
            for row in ontology:
                if row.get("ontology_term") and row["status"] != "accepted":
                    checked(
                        await client.post(
                            f"/api/v1/ontology/mappings/{row['id']}/accept",
                            headers=auth,
                        )
                    )
            report.pass_("ontology search, suggestions, and curation")

            quality = checked(await client.get(f"/api/v1/quality/{study_id}", headers=auth)).json()
            require(quality["total_columns"] == 4, f"quality total wrong: {quality}")
            current = checked(await client.get(f"/api/v1/mappings/{study_id}", headers=auth)).json()
            truth = {
                row["raw_column"]: row.get("curator_field") or row.get("matched_field") or ""
                for row in current
            }
            evaluation = checked(
                await client.post(
                    f"/api/v1/quality/{study_id}/evaluate",
                    headers=auth,
                    json={"ground_truth": truth},
                )
            ).json()
            require(evaluation["f1"] == 1.0 and evaluation["evaluated_columns"] == 4, f"quality evaluation wrong: {evaluation}")
            report.pass_("quality metrics and accuracy evaluation")

            harmonized_response = checked(
                await client.get(f"/api/v1/export/{study_id}/harmonized", headers=auth)
            )
            harmonized = list(csv.DictReader(io.StringIO(harmonized_response.text)))
            require(len(harmonized) == 3, "harmonized export row count changed")
            require("body_site" in harmonized[0], f"harmonized export lacks curated body_site: {list(harmonized[0])}")

            cbio = checked(await client.get(f"/api/v1/export/{study_id}/cbioportal", headers=auth))
            require(len(cbio.content) > 100, "cBioPortal text export is unexpectedly empty")
            archive = checked(
                await client.get(f"/api/v1/export/{study_id}/cbioportal-study", headers=auth)
            )
            with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                names = set(bundle.namelist())
                require(any(name.startswith("meta_") for name in names), f"cBioPortal ZIP lacks metadata files: {names}")
                require(any("clinical" in name for name in names), f"cBioPortal ZIP lacks clinical data: {names}")

            labeled = checked(await client.get(f"/api/v1/export/{study_id}/labeled", headers=auth))
            require(len(labeled.text.splitlines()) > 1, "study labeled export has no records")
            global_labeled = checked(await client.get("/api/v1/export/labeled", headers=auth))
            require(len(global_labeled.text.splitlines()) > 1, "global labeled export has no records")
            linkml = checked(await client.get(f"/api/v1/export/{study_id}/linkml-check", headers=auth)).json()
            require("ok" in linkml and "violations" in linkml, f"LinkML payload invalid: {linkml}")
            report_payload = checked(
                await client.get(f"/api/v1/export/{study_id}/report", headers=auth)
            ).json()
            require(report_payload.get("study", {}).get("id") == study_id, "mapping report study identity mismatch")
            report.pass_("harmonized, cBioPortal, labeled, LinkML, and audit exports")

            audit = checked(
                await client.get(
                    "/api/v1/audit",
                    headers=auth,
                    params={"study_id": study_id, "limit": 100},
                )
            ).json()
            actions = {row["action"] for row in audit["items"]}
            require("harmonize.completed" in actions and "edit" in actions, f"audit trail incomplete: {actions}")
            metrics = checked(await client.get("/metrics", headers=auth))
            require("http" in metrics.text.lower(), "Prometheus metrics payload looks empty")
            report.pass_("append-only audit query and Prometheus metrics")

            fed_key = checked(await client.get("/api/v1/federation/public-key", headers=auth)).json()
            require(len(fed_key.get("public_key", "")) == 64, f"federation public key invalid: {fed_key}")
            fed_export = checked(await client.get("/api/v1/federation/export", headers=auth)).json()
            require("payload" in fed_export and "signature" in fed_export, "federation export shape invalid")
            invalid_import = await client.post(
                "/api/v1/federation/import",
                headers=auth,
                json={"payload": {"source_instance": "untrusted"}, "signature": "bad"},
            )
            require(invalid_import.status_code == 400, f"invalid federation import returned {invalid_import.status_code}")
            report.pass_("federation signing and invalid-signature rejection")

            completed = checked(
                await client.post(f"/api/v1/studies/{study_id}/complete", headers=auth)
            ).json()
            require(completed["status"] == "completed", "study completion did not persist")
            active = checked(await client.get("/api/v1/studies", headers=auth)).json()
            require(all(row["id"] != study_id for row in active), "completed study remains in active list")
            checked(await client.delete(f"/api/v1/studies/{study_id}", headers=auth), 204)
            missing = await client.get(f"/api/v1/studies/{study_id}", headers=auth)
            require(missing.status_code == 404, f"deleted study returned {missing.status_code}")
            report.pass_("study completion, filing, and deletion")

        print(
            f"AUDIT_OK passed={len(report.passed)} skipped={len(report.skipped)}",
            flush=True,
        )
        return report
    finally:
        await cleanup(
            [user.id for user in (admin, curator) if user is not None],
            study_id,
            file_key,
        )
        print("[CLEANUP] temporary users, study, jobs, and upload removed", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.origin))
    except Exception as exc:
        print(f"AUDIT_FAILED {type(exc).__name__}: {exc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
