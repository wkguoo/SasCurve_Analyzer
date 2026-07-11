"""Serializable, defensive diagnostics shared by numerical SAS fits.

The helpers in this module deliberately do not perform fitting or file I/O.  They
turn arrays already selected by a fitting method into traceable statistics,
parameter rows, covariance correlations, and row-preserving residual records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


# A small negative eigenvalue can arise when a numerically PSD covariance is
# reconstructed from floating-point optimization output.  Values below this
# relative tolerance are treated as round-off; materially negative values are
# rejected instead of being exported as plausible correlations.
COVARIANCE_PSD_RELATIVE_TOLERANCE = 1e-10


@dataclass(frozen=True)
class FitDiagnostics:
    """JSON-serializable common fit statistics.

    ``None`` means that a quantity is not applicable or cannot be calculated
    reliably from the supplied arrays.  This is intentionally different from
    replacing a missing statistic with zero.
    """

    n: int
    parameter_count: int
    dof: int
    rss: float | None = None
    wrss: float | None = None
    rmse: float | None = None
    mae: float | None = None
    R2: float | None = None
    adjusted_R2: float | None = None
    chi_square: float | None = None
    reduced_chi_square: float | None = None
    AIC: float | None = None
    AICc: float | None = None
    BIC: float | None = None
    weighted: bool = False
    weighted_point_count: int = 0
    weighted_dof: int = 0
    sigma_aligned: bool | None = None
    invalid_sigma_point_count: int | None = None
    non_finite_weighted_residual_point_count: int | None = None
    weighting_reason: str | None = None
    sigma_is_absolute: bool | None = None
    information_criterion_basis: str | None = None
    information_criterion_point_count: int | None = None
    information_criterion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return only native Python values suitable for JSON/CSV exporters."""

        return {
            "n": _native_int(self.n),
            "parameter_count": _native_int(self.parameter_count),
            "dof": _native_int(self.dof),
            "rss": _finite_float(self.rss),
            "wrss": _finite_float(self.wrss),
            "rmse": _finite_float(self.rmse),
            "mae": _finite_float(self.mae),
            "R2": _finite_float(self.R2),
            "adjusted_R2": _finite_float(self.adjusted_R2),
            "chi_square": _finite_float(self.chi_square),
            "reduced_chi_square": _finite_float(self.reduced_chi_square),
            "AIC": _finite_float(self.AIC),
            "AICc": _finite_float(self.AICc),
            "BIC": _finite_float(self.BIC),
            "weighted": _native_bool(self.weighted),
            "weighted_point_count": _native_int(self.weighted_point_count),
            "weighted_dof": _native_int(self.weighted_dof),
            "sigma_aligned": _native_bool(self.sigma_aligned),
            "invalid_sigma_point_count": _native_int(self.invalid_sigma_point_count),
            "non_finite_weighted_residual_point_count": _native_int(self.non_finite_weighted_residual_point_count),
            "weighting_reason": _native_string(self.weighting_reason),
            "sigma_is_absolute": _native_bool(self.sigma_is_absolute),
            "information_criterion_basis": _native_string(self.information_criterion_basis),
            "information_criterion_point_count": _native_int(self.information_criterion_point_count),
            "information_criterion_reason": _native_string(self.information_criterion_reason),
        }


def _finite_float(value: Any) -> float | None:
    """Convert one scalar to a finite native float, otherwise return ``None``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _native_int(value: Any) -> int | None:
    """Convert a finite integer-like scalar to a native ``int``."""

    number = _finite_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _native_bool(value: Any) -> bool | None:
    """Normalize a flag without turning arbitrary objects into truthy values."""

    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    numeric_value = _finite_float(value)
    if numeric_value in {0.0, 1.0}:
        return bool(numeric_value)
    return None


def _native_string(value: Any) -> str | None:
    if isinstance(value, (str, np.str_)):
        return str(value)
    return None


def _as_1d_float(values: Any, name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a one-dimensional numeric sequence") from exc
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array.copy()


def _require_same_length(*named_arrays: tuple[str, np.ndarray]) -> None:
    lengths = {array.size for _, array in named_arrays}
    if len(lengths) > 1:
        names = ", ".join(name for name, _ in named_arrays)
        raise ValueError(f"{names} must have the same length")


def _parameter_count(value: Any) -> int:
    try:
        numeric_value = float(value)
        count = int(numeric_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("parameter_count must be a non-negative integer") from exc
    if not np.isfinite(numeric_value) or count != numeric_value or count < 0:
        raise ValueError("parameter_count must be a non-negative integer")
    return count


def _sum_of_squares(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        total = np.sum(np.square(values))
    return _finite_float(total)


def _mean_absolute(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        mean = np.mean(np.abs(values))
    return _finite_float(mean)


def _unweighted_information_criteria(
    rss: float | None,
    n: int,
    parameter_count: int,
) -> tuple[float | None, float | None, float | None]:
    """Return residual-variance AIC, AICc and BIC for an unweighted fit."""

    if rss is None or rss <= 0.0 or n <= 0:
        return None, None, None
    variance = rss / n
    if not np.isfinite(variance) or variance <= 0.0:
        return None, None, None
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        aic = _finite_float(n * np.log(variance) + 2.0 * parameter_count)
        bic = _finite_float(n * np.log(variance) + parameter_count * np.log(n))
    aicc: float | None = None
    if aic is not None and n > parameter_count + 1:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            aicc = _finite_float(aic + (2.0 * parameter_count * (parameter_count + 1)) / (n - parameter_count - 1))
    return aic, aicc, bic


def _absolute_sigma_information_criteria(
    chi_square: float | None,
    sigma: np.ndarray,
    parameter_count: int,
) -> tuple[float | None, float | None, float | None]:
    """Return Gaussian-likelihood information criteria for absolute sigma.

    The likelihood term is ``chi_square + sum(log(2*pi*sigma**2))`` over the
    actual finite weighted points.  The caller must supply only positive finite
    sigma values that contributed to ``chi_square``.
    """

    n = int(sigma.size)
    if chi_square is None or n <= 0:
        return None, None, None
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        sigma_term = np.sum(np.log(2.0 * np.pi * np.square(sigma)))
        likelihood_term = _finite_float(chi_square + sigma_term)
    if likelihood_term is None:
        return None, None, None
    aic = _finite_float(likelihood_term + 2.0 * parameter_count)
    bic = _finite_float(likelihood_term + parameter_count * np.log(n))
    aicc: float | None = None
    if aic is not None and n > parameter_count + 1:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            aicc = _finite_float(aic + (2.0 * parameter_count * (parameter_count + 1)) / (n - parameter_count - 1))
    return aic, aicc, bic


def fit_diagnostics(
    observed: Any,
    fitted: Any,
    *,
    parameter_count: int,
    sigma: Any | None = None,
    sigma_is_absolute: bool = True,
) -> dict[str, Any]:
    """Calculate complete common diagnostics without hiding invalid domains.

    Statistics use finite pairs from ``observed`` and ``fitted``.  A malformed
    or misaligned ``sigma`` never prevents unweighted statistics from being
    reported; it simply disables weighted quantities and leaves an explicit
    audit field describing why.  With effective absolute sigma, AIC/AICc/BIC
    use the absolute Gaussian likelihood.  Relative sigma never produces
    information criteria that could be used for model selection.
    """

    y = _as_1d_float(observed, "observed")
    yhat = _as_1d_float(fitted, "fitted")
    _require_same_length(("observed", y), ("fitted", yhat))
    k = _parameter_count(parameter_count)

    if not isinstance(sigma_is_absolute, (bool, np.bool_)):
        raise ValueError("sigma_is_absolute must be a boolean")

    finite_mask = np.isfinite(y) & np.isfinite(yhat)
    with np.errstate(over="ignore", invalid="ignore"):
        residual = y[finite_mask] - yhat[finite_mask]
    n = int(residual.size)
    dof = max(0, n - k)

    rss = _sum_of_squares(residual)
    mae = _mean_absolute(residual)
    rmse = _finite_float(np.sqrt(rss / n)) if rss is not None and n else None

    r2: float | None = None
    if n and rss is not None:
        selected_observed = y[finite_mask]
        with np.errstate(over="ignore", invalid="ignore"):
            tss = _sum_of_squares(selected_observed - np.mean(selected_observed))
        if tss is not None and tss > 0.0:
            r2 = _finite_float(1.0 - rss / tss)
    adjusted_r2: float | None = None
    if r2 is not None and n > 1 and dof > 0:
        adjusted_r2 = _finite_float(1.0 - (1.0 - r2) * (n - 1) / dof)

    weighted = False
    weighted_point_count = 0
    weighted_dof = 0
    sigma_aligned: bool | None = None
    invalid_sigma_point_count: int | None = None
    non_finite_weighted_residual_point_count: int | None = None
    weighting_reason: str | None = "no_sigma_provided"
    wrss: float | None = None
    chi_square: float | None = None
    reduced_chi_square: float | None = None

    absolute_sigma_flag = bool(sigma_is_absolute) if sigma is not None else None
    weighted_sigma = np.array([], dtype=float)
    if sigma is not None:
        try:
            sigma_array = _as_1d_float(sigma, "sigma")
        except ValueError:
            sigma_array = None
            sigma_aligned = False
            weighting_reason = "sigma_not_numeric"
        if sigma_array is not None:
            if sigma_array.size != y.size:
                sigma_aligned = False
                weighting_reason = "sigma_length_mismatch"
            else:
                sigma_aligned = True
                selected_sigma = sigma_array[finite_mask]
                valid_sigma = np.isfinite(selected_sigma) & (selected_sigma > 0.0)
                standardized = np.full(selected_sigma.shape, np.nan, dtype=float)
                if np.any(valid_sigma):
                    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                        standardized[valid_sigma] = residual[valid_sigma] / selected_sigma[valid_sigma]
                usable_weighted = valid_sigma & np.isfinite(standardized)
                weighted_point_count = int(np.count_nonzero(usable_weighted))
                invalid_sigma_point_count = int(np.count_nonzero(~valid_sigma))
                non_finite_weighted_residual_point_count = int(
                    np.count_nonzero(valid_sigma & ~np.isfinite(standardized))
                )
                weighted_dof = max(0, weighted_point_count - k)
                if weighted_point_count:
                    wrss = _sum_of_squares(standardized[usable_weighted])
                    chi_square = wrss
                    if wrss is not None:
                        weighted = True
                        weighted_sigma = selected_sigma[usable_weighted].copy()
                        if weighted_dof > 0:
                            reduced_chi_square = _finite_float(wrss / weighted_dof)
                        if invalid_sigma_point_count and non_finite_weighted_residual_point_count:
                            weighting_reason = "partial_valid_sigma_and_non_finite_weighted_residual"
                        elif invalid_sigma_point_count:
                            weighting_reason = "partial_valid_sigma"
                        elif non_finite_weighted_residual_point_count:
                            weighting_reason = "partial_non_finite_weighted_residual"
                        else:
                            weighting_reason = "all_sigma_valid"
                    else:
                        weighting_reason = "non_finite_weighted_residual"
                else:
                    weighting_reason = (
                        "non_finite_weighted_residual"
                        if non_finite_weighted_residual_point_count
                        else "no_valid_sigma"
                    )

    information_criterion_basis: str
    information_criterion_point_count: int
    information_criterion_reason: str | None = None
    if weighted and absolute_sigma_flag:
        information_criterion_basis = "absolute_sigma_gaussian"
        information_criterion_point_count = weighted_point_count
        aic, aicc, bic = _absolute_sigma_information_criteria(chi_square, weighted_sigma, k)
        if aic is None:
            information_criterion_reason = "non_finite_absolute_sigma_likelihood"
    elif weighted:
        information_criterion_basis = "unavailable_relative_sigma"
        information_criterion_point_count = weighted_point_count
        information_criterion_reason = "relative_sigma"
        aic = aicc = bic = None
    else:
        information_criterion_basis = "unweighted_residual_variance"
        information_criterion_point_count = n
        aic, aicc, bic = _unweighted_information_criteria(rss, n, k)
        if aic is None:
            information_criterion_reason = "non_positive_or_non_finite_rss"
        elif sigma is not None:
            information_criterion_reason = "no_effective_weighting"
    return FitDiagnostics(
        n=n,
        parameter_count=k,
        dof=dof,
        rss=rss,
        wrss=wrss,
        rmse=rmse,
        mae=mae,
        R2=r2,
        adjusted_R2=adjusted_r2,
        chi_square=chi_square,
        reduced_chi_square=reduced_chi_square,
        AIC=aic,
        AICc=aicc,
        BIC=bic,
        weighted=weighted,
        weighted_point_count=weighted_point_count,
        weighted_dof=weighted_dof,
        sigma_aligned=sigma_aligned,
        invalid_sigma_point_count=invalid_sigma_point_count,
        non_finite_weighted_residual_point_count=non_finite_weighted_residual_point_count,
        weighting_reason=weighting_reason,
        sigma_is_absolute=absolute_sigma_flag,
        information_criterion_basis=information_criterion_basis,
        information_criterion_point_count=information_criterion_point_count,
        information_criterion_reason=information_criterion_reason,
    ).to_dict()


def _optional_values(values: Any, names: list[str], label: str) -> list[Any]:
    if values is None:
        return [None] * len(names)
    if isinstance(values, Mapping):
        return [values.get(name) for name in names]
    if isinstance(values, (str, bytes)):
        if label == "units":
            return [values] * len(names)
        raise ValueError(f"{label} must have one value per parameter")
    try:
        sequence = list(values)
    except TypeError as exc:
        if len(names) == 1:
            return [values]
        raise ValueError(f"{label} must have one value per parameter") from exc
    if len(sequence) != len(names):
        raise ValueError(f"{label} must have one value per parameter")
    return sequence


def _normalise_parameter_names(names: Sequence[str]) -> list[str]:
    cleaned = list(names)
    if any(not isinstance(name, str) or not name.strip() for name in cleaned):
        raise ValueError("parameter names must be non-empty strings")
    return cleaned


def _normalise_bounds(bounds: Any, names: list[str]) -> tuple[list[Any], list[Any]]:
    """Normalize documented parameter-bound shapes without silent ambiguity.

    A list/tuple of one ``(lower, upper)`` pair per parameter is interpreted as
    per-parameter bounds, including the two-parameter tuple-of-pairs case.
    A SciPy-style vector form remains ``(lower_array, upper_array)`` with
    NumPy arrays.  A two-dimensional NumPy array has shape ``(n_parameters, 2)``
    and is likewise per-parameter bounds.  This explicit rule prevents a tuple
    of pairs from being silently transposed into unrelated lower/upper vectors.
    """

    if bounds is None:
        return [None] * len(names), [None] * len(names)
    if isinstance(bounds, Mapping):
        lower: list[Any] = []
        upper: list[Any] = []
        for name in names:
            pair = bounds.get(name)
            if pair is None:
                lower.append(None)
                upper.append(None)
                continue
            try:
                low, high = pair
            except (TypeError, ValueError) as exc:
                raise ValueError("each named bound must be a (lower, upper) pair") from exc
            lower.append(low)
            upper.append(high)
        return lower, upper
    if isinstance(bounds, np.ndarray):
        if bounds.ndim != 2 or bounds.shape != (len(names), 2):
            raise ValueError("array bounds must have shape (parameter_count, 2)")
        return bounds[:, 0].tolist(), bounds[:, 1].tolist()
    if isinstance(bounds, list) and len(bounds) == len(names) and all(
        isinstance(pair, Sequence) and not isinstance(pair, (str, bytes)) and len(pair) == 2 for pair in bounds
    ):
        return [pair[0] for pair in bounds], [pair[1] for pair in bounds]
    if isinstance(bounds, tuple) and len(bounds) == len(names) and all(
        isinstance(pair, (list, tuple)) and len(pair) == 2 for pair in bounds
    ):
        return [pair[0] for pair in bounds], [pair[1] for pair in bounds]
    try:
        lower_values, upper_values = bounds
    except (TypeError, ValueError) as exc:
        raise ValueError("bounds must be (lower, upper), parameter pairs, or a name mapping") from exc
    return _optional_values(lower_values, names, "lower bounds"), _optional_values(upper_values, names, "upper bounds")


def _bound_hit(value: float | None, lower: float | None, upper: float | None, tolerance: float) -> bool | None:
    if value is None:
        return None
    finite_bounds = [bound for bound in (lower, upper) if bound is not None]
    if not finite_bounds:
        return None
    return any(abs(value - bound) <= max(tolerance, abs(bound) * tolerance) for bound in finite_bounds)


def parameter_records(
    names: Sequence[str],
    values: Sequence[Any] | np.ndarray,
    *,
    units: Sequence[str] | Mapping[str, str] | str | None = None,
    initial: Sequence[Any] | Mapping[str, Any] | None = None,
    bounds: Any = None,
    stderr: Sequence[Any] | Mapping[str, Any] | None = None,
    bound_tolerance: float = 1e-8,
) -> list[dict[str, Any]]:
    """Return fixed-schema parameter rows with uncertainty and bound provenance."""

    parameter_names = _normalise_parameter_names(names)
    raw_values = _optional_values(values, parameter_names, "values")
    raw_units = _optional_values(units, parameter_names, "units")
    raw_initial = _optional_values(initial, parameter_names, "initial")
    raw_stderr = _optional_values(stderr, parameter_names, "stderr")
    raw_lower, raw_upper = _normalise_bounds(bounds, parameter_names)
    tolerance = _finite_float(bound_tolerance)
    if tolerance is None or tolerance < 0.0:
        raise ValueError("bound_tolerance must be a finite non-negative number")

    rows: list[dict[str, Any]] = []
    for index, name in enumerate(parameter_names):
        value = _finite_float(raw_values[index])
        initial_value = _finite_float(raw_initial[index])
        lower = _finite_float(raw_lower[index])
        upper = _finite_float(raw_upper[index])
        standard_error = _finite_float(raw_stderr[index])
        if standard_error is not None and standard_error < 0.0:
            standard_error = None
        ci95_low = None if value is None or standard_error is None else _finite_float(value - 1.96 * standard_error)
        ci95_high = None if value is None or standard_error is None else _finite_float(value + 1.96 * standard_error)
        rows.append(
            {
                "name": name,
                "value": value,
                "unit": str(raw_units[index]) if raw_units[index] is not None else "",
                "initial": initial_value,
                "lower_bound": lower,
                "upper_bound": upper,
                "stderr": standard_error,
                "ci95_low": ci95_low,
                "ci95_high": ci95_high,
                "bound_hit": _bound_hit(value, lower, upper, tolerance),
            }
        )
    return rows


def covariance_to_correlation(covariance: Any) -> list[list[float | None]]:
    """Convert a symmetric covariance matrix into JSON-safe correlations.

    A zero, negative, or non-finite diagonal is not an identifiable variance and
    produces ``None`` for every correlation that depends on it.  A non-square
    or non-symmetric matrix is rejected explicitly rather than silently fixed.
    For an all-finite symmetric matrix, a materially negative eigenvalue below
    ``-COVARIANCE_PSD_RELATIVE_TOLERANCE * max(1, max(abs(covariance)))`` also
    raises ``ValueError``.  Partially non-finite matrices cannot be asserted
    PSD and are returned only with nulls for unavailable correlations.
    """

    try:
        cov = np.asarray(covariance, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("covariance must be a square numeric matrix") from exc
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError("covariance must be a square numeric matrix")
    if not np.allclose(cov, cov.T, rtol=1e-10, atol=1e-12, equal_nan=True):
        raise ValueError("covariance must be symmetric")
    if cov.size and np.all(np.isfinite(cov)):
        scale = max(1.0, float(np.max(np.abs(cov))))
        try:
            eigenvalues = np.linalg.eigvalsh(cov)
        except np.linalg.LinAlgError as exc:
            raise ValueError("covariance PSD check failed") from exc
        if float(np.min(eigenvalues)) < -COVARIANCE_PSD_RELATIVE_TOLERANCE * scale:
            raise ValueError("covariance must be positive semidefinite within numerical tolerance")

    size = int(cov.shape[0])
    result: list[list[float | None]] = [[None for _ in range(size)] for _ in range(size)]
    diagonal = np.diag(cov)
    valid_variance = np.isfinite(diagonal) & (diagonal > 0.0)
    for index in range(size):
        if valid_variance[index]:
            result[index][index] = 1.0

    for row in range(size):
        for column in range(row + 1, size):
            if not (valid_variance[row] and valid_variance[column]):
                continue
            covariance_value = _finite_float(cov[row, column])
            if covariance_value is None:
                continue
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                coefficient = _finite_float(covariance_value / np.sqrt(diagonal[row] * diagonal[column]))
            if coefficient is None or abs(coefficient) > 1.0 + 1e-10:
                continue
            coefficient = float(np.clip(coefficient, -1.0, 1.0))
            result[row][column] = coefficient
            result[column][row] = coefficient
    return result


def build_residual_rows(q: Any, observed: Any, fitted: Any, *, sigma: Any | None = None) -> list[dict[str, Any]]:
    """Build one residual record per input row without dropping invalid rows."""

    q_values = _as_1d_float(q, "q")
    observed_values = _as_1d_float(observed, "observed")
    fitted_values = _as_1d_float(fitted, "fitted")
    _require_same_length(("q", q_values), ("observed", observed_values), ("fitted", fitted_values))

    sigma_values: np.ndarray | None = None
    if sigma is not None:
        sigma_values = _as_1d_float(sigma, "sigma")
        _require_same_length(("q", q_values), ("sigma", sigma_values))

    rows: list[dict[str, Any]] = []
    for index in range(q_values.size):
        q_value = _finite_float(q_values[index])
        observed_value = _finite_float(observed_values[index])
        fitted_value = _finite_float(fitted_values[index])
        reasons: list[str] = []
        if q_value is None:
            reasons.append("non_finite_q")
        if observed_value is None:
            reasons.append("non_finite_observed")
        if fitted_value is None:
            reasons.append("non_finite_fitted")

        residual: float | None = None
        if not reasons:
            with np.errstate(over="ignore", invalid="ignore"):
                residual = _finite_float(observed_value - fitted_value)
            if residual is None:
                reasons.append("non_finite_residual")

        sigma_value = None if sigma_values is None else _finite_float(sigma_values[index])
        standardized_residual: float | None = None
        weight: float | None = None
        weighting_valid = False
        weighting_exclusion_reason: str | None = None
        if sigma_values is None:
            weighting_exclusion_reason = "sigma_not_provided"
        elif sigma_value is None:
            weighting_exclusion_reason = "non_finite_sigma"
        elif sigma_value <= 0.0:
            weighting_exclusion_reason = "non_positive_sigma"
        elif residual is None:
            weighting_exclusion_reason = "residual_not_available"
        else:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                standardized_residual = _finite_float(residual / sigma_value)
                weight = _finite_float(1.0 / (sigma_value**2))
            if standardized_residual is not None and weight is not None:
                weighting_valid = True
            else:
                weighting_exclusion_reason = "non_finite_weight_or_standardized_residual"

        rows.append(
            {
                "q": q_value,
                "observed": observed_value,
                "fitted": fitted_value,
                "residual": residual,
                "standardized_residual": standardized_residual,
                "sigma": sigma_value,
                "weight": weight,
                "included": not reasons,
                "exclusion_reason": None if not reasons else "; ".join(reasons),
                "weighting_valid": weighting_valid,
                "weighting_exclusion_reason": weighting_exclusion_reason,
            }
        )
    return rows
