from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.graft_efo import _copy_efo_tables


def _rows(path: Path, table: str) -> list[tuple]:
    with sqlite3.connect(path) as connection:
        return connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()


def test_copy_efo_tables_preserves_source_and_replaces_destination(tmp_path: Path):
    old_db = tmp_path / "old.sqlite"
    new_db = tmp_path / "new.sqlite"
    with sqlite3.connect(old_db) as connection:
        connection.execute('CREATE TABLE "efo_synonym_phenotype" (id INTEGER, label TEXT)')
        connection.executemany(
            'INSERT INTO "efo_synonym_phenotype" VALUES (?, ?)',
            [(1, "alpha"), (2, "beta")],
        )
        connection.execute('CREATE TABLE "not_efo" (id INTEGER)')
    with sqlite3.connect(new_db) as connection:
        connection.execute('CREATE TABLE "efo_synonym_phenotype" (id INTEGER, label TEXT)')
        connection.execute('INSERT INTO "efo_synonym_phenotype" VALUES (9, "stale")')

    _copy_efo_tables(old_db, new_db)

    expected = [(1, "alpha"), (2, "beta")]
    assert _rows(old_db, "efo_synonym_phenotype") == expected
    assert _rows(new_db, "efo_synonym_phenotype") == expected
    with sqlite3.connect(new_db) as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "not_efo" not in names


def test_copy_efo_tables_handles_source_only_table(tmp_path: Path):
    old_db = tmp_path / "old.sqlite"
    new_db = tmp_path / "new.sqlite"
    with sqlite3.connect(old_db) as connection:
        connection.execute('CREATE TABLE "efo_phenotype" (id INTEGER)')
        connection.execute('INSERT INTO "efo_phenotype" VALUES (1)')
    sqlite3.connect(new_db).close()

    _copy_efo_tables(old_db, new_db)

    assert _rows(old_db, "efo_phenotype") == [(1,)]
    assert _rows(new_db, "efo_phenotype") == [(1,)]