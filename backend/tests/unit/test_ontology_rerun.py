from __future__ import annotations

import pytest

from app.services import ontology_rerun
from app.services.harmonizer import supports_ontology_mapping


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("old_field", "new_field"),
    [("notes", "body_site"), ("body_site", "body_site")],
)
async def test_field_edit_or_accept_into_ontology_adds_value_mappings(
    monkeypatch, old_field, new_field
):
    inserted: list[dict] = []

    class Engine:
        def map_values(self, raw_df, schema_mappings):
            assert raw_df.to_dict(orient="list") == {"biopsy_location": ["lung", "liver"]}
            assert schema_mappings == [
                {
                    "raw_column": "biopsy_location",
                    "matched_field": "body_site",
                    "curator_field": "body_site",
                }
            ]
            return [
                {
                    "field_name": "body_site",
                    "raw_value": value,
                    "ontology_term": value.title(),
                    "ontology_id": f"UBERON:{index}",
                    "confidence_score": 1.0,
                    "status": "accepted",
                }
                for index, value in enumerate(raw_df["biopsy_location"])
            ]

    async def delete_unreviewed(*args, **kwargs):
        return 0

    async def existing_keys(*args, **kwargs):
        return set()

    async def insert_rows(db, study_id, rows):
        assert study_id == "study-1"
        inserted.extend(rows)

    monkeypatch.setattr(ontology_rerun, "_column_values", lambda *args: ["lung", "liver"])
    monkeypatch.setattr(ontology_rerun, "get_engine", lambda: Engine())
    monkeypatch.setattr(ontology_rerun.ontology_repo, "delete_unreviewed_ontology", delete_unreviewed)
    monkeypatch.setattr(ontology_rerun.ontology_repo, "existing_value_keys", existing_keys)
    monkeypatch.setattr(ontology_rerun.ontology_repo, "insert_ontology_mappings", insert_rows)

    result = await ontology_rerun.rerun_column_ontology(
        object(),
        study_id="study-1",
        file_key="upload.csv",
        raw_column="biopsy_location",
        old_field=old_field,
        new_field=new_field,
    )

    assert result == {"added": 2, "removed": 0}
    assert {(row["field_name"], row["raw_value"]) for row in inserted} == {
        ("body_site", "lung"),
        ("body_site", "liver"),
    }


@pytest.mark.asyncio
async def test_field_edit_out_of_ontology_removes_only_repository_selected_rows(monkeypatch):
    calls: dict[str, object] = {}

    async def delete_unreviewed(db, study_id, fields, values):
        calls.update(study_id=study_id, fields=fields, values=values)
        return 2

    async def fail_insert(*args, **kwargs):
        pytest.fail("moving out of an ontology field must not insert rows")

    monkeypatch.setattr(ontology_rerun, "_column_values", lambda *args: ["lung", "liver"])
    monkeypatch.setattr(
        ontology_rerun,
        "get_engine",
        lambda: pytest.fail("moving out of an ontology field must not invoke the engine"),
    )
    monkeypatch.setattr(ontology_rerun.ontology_repo, "delete_unreviewed_ontology", delete_unreviewed)
    monkeypatch.setattr(ontology_rerun.ontology_repo, "insert_ontology_mappings", fail_insert)

    result = await ontology_rerun.rerun_column_ontology(
        object(),
        study_id="study-2",
        file_key="upload.csv",
        raw_column="biopsy_location",
        old_field="body_site",
        new_field="notes",
    )

    assert result == {"added": 0, "removed": 2}
    assert calls == {
        "study_id": "study-2",
        "fields": {"body_site", "notes"},
        "values": {"lung", "liver"},
    }


def test_dictionary_backed_fields_support_ontology_mapping():
    assert supports_ontology_mapping("sex")
    assert supports_ontology_mapping("country")
    assert supports_ontology_mapping("body_site")
    assert not supports_ontology_mapping("notes")