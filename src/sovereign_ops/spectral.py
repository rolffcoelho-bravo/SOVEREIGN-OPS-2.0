"""G7 · Multi-Resolution Wavelet Packet Spectral Decomposition.

Implements the **Haar wavelet packet transform** from first principles
(no external wavelet library) to decompose a 1-D signal into a full
binary tree of time-frequency sub-bands, then measures spectral
divergence between reference and test distributions.

Mathematical foundation
-----------------------
The Discrete Wavelet Packet Transform (DWPT) generalises the DWT by
decomposing *both* approximation and detail coefficients at every
level, yielding 2^J sub-bands at depth J.  The Haar basis is chosen
for its computational simplicity and interpretability in industrial
telemetry, where step-change anomalies are common.

Haar filter bank:
  Low-pass  h[n] = [1/√2,  1/√2]
  High-pass g[n] = [1/√2, −1/√2]

Energy at node (j, k):
  E_{j,k} = (1/N) Σ |c_{j,k}[n]|²

The normalised energy spectrum across leaf nodes provides a
frequency-domain fingerprint.  Anomalies are detected via the
Kullback-Leibler divergence D_KL(P_test ‖ P_ref) or the symmetric
Jensen-Shannon divergence D_JS.

**Novel contribution**: combining wavelet packet spectral fingerprints
with KL/JS divergence scoring in a DARP-compliant, cryptographically
provenant pipeline — to our knowledge, not previously integrated in
anomaly-detection evaluation frameworks.

**No live telemetry** — operates on historical arrays only.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g7_contracts import (
    SpectralDivergenceScore,
    WaveletNode,
    WaveletPacketSpectrum,
)

__all__ = [
    "haar_wavelet_packet_decompose",
    "build_energy_spectrum",
    "spectral_divergence",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SQRT2_INV: float = 1.0 / math.sqrt(2.0)
_EPS: float = 1e-15  # floor to avoid log(0)


# ---------------------------------------------------------------------------
# Haar wavelet packet transform (from first principles)
# ---------------------------------------------------------------------------


def _haar_low(signal: NDArray[np.float64]) -> NDArray[np.float64]:
    """Apply Haar low-pass filter and downsample by 2.

    h[n] = [1/√2, 1/√2]  →  y[k] = (x[2k] + x[2k+1]) / √2
    """
    n = len(signal)
    # Pad to even length if needed
    if n % 2 != 0:
        signal = np.append(signal, signal[-1])
        n += 1
    return (signal[0:n:2] + signal[1:n:2]) * _SQRT2_INV


def _haar_high(signal: NDArray[np.float64]) -> NDArray[np.float64]:
    """Apply Haar high-pass filter and downsample by 2.

    g[n] = [1/√2, −1/√2]  →  y[k] = (x[2k] − x[2k+1]) / √2
    """
    n = len(signal)
    if n % 2 != 0:
        signal = np.append(signal, signal[-1])
        n += 1
    return (signal[0:n:2] - signal[1:n:2]) * _SQRT2_INV


def haar_wavelet_packet_decompose(
    signal: NDArray[np.float64],
    *,
    depth: int,
) -> dict[tuple[int, int], NDArray[np.float64]]:
    """Full wavelet packet decomposition to the specified depth.

    Parameters
    ----------
    signal:
        1-D array of float64 values (NaNs are replaced by 0).
    depth:
        Decomposition depth (1 ≤ depth ≤ 12).

    Returns
    -------
    Dictionary mapping (level, index) → coefficient array for every
    node in the full binary tree from level 0 to ``depth``.

    Raises
    ------
    ValueError
        If signal is not 1-D or depth is out of range.
    """
    if signal.ndim != 1:
        raise ValueError("Signal must be 1-D")
    if not 1 <= depth <= 12:
        raise ValueError(f"Depth must be in [1, 12], got {depth}")
    if len(signal) < 2:
        raise ValueError("Signal must have at least 2 samples")

    # Replace NaN with 0 (missing data = no energy contribution)
    clean = np.where(np.isnan(signal), 0.0, signal).astype(np.float64)

    # Tree: (level, index) → coefficients
    tree: dict[tuple[int, int], NDArray[np.float64]] = {(0, 0): clean}

    for level in range(1, depth + 1):
        for parent_idx in range(2 ** (level - 1)):
            parent = tree.get((level - 1, parent_idx))
            if parent is None or len(parent) < 2:
                # Leaf reached before target depth — propagate as-is
                tree[(level, 2 * parent_idx)] = parent if parent is not None else np.array([0.0])
                tree[(level, 2 * parent_idx + 1)] = np.array([0.0])
                continue

            # Low-pass (approximation) → left child
            tree[(level, 2 * parent_idx)] = _haar_low(parent)
            # High-pass (detail) → right child
            tree[(level, 2 * parent_idx + 1)] = _haar_high(parent)

    return tree


# ---------------------------------------------------------------------------
# Energy spectrum construction
# ---------------------------------------------------------------------------


def build_energy_spectrum(
    signal: NDArray[np.float64],
    *,
    dataset_id: DatasetId,
    depth: int = 4,
    source_sha256: str,
) -> WaveletPacketSpectrum:
    """Build the normalised wavelet packet energy spectrum.

    Parameters
    ----------
    signal:
        1-D float64 signal array.
    dataset_id:
        Domain identifier.
    depth:
        Wavelet packet decomposition depth (default 4 → 16 sub-bands).
    source_sha256:
        SHA-256 of the source data for provenance.

    Returns
    -------
    WaveletPacketSpectrum contract with energy at each leaf node.
    """
    tree = haar_wavelet_packet_decompose(signal, depth=depth)
    n = max(len(signal), 1)

    # Collect leaf nodes at the target depth
    n_leaves = 2**depth
    nodes: list[WaveletNode] = []
    total_energy = 0.0

    for idx in range(n_leaves):
        coeffs = tree.get((depth, idx))
        if coeffs is None or len(coeffs) == 0:
            energy = 0.0
            count = 0
        else:
            energy = float(np.sum(coeffs**2)) / n
            count = len(coeffs)
        total_energy += energy
        nodes.append(
            WaveletNode(
                level=depth,
                index=idx,
                energy=round(energy, 10),
                coefficient_count=count,
            )
        )

    return WaveletPacketSpectrum(
        dataset_id=dataset_id,
        depth=depth,
        nodes=tuple(nodes),
        total_energy=round(total_energy, 10),
        signal_length=len(signal),
        source_sha256=source_sha256,
    )


# ---------------------------------------------------------------------------
# Spectral divergence scoring
# ---------------------------------------------------------------------------


def _normalise_spectrum(spectrum: WaveletPacketSpectrum) -> NDArray[np.float64]:
    """Extract and normalise the energy vector to a probability distribution."""
    energies = np.array([n.energy for n in spectrum.nodes], dtype=np.float64)
    total = energies.sum()
    if total < _EPS:
        # Uniform distribution when signal has near-zero energy
        return np.full(len(energies), 1.0 / len(energies))
    return energies / total


def spectral_divergence(
    reference: WaveletPacketSpectrum,
    test: WaveletPacketSpectrum,
) -> SpectralDivergenceScore:
    """Compute KL and JS divergence between two wavelet energy spectra.

    Parameters
    ----------
    reference:
        Energy spectrum from the reference (training) signal.
    test:
        Energy spectrum from the test signal.

    Returns
    -------
    SpectralDivergenceScore with both divergence measures, the
    dominant anomaly band, and the maximum per-band energy ratio.

    Raises
    ------
    ValueError
        If spectra have different depths or domains.
    """
    if reference.dataset_id != test.dataset_id:
        raise ValueError("Cross-domain spectral comparison prohibited")
    if reference.depth != test.depth:
        raise ValueError(f"Spectra must have equal depth: {reference.depth} vs {test.depth}")

    p_ref = _normalise_spectrum(reference)
    p_test = _normalise_spectrum(test)
    n_bands = len(p_ref)

    # Floor to avoid log(0)
    p_ref_safe = np.maximum(p_ref, _EPS)
    p_test_safe = np.maximum(p_test, _EPS)

    # KL divergence: D_KL(P_test ‖ P_ref) = Σ P_test · log(P_test / P_ref)
    kl = float(np.sum(p_test_safe * np.log(p_test_safe / p_ref_safe)))

    # Jensen-Shannon divergence: D_JS = ½ D_KL(P‖M) + ½ D_KL(Q‖M)
    m = 0.5 * (p_ref_safe + p_test_safe)
    js = float(
        0.5 * np.sum(p_ref_safe * np.log(p_ref_safe / m))
        + 0.5 * np.sum(p_test_safe * np.log(p_test_safe / m))
    )

    # Find the sub-band with maximum energy ratio change
    ratios = np.where(
        p_ref_safe > _EPS,
        p_test_safe / p_ref_safe,
        np.ones(n_bands),
    )
    max_ratio_band = int(np.argmax(np.abs(np.log(np.maximum(ratios, _EPS)))))
    max_ratio = float(ratios[max_ratio_band])

    # Provenance hashes
    ref_hash = hashlib.sha256(
        json.dumps([float(x) for x in p_ref], separators=(",", ":")).encode()
    ).hexdigest()
    test_hash = hashlib.sha256(
        json.dumps([float(x) for x in p_test], separators=(",", ":")).encode()
    ).hexdigest()

    return SpectralDivergenceScore(
        dataset_id=reference.dataset_id,
        kl_divergence=round(max(kl, 0.0), 10),
        js_divergence=round(max(js, 0.0), 10),
        n_subbands=n_bands,
        max_subband_ratio=round(max_ratio, 10),
        dominant_anomaly_band=max_ratio_band,
        reference_sha256=ref_hash,
        test_sha256=test_hash,
    )
