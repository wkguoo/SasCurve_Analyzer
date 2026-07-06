from __future__ import annotations

from app.core.data_model import CurveData, utc_now_iso


ANGSTROM_ALIASES = {"A^-1", "Å^-1", "1/A", "1/Å", "angstrom^-1"}
NM_ALIASES = {"nm^-1", "1/nm"}


def normalize_q_unit(unit: str) -> str:
    cleaned = unit.strip()
    if cleaned in ANGSTROM_ALIASES:
        return "A^-1"
    if cleaned in NM_ALIASES:
        return "nm^-1"
    raise ValueError(f"Unsupported q unit: {unit}")


def convert_q_unit(curve: CurveData, target_unit: str) -> CurveData:
    source = normalize_q_unit(curve.q_unit)
    target = normalize_q_unit(target_unit)
    if source == target:
        factor = 1.0
    elif source == "A^-1" and target == "nm^-1":
        factor = 10.0
    elif source == "nm^-1" and target == "A^-1":
        factor = 0.1
    else:
        raise ValueError(f"Unsupported q unit conversion: {source} to {target}")

    history_entry = {
        "action": "convert_q_unit",
        "created_at": utc_now_iso(),
        "source_unit": source,
        "target_unit": target,
        "factor": factor,
        "note": "Intensity values were not converted or scaled.",
    }
    return curve.copy_with(
        name=f"{curve.name}_{target.replace('^-1', '-1')}",
        q=curve.q * factor,
        q_unit=target,
        history_entry=history_entry,
    )

