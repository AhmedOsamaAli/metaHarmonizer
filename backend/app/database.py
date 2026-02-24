"""
MetaHarmonizer Dashboard — Database Layer

Uses SQLite for persistent storage with WAL mode for concurrent access.
Clean separation: all SQL lives here, services call these functions.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "metaharmonizer.db"


def _ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Return a synchronous SQLite connection with WAL mode and row factory."""
    _ensure_db_dir()
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS studies (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            upload_date   TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            file_path     TEXT,
            row_count     INTEGER,
            column_count  INTEGER
        );

        CREATE TABLE IF NOT EXISTS mappings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id         TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            raw_column       TEXT NOT NULL,
            matched_field    TEXT,
            confidence_score REAL,
            stage            TEXT,
            method           TEXT,
            alternatives     TEXT,          -- JSON array
            status           TEXT NOT NULL DEFAULT 'pending',
            curator_field    TEXT,
            curator_note     TEXT,
            reviewed_at      TEXT,
            reviewed_by      TEXT
        );

        CREATE TABLE IF NOT EXISTS ontology_mappings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id         TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            field_name       TEXT NOT NULL,
            raw_value        TEXT NOT NULL,
            ontology_term    TEXT,
            ontology_id      TEXT,
            confidence_score REAL,
            status           TEXT NOT NULL DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id    TEXT,
            action      TEXT NOT NULL,
            mapping_id  INTEGER,
            old_value   TEXT,
            new_value   TEXT,
            curator     TEXT,
            timestamp   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_mappings_study ON mappings(study_id);
        CREATE INDEX IF NOT EXISTS idx_onto_study ON ontology_mappings(study_id);
        CREATE INDEX IF NOT EXISTS idx_audit_study ON audit_log(study_id);
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Study CRUD
# ---------------------------------------------------------------------------

def create_study(
    study_id: str,
    name: str,
    file_path: str,
    row_count: int,
    column_count: int,
) -> dict:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO studies (id, name, upload_date, status, file_path, row_count, column_count)
           VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
        (study_id, name, now, file_path, row_count, column_count),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
    conn.close()
    return dict(row)


def get_study(study_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM studies WHERE id = ?", (study_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_studies() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM studies ORDER BY upload_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_study_status(study_id: str, status: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE studies SET status = ? WHERE id = ?", (status, study_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Mapping CRUD
# ---------------------------------------------------------------------------

def insert_mappings(study_id: str, mappings_list: list[dict]) -> None:
    conn = get_connection()
    for m in mappings_list:
        conn.execute(
            """INSERT INTO mappings
               (study_id, raw_column, matched_field, confidence_score,
                stage, method, alternatives, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                study_id,
                m["raw_column"],
                m.get("matched_field"),
                m.get("confidence_score"),
                m.get("stage"),
                m.get("method"),
                json.dumps(m.get("alternatives", [])),
                m.get("status", "pending"),
            ),
        )
    conn.commit()
    conn.close()


def get_mappings(study_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mappings WHERE study_id = ? ORDER BY confidence_score DESC",
        (study_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["alternatives"] = json.loads(d["alternatives"]) if d["alternatives"] else []
        result.append(d)
    return result


def get_mapping(mapping_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM mappings WHERE id = ?", (mapping_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["alternatives"] = json.loads(d["alternatives"]) if d["alternatives"] else []
        return d
    return None


def update_mapping_status(
    mapping_id: int,
    status: str,
    curator_field: Optional[str] = None,
    curator_note: Optional[str] = None,
    reviewed_by: str = "curator",
) -> Optional[dict]:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE mappings
           SET status = ?, curator_field = ?, curator_note = ?,
               reviewed_at = ?, reviewed_by = ?
           WHERE id = ?""",
        (status, curator_field, curator_note, now, reviewed_by, mapping_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM mappings WHERE id = ?", (mapping_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["alternatives"] = json.loads(d["alternatives"]) if d["alternatives"] else []
        return d
    return None


def batch_update_mapping_status(mapping_ids: list[int], status: str) -> int:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in mapping_ids)
    conn.execute(
        f"UPDATE mappings SET status = ?, reviewed_at = ? WHERE id IN ({placeholders})",
        [status, now] + mapping_ids,
    )
    conn.commit()
    affected = conn.execute(
        f"SELECT COUNT(*) as cnt FROM mappings WHERE id IN ({placeholders})",
        mapping_ids,
    ).fetchone()["cnt"]
    conn.close()
    return affected


# ---------------------------------------------------------------------------
# Ontology Mapping CRUD
# ---------------------------------------------------------------------------

def insert_ontology_mappings(study_id: str, onto_list: list[dict]) -> None:
    conn = get_connection()
    for o in onto_list:
        conn.execute(
            """INSERT INTO ontology_mappings
               (study_id, field_name, raw_value, ontology_term,
                ontology_id, confidence_score, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                study_id,
                o["field_name"],
                o["raw_value"],
                o.get("ontology_term"),
                o.get("ontology_id"),
                o.get("confidence_score"),
                o.get("status", "pending"),
            ),
        )
    conn.commit()
    conn.close()


def get_ontology_mappings(study_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM ontology_mappings WHERE study_id = ? ORDER BY field_name",
        (study_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

def add_audit_entry(
    study_id: str,
    action: str,
    mapping_id: Optional[int] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    curator: str = "curator",
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO audit_log
           (study_id, action, mapping_id, old_value, new_value, curator, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (study_id, action, mapping_id, old_value, new_value, curator, now),
    )
    conn.commit()
    conn.close()


def get_audit_log(study_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE study_id = ? ORDER BY timestamp DESC",
        (study_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
