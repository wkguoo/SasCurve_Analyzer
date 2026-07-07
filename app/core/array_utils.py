from __future__ import annotations

from typing import Any

import numpy as np


def sort_arrays_by_q(q: Any, *arrays: Any) -> tuple[np.ndarray, ...]:
    q_array = np.asarray(q, dtype=float)
    order = np.argsort(q_array, kind="mergesort")
    sorted_arrays: list[np.ndarray] = [q_array[order]]
    for array in arrays:
        sorted_arrays.append(np.asarray(array, dtype=float)[order])
    return tuple(sorted_arrays)
