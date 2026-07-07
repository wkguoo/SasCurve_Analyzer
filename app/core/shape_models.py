from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.special import j1


ModelFunction = Callable[[np.ndarray, float], np.ndarray]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    parameter_names: list[str]
    initial_values: list[float]
    lower_bounds: list[float]
    upper_bounds: list[float]
    units: dict[str, str]
    assumptions: list[str]
    description: str


def _sinc(x: np.ndarray) -> np.ndarray:
    out = np.ones_like(x, dtype=float)
    mask = np.abs(x) > 1e-10
    out[mask] = np.sin(x[mask]) / x[mask]
    return out


def _sphere_amplitude(q: np.ndarray, radius: float) -> np.ndarray:
    x = np.asarray(q, dtype=float) * max(float(radius), 1e-12)
    amp = np.ones_like(x)
    mask = np.abs(x) > 1e-8
    xm = x[mask]
    amp[mask] = 3.0 * (np.sin(xm) - xm * np.cos(xm)) / (xm**3)
    return amp


def sphere_model(q: np.ndarray, radius: float, scale: float, background: float) -> np.ndarray:
    return scale * _sphere_amplitude(q, radius) ** 2 + background


def core_shell_sphere_model(
    q: np.ndarray,
    core_radius: float,
    shell_thickness: float,
    core_contrast: float,
    shell_contrast: float,
    scale: float,
    background: float,
) -> np.ndarray:
    core_radius = max(float(core_radius), 1e-12)
    total_radius = core_radius + max(float(shell_thickness), 1e-12)
    core_volume = core_radius**3
    total_volume = total_radius**3
    amp_core = core_contrast * core_volume * _sphere_amplitude(q, core_radius)
    amp_shell = shell_contrast * (total_volume * _sphere_amplitude(q, total_radius) - core_volume * _sphere_amplitude(q, core_radius))
    norm = max(total_volume**2, 1e-24)
    return scale * ((amp_core + amp_shell) ** 2 / norm) + background


def ellipsoid_model(q: np.ndarray, equatorial_radius: float, polar_radius: float, scale: float, background: float) -> np.ndarray:
    mu = np.linspace(0.0, 1.0, 48)
    q_arr = np.asarray(q, dtype=float)
    radii = np.sqrt((equatorial_radius**2) * (1.0 - mu**2) + (polar_radius**2) * mu**2)
    values = np.vstack([_sphere_amplitude(q_arr, radius) ** 2 for radius in radii])
    return scale * np.mean(values, axis=0) + background


def cylinder_model(q: np.ndarray, radius: float, length: float, scale: float, background: float) -> np.ndarray:
    mu = np.linspace(0.0, 1.0, 64)
    q_arr = np.asarray(q, dtype=float)
    values = []
    for muv in mu:
        sin_alpha = np.sqrt(max(0.0, 1.0 - muv**2))
        qr = q_arr * radius * sin_alpha
        radial = np.ones_like(q_arr)
        mask = np.abs(qr) > 1e-8
        radial[mask] = 2.0 * j1(qr[mask]) / qr[mask]
        axial = _sinc(q_arr * length * muv / 2.0)
        values.append((radial * axial) ** 2)
    return scale * np.mean(np.vstack(values), axis=0) + background


def disk_model(q: np.ndarray, radius: float, thickness: float, scale: float, background: float) -> np.ndarray:
    return cylinder_model(q, radius, thickness, scale, background)


def gaussian_chain_model(q: np.ndarray, rg: float, scale: float, background: float) -> np.ndarray:
    x = (np.asarray(q, dtype=float) * max(float(rg), 1e-12)) ** 2
    value = np.ones_like(x)
    mask = x > 1e-8
    xm = x[mask]
    value[mask] = 2.0 * (np.exp(-xm) + xm - 1.0) / (xm**2)
    return scale * value + background


def dab_model(q: np.ndarray, correlation_length: float, scale: float, background: float) -> np.ndarray:
    x = np.asarray(q, dtype=float) * max(float(correlation_length), 1e-12)
    return scale / ((1.0 + x**2) ** 2) + background


def mass_fractal_model(q: np.ndarray, dimension: float, cutoff_length: float, scale: float, background: float) -> np.ndarray:
    q_arr = np.maximum(np.asarray(q, dtype=float), 1e-12)
    dimension = float(np.clip(dimension, 1.0, 3.0))
    cutoff_length = max(float(cutoff_length), 1e-12)
    finite_cutoff = 1.0 / cutoff_length
    return scale * ((q_arr**2 + finite_cutoff**2) ** (-dimension / 2.0)) + background


def surface_fractal_model(q: np.ndarray, surface_dimension: float, scale: float, background: float) -> np.ndarray:
    q_arr = np.maximum(np.asarray(q, dtype=float), 1e-12)
    surface_dimension = float(np.clip(surface_dimension, 2.0, 3.0))
    alpha = 6.0 - surface_dimension
    return scale * (q_arr ** (-alpha)) + background


def lamellar_peak_stack_model(q: np.ndarray, q0: float, width: float, amplitude: float, decay: float, background: float) -> np.ndarray:
    q_arr = np.asarray(q, dtype=float)
    q0 = max(float(q0), 1e-12)
    width = max(float(width), 1e-12)
    decay = max(float(decay), 1e-12)
    output = np.full_like(q_arr, float(background), dtype=float)
    q_max = float(np.nanmax(q_arr)) if q_arr.size else q0
    orders = max(1, int(np.floor(q_max / q0)))
    for order in range(1, orders + 1):
        output += amplitude * np.exp(-order / decay) * np.exp(-0.5 * ((q_arr - order * q0) / width) ** 2)
    return output


MODEL_FUNCTIONS: dict[str, Callable] = {
    "sphere": sphere_model,
    "core_shell_sphere": core_shell_sphere_model,
    "ellipsoid": ellipsoid_model,
    "cylinder": cylinder_model,
    "disk": disk_model,
    "gaussian_chain": gaussian_chain_model,
    "dab": dab_model,
    "mass_fractal": mass_fractal_model,
    "surface_fractal": surface_fractal_model,
    "lamellar_peak_stack": lamellar_peak_stack_model,
}


MODEL_SPECS: dict[str, ModelSpec] = {
    "sphere": ModelSpec("sphere", ["radius", "scale", "background"], [30.0, 1.0, 0.0], [1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf], {"radius": "1/q"}, ["dilute_particle_required", "sphere_shape_assumption"], "Monodisperse sphere form factor."),
    "core_shell_sphere": ModelSpec("core_shell_sphere", ["core_radius", "shell_thickness", "core_contrast", "shell_contrast", "scale", "background"], [25.0, 5.0, 1.0, 0.5, 1.0, 0.0], [1e-6, 1e-6, -np.inf, -np.inf, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf], {"core_radius": "1/q", "shell_thickness": "1/q"}, ["dilute_particle_required", "core_shell_assumption"], "Core-shell sphere with fitted relative contrasts."),
    "ellipsoid": ModelSpec("ellipsoid", ["equatorial_radius", "polar_radius", "scale", "background"], [25.0, 60.0, 1.0, 0.0], [1e-6, 1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf], {"equatorial_radius": "1/q", "polar_radius": "1/q"}, ["dilute_particle_required", "ellipsoid_shape_assumption"], "Randomly oriented ellipsoid approximation."),
    "cylinder": ModelSpec("cylinder", ["radius", "length", "scale", "background"], [10.0, 100.0, 1.0, 0.0], [1e-6, 1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf], {"radius": "1/q", "length": "1/q"}, ["dilute_particle_required", "cylinder_shape_assumption"], "Randomly oriented cylinder approximation."),
    "disk": ModelSpec("disk", ["radius", "thickness", "scale", "background"], [80.0, 5.0, 1.0, 0.0], [1e-6, 1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf], {"radius": "1/q", "thickness": "1/q"}, ["dilute_particle_required", "disk_shape_assumption"], "Thin disk as short-cylinder approximation."),
    "gaussian_chain": ModelSpec("gaussian_chain", ["Rg", "scale", "background"], [30.0, 1.0, 0.0], [1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf], {"Rg": "1/q"}, ["polymer_gaussian_chain_assumption"], "Debye Gaussian-chain form factor."),
    "dab": ModelSpec("dab", ["correlation_length", "scale", "background"], [30.0, 1.0, 0.0], [1e-6, 0.0, -np.inf], [np.inf, np.inf, np.inf], {"correlation_length": "1/q"}, ["two_phase_required", "dab_random_two_phase_assumption"], "Debye-Anderson-Brumberger two-phase model."),
    "mass_fractal": ModelSpec("mass_fractal", ["dimension", "cutoff_length", "scale", "background"], [2.2, 100.0, 1.0, 0.0], [1.0, 1e-6, 0.0, -np.inf], [3.0, np.inf, np.inf, np.inf], {"dimension": "", "cutoff_length": "1/q"}, ["mass_fractal_assumption"], "Mass-fractal empirical model with cutoff."),
    "surface_fractal": ModelSpec("surface_fractal", ["surface_dimension", "scale", "background"], [2.5, 1.0, 0.0], [2.0, 0.0, -np.inf], [3.0, np.inf, np.inf], {"surface_dimension": ""}, ["surface_fractal_assumption"], "Surface-fractal power-law model."),
    "lamellar_peak_stack": ModelSpec("lamellar_peak_stack", ["q0", "width", "amplitude", "decay", "background"], [0.1, 0.01, 1.0, 2.0, 0.0], [1e-8, 1e-8, 0.0, 0.1, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf], {"q0": "q", "width": "q"}, ["lamellar_or_periodic_structure_required"], "Gaussian peak stack at integer q0 orders."),
}


def model_names() -> list[str]:
    return list(MODEL_SPECS)


def evaluate_model(name: str, q: np.ndarray, parameters: list[float]) -> np.ndarray:
    if name not in MODEL_FUNCTIONS:
        raise ValueError(f"Unsupported shape model: {name}")
    return MODEL_FUNCTIONS[name](q, *parameters)

