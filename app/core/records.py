from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from app.core.data_model import FormalRecord, HistoryRecord


def create_history_record(action_type: str, input_ids=None, output_ids=None, parameters=None, user_note: str = "", warnings=None) -> HistoryRecord:
    return HistoryRecord.create(action_type, input_ids=input_ids, output_ids=output_ids, parameters=parameters, user_note=user_note, warnings=warnings)


def create_formal_record(source_type: str, source_id: str, title: str, **kwargs) -> FormalRecord:
    return FormalRecord.create(source_type=source_type, source_id=source_id, title=title, **kwargs)


def _dataclass_kwargs(cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in allowed}


def _as_float_pair(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Expected a length-2 q_range, got {value!r}.")
    return float(value[0]), float(value[1])


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
    history = [HistoryRecord(**_dataclass_kwargs(HistoryRecord, record)) for record in payload.get("history", [])]
    formal: list[FormalRecord] = []
    for record in payload.get("formal", []):
        fields_payload = _dataclass_kwargs(FormalRecord, record)
        if "q_range" in fields_payload and fields_payload["q_range"] is not None:
            fields_payload["q_range"] = _as_float_pair(fields_payload["q_range"])
        formal.append(FormalRecord(**fields_payload))
    return history, formal
