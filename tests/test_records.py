from __future__ import annotations

from app.core.records import create_formal_record, create_history_record, load_records, save_records


def test_history_record_create() -> None:
    record = create_history_record("import", input_ids=["file"], output_ids=["curve"])
    assert record.action_type == "import"
    assert record.record_id


def test_formal_record_create() -> None:
    record = create_formal_record("curve", "curve-1", "Important curve")
    assert record.source_type == "curve"
    assert record.formal_id


def test_save_and_load_records(tmp_path) -> None:
    history = [create_history_record("analysis", input_ids=["curve"], output_ids=["analysis"])]
    formal = [create_formal_record("analysis", "analysis", "Selected analysis")]
    path = tmp_path / "records.json"
    save_records(path, history, formal)
    loaded_history, loaded_formal = load_records(path)
    assert loaded_history[0].action_type == "analysis"
    assert loaded_formal[0].title == "Selected analysis"

