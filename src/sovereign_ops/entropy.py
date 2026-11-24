"""G7 · Information-Theoretic Anomaly Profiling via Rényi Entropy.

Implements the **Rényi α-spectrum** — a parameterised family of
entropies that generalises Shannon entropy — for characterising
distributional complexity of telemetry signals at multiple
sensitivity levels.

Mathematical foundation
-----------------------
Rényi entropy of order α (α ≥ 0, α ≠ 1):

    H_α(X) = 1/(1−α) · log₂(Σᵢ pᵢ^α)

Special cases:
  α → 0 : Hartley entropy = log₂(|support|)
  α → 1 : Shannon entropy = −Σ pᵢ log₂ pᵢ  (by L'Hôpital)
  α = 2 : Collision entropy = −log₂(Σ pᵢ²)
  α → ∞ : Min-entropy = −log₂(max pᵢ)

The α-spectrum {H_α : α ∈ A} captures distributional features
across a continuum of sensitivity parameters:
- Low α (< 1) weights rare events (tail sensitivity)
- α = 1 balances all events by their probability
- High α (> 1) concentrates on the mode (peak sensitivity)

Rényi divergence of order α:

    D_α(P‖Q) = 1/(α−1) · log₂(Σᵢ pᵢ^α · qᵢ^{1−α})

The divergence profile across α identifies *which* distributional
features drive the anomaly — a richer characterisation than
single-α (KL) divergence alone.

**Novel contribution**: the α-spectrum divergence profile as an
anomaly characterisation tool is, to our knowledge, not previously
used in industrial anomaly detection pipelines.

**No live telemetry** — operates on historical arrays only.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g7_contracts import (
    EntropyAlphaSpectrum,
    EntropyDivergenceProfile,
    RenyiEntropyPoint,
)

__all__ = [
    "histogram_density",
    "renyi_entropy",
    "build_alpha_spectrum",
    "entropy_divergence_profile",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPS: float = 1e-15
_DEFAULT_ALPHAS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0)

# α-label classification
_ALPHA_LABELS: dict[str, tuple[float, float]] = {
    "hartley": (0.0, 0.1),
    "sub_shannon": (0.1, 0.99),
    "shannon": (0.99, 1.01),
    "collision": (1.99, 2.01),
    "super_collision": (2.01, 5.01),
    "near_min": (5.01, 50.0),
    "min_entropy": (50.0, float("inf")),
}


def _classify_alpha(
    alpha: float,
) -> Literal[
    "hartley",
    "sub_shannon",
    "shannon",
    "collision",
    "super_collision",
    "near_min",
    "min_entropy",
]:
    """Classify an α value into its entropy regime."""
    if alpha < 0.1:
        return "hartley"
    if alpha < 0.99:
        return "sub_shannon"
    if alpha < 1.01:
        return "shannon"
    if 1.99 <= alpha < 2.01:
        return "collision"
    if alpha < 5.01:
        return "super_collision"
    if alpha < 50.0:
        return "near_min"
    return "min_entropy"


# ---------------------------------------------------------------------------
# Density estimation via histogram
# ---------------------------------------------------------------------------


def histogram_density(
    values: NDArray[np.float64],
    *,
    n_bins: int | None = None,
) -> tuple[NDArray[np.float64], int]:
    """Estimate a discrete probability distribution via histogram binning.

    Uses Freedman-Diaconis rule for automatic bin count when not
    specified, with a floor of 10 and a ceiling of 256 bins.

    Parameters
    ----------
    values:
        1-D array of observations (NaNs dropped).
    n_bins:
        Fixed number of bins.  ``None`` → automatic.

    Returns
    -------
    (probabilities, n_bins) where probabilities sums to 1.
    """
    clean = values[~np.isnan(values)]
    if len(clean) < 2:
        raise ValueError("Need at least 2 non-NaN values for density estimation")

    if n_bins is None:
        # Freedman-Diaconis rule
        q75, q25 = float(np.percentile(clean, 75)), float(np.percentile(clean, 25))
        iqr = q75 - q25
        if iqr < _EPS:
            n_bins = 10
        else:
            bin_width = 2.0 * iqr * len(clean) ** (-1.0 / 3.0)
            data_range = float(np.max(clean) - np.min(clean))
            n_bins = max(10, min(256, int(math.ceil(data_range / bin_width))))

    counts, _ = np.histogram(clean, bins=n_bins)
    total = counts.sum()
    if total == 0:
        return np.full(n_bins, 1.0 / n_bins), n_bins

    probs = counts.astype(np.float64) / total
    return probs, n_bins


# ---------------------------------------------------------------------------
# Rényi entropy computation
# ---------------------------------------------------------------------------


def renyi_entropy(
    probs: NDArray[np.float64],
    *,
    alpha: float,
) -> float:
    """Compute Rényi entropy H_α for a discrete probability distribution.

    Parameters
    ----------
    probs:
        Probability vector (must sum to ≈ 1, entries ≥ 0).
    alpha:
        Rényi parameter (α ≥ 0).  α = 1 → Shannon entropy.

    Returns
    -------
    H_α in bits (log base 2).
    """
    if alpha < 0.0:
        raise ValueError(f"α must be ≥ 0, got {alpha}")

    # Remove zero-probability bins
    p = probs[probs > _EPS]
    if len(p) == 0:
        return 0.0

    # Normalise (defensive)
    p = p / p.sum()

    # Special case: α → 0 (Hartley entropy)
    if alpha < _EPS:
        return float(math.log2(len(p)))

    # Special case: α → 1 (Shannon entropy via L'Hôpital)
    if abs(alpha - 1.0) < 1e-6:
        return float(-np.sum(p * np.log2(p)))

    # Special case: α → ∞ (min-entropy)
    if alpha > 100.0:
        return float(-math.log2(np.max(p)))

    # General case: H_α = 1/(1−α) · log₂(Σ pᵢ^α)
    # Use log-sum-exp for numerical stability
    log_p = np.log(p)
    log_sum = float(np.log(np.sum(np.exp(alpha * log_p))))
    return log_sum / ((1.0 - alpha) * math.log(2.0))


# ---------------------------------------------------------------------------
# α-Spectrum construction
# ---------------------------------------------------------------------------


def build_alpha_spectrum(
    values: NDArray[np.float64],
    *,
    dataset_id: DatasetId,
    alphas: tuple[float, ...] = _DEFAULT_ALPHAS,
    n_bins: int | None = None,
    source_sha256: str,
) -> EntropyAlphaSpectrum:
    """Build the Rényi α-spectrum for a signal.

    Parameters
    ----------
    values:
        1-D float64 signal array.
    dataset_id:
        Domain identifier.
    alphas:
        α values at which to compute entropy.
    n_bins:
        Histogram bins (None → automatic).
    source_sha256:
        SHA-256 of the source data for provenance.

    Returns
    -------
    EntropyAlphaSpectrum contract.
    """
    probs, actual_bins = histogram_density(values, n_bins=n_bins)

    points: list[RenyiEntropyPoint] = []
    shannon_h = 0.0
    min_h = 0.0

    for alpha in alphas:
        h = renyi_entropy(probs, alpha=alpha)
        label = _classify_alpha(alpha)
        points.append(
            RenyiEntropyPoint(
                alpha=round(alpha, 6),
                entropy=round(h, 10),
                alpha_label=label,
            )
        )
        if abs(alpha - 1.0) < 1e-6:
            shannon_h = h

    # Compute min-entropy (α → ∞) separately
    min_h = renyi_entropy(probs, alpha=200.0)

    # If Shannon not in the list, compute it
    if shannon_h == 0.0:
        shannon_h = renyi_entropy(probs, alpha=1.0)

    # Entropy ratio: min_entropy / shannon_entropy ∈ (0, 1]
    ratio = min_h / shannon_h if shannon_h > _EPS else 1.0
    ratio = max(0.0, min(1.0, ratio))

    return EntropyAlphaSpectrum(
        dataset_id=dataset_id,
        points=tuple(points),
        shannon_entropy=round(shannon_h, 10),
        min_entropy=round(min_h, 10),
        entropy_ratio=round(ratio, 10),
        n_bins=actual_bins,
        source_sha256=source_sha256,
    )


# ---------------------------------------------------------------------------
# Rényi divergence profile
# ---------------------------------------------------------------------------


def _renyi_divergence(
    p: NDArray[np.float64],
    q: NDArray[np.float64],
    *,
    alpha: float,
) -> float:
    """Rényi divergence D_α(P‖Q).

    D_α(P‖Q) = 1/(α−1) · log₂(Σᵢ pᵢ^α · qᵢ^{1−α})

    Special case α → 1: KL divergence D_KL(P‖Q) = Σ pᵢ log₂(pᵢ/qᵢ).
    """
    p_safe = np.maximum(p, _EPS)
    q_safe = np.maximum(q, _EPS)
    p_safe = p_safe / p_safe.sum()
    q_safe = q_safe / q_safe.sum()

    # α → 1: KL divergence
    if abs(alpha - 1.0) < 1e-6:
        return float(np.sum(p_safe * np.log2(p_safe / q_safe)))

    if abs(alpha) < _EPS:
        return 0.0

    # General Rényi divergence via log-sum-exp
    log_terms = alpha * np.log(p_safe) + (1.0 - alpha) * np.log(q_safe)
    log_sum = float(np.log(np.sum(np.exp(log_terms))))

    return max(0.0, log_sum / ((alpha - 1.0) * math.log(2.0)))


def entropy_divergence_profile(
    reference: NDArray[np.float64],
    test: NDArray[np.float64],
    *,
    dataset_id: DatasetId,
    alphas: tuple[float, ...] = _DEFAULT_ALPHAS,
    n_bins: int | None = None,
) -> EntropyDivergenceProfile:
    """Compute the Rényi α-divergence profile between reference and test.

    Parameters
    ----------
    reference:
        1-D float64 reference (training) signal.
    test:
        1-D float64 test signal.
    dataset_id:
        Domain identifier.
    alphas:
        α values at which to compute divergence.
    n_bins:
        Histogram bins (None → automatic, shared between both).

    Returns
    -------
    EntropyDivergenceProfile contract.
    """
    # Shared binning for consistent comparison
    all_vals = np.concatenate(
        [
            reference[~np.isnan(reference)],
            test[~np.isnan(test)],
        ]
    )
    if len(all_vals) < 4:
        raise ValueError("Need at least 4 total non-NaN values")

    p_ref, actual_bins = histogram_density(reference, n_bins=n_bins)
    p_test, _ = histogram_density(test, n_bins=actual_bins)

    # Ensure same dimensionality
    min_len = min(len(p_ref), len(p_test))
    p_ref = p_ref[:min_len]
    p_test = p_test[:min_len]

    divergences: list[tuple[float, float]] = []
    max_div = 0.0
    max_div_alpha = alphas[0] if alphas else 1.0

    for alpha in alphas:
        div = _renyi_divergence(p_test, p_ref, alpha=alpha)
        divergences.append((round(alpha, 6), round(div, 10)))
        if div > max_div:
            max_div = div
            max_div_alpha = alpha

    mean_div = sum(d for _, d in divergences) / max(len(divergences), 1)

    # Provenance
    ref_hash = hashlib.sha256(
        json.dumps(
            [round(float(x), 10) for x in p_ref],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    test_hash = hashlib.sha256(
        json.dumps(
            [round(float(x), 10) for x in p_test],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    return EntropyDivergenceProfile(
        dataset_id=dataset_id,
        alpha_divergences=tuple(divergences),
        mean_divergence=round(mean_div, 10),
        max_divergence=round(max_div, 10),
        max_divergence_alpha=round(max_div_alpha, 6),
        reference_sha256=ref_hash,
        test_sha256=test_hash,
    )
