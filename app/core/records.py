from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.core.data_model import FormalRecord, HistoryRecord


def create_history_record(action_type: str, input_ids=None, output_ids=None, parameters=None, user_note: str = "", warnings=None) -> HistoryRecord:
    return HistoryRecord.create(action_type, input_ids=input_ids, output_ids=output_ids, parameters=parameters, user_note=user_note, warnings=warnings)


def create_formal_record(source_type: str, source_id: str, title: str, **kwargs) -> FormalRecord:
    return FormalRecord.create(source_type=source_type, source_id=source_id, title=title, **kwargs)


def save_records(path: str | Path, history: list[HistoryRecord], formal: list[FormalRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "history": [asdict(record) for record in history],
        "formal": [asdict(record) for record in formal],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_records(path: str | Path) -> tuple[list[HistoryRecord], list[FormalRecord]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    history = [HistoryRecord(**record) for record in payload.get("history", [])]
    formal = [FormalRecord(**record) for record in payload.get("formal", [])]
    return history, formal

