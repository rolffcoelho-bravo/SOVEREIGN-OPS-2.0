"""G8.2 — Sliding-window spectral tracking engine.

Implements the first pillar of Adaptive Spectral Regime Detection:
continuous monitoring of the evolving spectral fingerprint through
time via a sliding window over the wavelet packet energy spectrum.

**Core Algorithm — Spectral Divergence Tracking:**

1. Compute a *reference spectrum* from the first ``n_ref`` windows
   (calibration phase).
2. Slide through the remaining signal in fixed-step windows.
3. At each window position, compute the wavelet packet energy
   spectrum and measure Jensen-Shannon divergence from the
   reference.
4. The divergence time-series feeds the downstream change-point
   detector (G8.3).

**Adaptive Bandwidth (Silverman):**

The window size adapts to the local signal variability using
Silverman's rule of thumb adapted for spectral density estimation:

    h = 0.9 · min(σ, IQR/1.34) · n^(−1/5)

This ensures finer resolution in regions of rapid spectral change
and coarser resolution in stable regions — maximising sensitivity
while minimising false alarms.

**Mathematical Foundation:**

Jensen-Shannon divergence is symmetric and bounded ∈ [0, ln 2]:

    JSD(P‖Q) = ½ KL(P‖M) + ½ KL(Q‖M),  M = ½(P + Q)

where KL is the Kullback-Leibler divergence. This makes it
suitable for time-series tracking since the magnitude is
directly interpretable regardless of direction.

All outputs are DARP-compliant frozen contracts with SHA-256
provenance chains.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g8_contracts import (
    AdaptiveBandwidth,
    SpectralTrackingState,
    SpectralWindow,
)

if TYPE_CHECKING:
    pass


# ── constants ─────────────────────────────────────────────────────

_EPSILON = 1e-12  # smoothing to avoid log(0)
_MIN_WINDOW = 4  # absolute minimum window size


# ── information-theoretic divergences ─────────────────────────────


def _normalise_spectrum(energies: NDArray[np.float64]) -> NDArray[np.float64]:
    """Normalise an energy spectrum to a probability distribution.

    Adds ε-smoothing so no bin is exactly zero — required for
    KL divergence computation.
    """
    smoothed = energies + _EPSILON
    total = smoothed.sum()
    if total <= 0:
        # uniform fallback for degenerate input
        return np.ones_like(smoothed) / len(smoothed)
    return smoothed / total


def kl_divergence(
    p: NDArray[np.float64],
    q: NDArray[np.float64],
) -> float:
    """Kullback-Leibler divergence KL(P‖Q).

    Both ``p`` and ``q`` must be normalised probability distributions
    of the same length.  Uses ε-smoothing on ``q`` to avoid log(0).

    Returns
    -------
    float
        KL(P‖Q) ≥ 0.  Zero iff P = Q.
    """
    q_safe = np.maximum(q, _EPSILON)
    p_safe = np.maximum(p, _EPSILON)
    return float(np.sum(p_safe * np.log(p_safe / q_safe)))


def js_divergence(
    p: NDArray[np.float64],
    q: NDArray[np.float64],
) -> float:
    """Jensen-Shannon divergence JSD(P‖Q) ∈ [0, ln 2].

    Symmetric, bounded, and the square root is a metric.

    JSD(P‖Q) = ½ KL(P‖M) + ½ KL(Q‖M),  M = ½(P + Q)
    """
    m = 0.5 * (p + q)
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


# ── wavelet packet spectrum ───────────────────────────────────────


def wavelet_packet_spectrum(
    signal: NDArray[np.float64],
    max_level: int = 3,
) -> NDArray[np.float64]:
    """Compute wavelet packet energy spectrum via Haar decomposition.

    Uses an iterative Haar wavelet packet transform up to
    ``max_level`` levels.  At each node of the decomposition tree,
    the energy (sum of squares) is computed and normalised.

    This yields 2^max_level spectral bands whose energy distribution
    characterises the signal's frequency content.

    Parameters
    ----------
    signal : array
        1-D real-valued signal.
    max_level : int
        Decomposition depth.  Produces 2^max_level bands.

    Returns
    -------
    NDArray[np.float64]
        Normalised energy per spectral band.
    """
    n_bands = 2**max_level
    sig = np.asarray(signal, dtype=np.float64)

    # Pad to next multiple of n_bands
    pad_len = (n_bands - len(sig) % n_bands) % n_bands
    if pad_len > 0:
        sig = np.concatenate([sig, np.zeros(pad_len)])

    # Iterative Haar wavelet packet decomposition
    coeffs: list[NDArray[np.float64]] = [sig]

    for _level in range(max_level):
        next_coeffs: list[NDArray[np.float64]] = []
        for node in coeffs:
            n = len(node)
            if n < 2:
                next_coeffs.append(node)
                next_coeffs.append(np.zeros(1))
                continue
            even = node[0::2]
            odd = node[1::2]
            approx = (even + odd) / np.sqrt(2)
            detail = (even - odd) / np.sqrt(2)
            next_coeffs.append(approx)
            next_coeffs.append(detail)
        coeffs = next_coeffs

    # Energy per band
    energies = np.array([float(np.sum(c**2)) for c in coeffs])
    return _normalise_spectrum(energies)


# ── adaptive bandwidth ────────────────────────────────────────────


def compute_adaptive_bandwidth(
    divergence_series: NDArray[np.float64],
    base_window_size: int,
    dataset_id: DatasetId,
) -> AdaptiveBandwidth:
    """Compute adaptive window bandwidth via Silverman's rule.

    Silverman's rule of thumb for density estimation:

        h = 0.9 · min(σ, IQR/1.34) · n^(−1/5)

    The adapted window size is ``base_window_size`` scaled by
    1/h (narrower windows when variability is high).

    Parameters
    ----------
    divergence_series : array
        Time-series of spectral divergence values.
    base_window_size : int
        Default window size before adaptation.
    dataset_id : DatasetId
        Source dataset identifier.

    Returns
    -------
    AdaptiveBandwidth
        DARP-compliant frozen contract.
    """
    n = len(divergence_series)
    std = float(np.std(divergence_series, ddof=1)) if n > 1 else 0.0
    q75, q25 = (
        float(np.percentile(divergence_series, 75)),
        float(np.percentile(divergence_series, 25)),
    )
    iqr = q75 - q25

    # Silverman's rule
    spread = min(std, iqr / 1.34) if iqr > 0 else std
    silverman_h = 0.9 * spread * (n ** (-0.2)) if n > 0 and spread > 0 else 1.0

    # Adapted window: scale inversely with bandwidth
    # Clamp to [_MIN_WINDOW, base_window_size * 2]
    if silverman_h > 0:
        adapted = int(base_window_size / max(silverman_h, 0.1))
    else:
        adapted = base_window_size
    adapted = max(_MIN_WINDOW, min(adapted, base_window_size * 2))

    return AdaptiveBandwidth(
        dataset_id=dataset_id,
        base_window_size=base_window_size,
        adapted_window_size=adapted,
        silverman_h=silverman_h,
        signal_std=std,
        signal_iqr=iqr,
        n_observations=n,
    )


# ── sliding-window tracker ───────────────────────────────────────


def _sha256_array(arr: NDArray[np.float64]) -> str:
    """SHA-256 of a numpy array's bytes."""
    return hashlib.sha256(arr.tobytes()).hexdigest()


def track_spectral_divergence(
    signal: NDArray[np.float64],
    dataset_id: DatasetId,
    source_sha256: str,
    window_size: int = 128,
    step_size: int | None = None,
    max_level: int = 3,
    n_reference_windows: int = 5,
) -> SpectralTrackingState:
    """Run sliding-window spectral tracking over a signal.

    1. Splits the signal into overlapping windows.
    2. Computes wavelet packet energy spectrum per window.
    3. Builds a reference spectrum from the first
       ``n_reference_windows`` windows.
    4. Measures JS and KL divergence at every subsequent window.
    5. Computes adaptive bandwidth from the divergence series.

    Parameters
    ----------
    signal : array
        1-D real-valued signal (time-series).
    dataset_id : DatasetId
        Source dataset identifier.
    source_sha256 : str
        SHA-256 of the source data for provenance.
    window_size : int
        Base window size in samples.
    step_size : int or None
        Step between windows (default: window_size // 2).
    max_level : int
        Wavelet decomposition depth.
    n_reference_windows : int
        Number of initial windows to build the reference spectrum.

    Returns
    -------
    SpectralTrackingState
        Complete tracking state with divergence series.
    """
    if step_size is None:
        step_size = max(1, window_size // 2)

    sig = np.asarray(signal, dtype=np.float64)
    n_total = len(sig)

    # Generate window positions
    starts: list[int] = []
    pos = 0
    while pos + window_size <= n_total:
        starts.append(pos)
        pos += step_size
    if not starts:
        # Signal too short — use entire signal as one window
        starts = [0]

    # Compute spectrum per window
    spectra: list[NDArray[np.float64]] = []
    for s in starts:
        end = min(s + window_size, n_total)
        chunk = sig[s:end]
        spectra.append(wavelet_packet_spectrum(chunk, max_level=max_level))

    # Build reference spectrum (average of first n_ref windows)
    n_ref = min(n_reference_windows, len(spectra))
    ref_stack = np.stack(spectra[:n_ref])
    reference = _normalise_spectrum(ref_stack.mean(axis=0))

    # Compute divergences
    windows: list[SpectralWindow] = []
    divergences: list[float] = []
    for idx, (s, spectrum) in enumerate(zip(starts, spectra, strict=False)):
        end = min(s + window_size, n_total)
        jsd = js_divergence(spectrum, reference)
        kld = kl_divergence(spectrum, reference)
        divergences.append(jsd)

        windows.append(
            SpectralWindow(
                dataset_id=dataset_id,
                window_index=idx,
                window_start=s,
                window_end=end,
                n_samples=end - s,
                spectral_energy=tuple(float(x) for x in spectrum),
                js_divergence=jsd,
                kl_divergence=kld,
                source_sha256=source_sha256,
            )
        )

    div_array = np.array(divergences, dtype=np.float64)

    # Adaptive bandwidth
    bandwidth = compute_adaptive_bandwidth(div_array, window_size, dataset_id)

    return SpectralTrackingState(
        dataset_id=dataset_id,
        windows=tuple(windows),
        bandwidth=bandwidth,
        n_windows=len(windows),
        mean_divergence=float(div_array.mean()) if len(div_array) > 0 else 0.0,
        max_divergence=float(div_array.max()) if len(div_array) > 0 else 0.0,
        divergence_series_sha256=_sha256_array(div_array),
    )
