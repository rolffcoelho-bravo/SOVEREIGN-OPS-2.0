"""G8.3 — Change-point detection + entropy-based regime classification.

Implements pillars 2 and 3 of Adaptive Spectral Regime Detection:

**Pillar 2 — CUSUM Change-Point Detection:**

Page's CUSUM (Cumulative Sum) control chart (Page, 1954) detects
shifts in the mean of a monitored process.  Applied to the spectral
divergence series from G8.2, it identifies regime transitions with
provable average-run-length guarantees:

    S⁺_t = max(0, S⁺_{t-1} + (x_t − μ₀ − k))   [upward shift]
    S⁻_t = max(0, S⁻_{t-1} + (μ₀ − k − x_t))   [downward shift]

Alarm fires when S⁺_t > h or S⁻_t > h.

The in-control ARL₀ = exp(2hk/σ²) / (2hk/σ²) gives the expected
number of observations between false alarms.

**Pillar 3 — Entropy-Signature Regime Classification:**

Each segment between change points is characterised by its Rényi
α-spectrum — the curve H_α(X) for α ∈ (0, ∞) \ {1}:

    H_α(X) = 1/(1−α) · log₂(∑ᵢ pᵢ^α)

The complexity index C = H₀.₅ / H₂.₀ captures the ratio of
rare-event sensitivity to tail dominance.

Segments are clustered via partition-around-medoids (PAM) in
divergence-metric space using the average silhouette width criterion
to select the optimal number of regimes.

All outputs are DARP-compliant frozen contracts.
"""

from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from sovereign_ops.contracts import DatasetId
from sovereign_ops.g8_contracts import (
    ChangePoint,
    ChangePointSeries,
    CUSUMState,
    RegimeCentroid,
    RegimeClassificationResult,
    RegimeSegment,
    RegimeSignature,
    RegimeTransitionMatrix,
)

if TYPE_CHECKING:
    pass

# ── constants ─────────────────────────────────────────────────────

_DEFAULT_CUSUM_K = 0.5  # allowance / slack
_DEFAULT_CUSUM_H = 4.0  # decision interval
_MIN_SEGMENT_SIZE = 2  # minimum segment for entropy estimation
_REGIME_LABELS = ("nominal", "degraded", "anomalous", "transitional")


# ── 1. CUSUM change-point detection ──────────────────────────────


def cusum_detect(
    series: NDArray[np.float64],
    k: float = _DEFAULT_CUSUM_K,
    h: float = _DEFAULT_CUSUM_H,
    mu_0: float | None = None,
) -> tuple[list[CUSUMState], list[ChangePoint]]:
    """Two-sided CUSUM detection on a 1-D series.

    Parameters
    ----------
    series : array
        Monitored process (spectral divergence series).
    k : float
        Allowance / slack parameter.
    h : float
        Decision interval (alarm threshold).
    mu_0 : float or None
        In-control mean.  If None, estimated from the first
        quarter of the series.

    Returns
    -------
    states : list[CUSUMState]
        CUSUM state at each time step.
    change_points : list[ChangePoint]
        Detected alarm locations.
    """
    n = len(series)
    if n == 0:
        return [], []

    # Estimate in-control mean from calibration region
    if mu_0 is None:
        cal_end = max(1, n // 4)
        mu_0 = float(np.mean(series[:cal_end]))

    s_plus = 0.0
    s_minus = 0.0
    last_alarm = -1
    states: list[CUSUMState] = []
    change_points: list[ChangePoint] = []

    for t in range(n):
        x = float(series[t])
        s_plus = max(0.0, s_plus + (x - mu_0 - k))
        s_minus = max(0.0, s_minus + (mu_0 - k - x))

        alarm_p = s_plus > h
        alarm_m = s_minus > h

        states.append(
            CUSUMState(
                step=t,
                observation=x,
                cusum_plus=s_plus,
                cusum_minus=s_minus,
                alarm_plus=alarm_p,
                alarm_minus=alarm_m,
            )
        )

        if alarm_p or alarm_m:
            run_length = t - last_alarm if last_alarm >= 0 else t + 1
            sig = 1.0 - math.exp(-max(s_plus, s_minus) / h)  # heuristic confidence
            sig = max(0.0, min(1.0, sig))

            change_points.append(
                ChangePoint(
                    location=t,
                    direction="increase" if alarm_p else "decrease",
                    cusum_value=max(s_plus, s_minus),
                    threshold=h,
                    run_length=max(1, run_length),
                    significance=sig,
                )
            )
            last_alarm = t
            # Reset after alarm
            if alarm_p:
                s_plus = 0.0
            if alarm_m:
                s_minus = 0.0

    return states, change_points


def build_change_point_series(
    series: NDArray[np.float64],
    dataset_id: DatasetId,
    k: float = _DEFAULT_CUSUM_K,
    h: float = _DEFAULT_CUSUM_H,
) -> ChangePointSeries:
    """Full CUSUM detection pipeline returning a DARP-compliant contract.

    Parameters
    ----------
    series : array
        Spectral divergence series.
    dataset_id : DatasetId
        Source dataset identifier.
    k, h : float
        CUSUM parameters.

    Returns
    -------
    ChangePointSeries
        Frozen contract with all detected change points.
    """
    n = len(series)
    cal_end = max(1, n // 4)
    mu_0 = float(np.mean(series[:cal_end])) if n > 0 else 0.0
    std_0 = float(np.std(series[:cal_end], ddof=1)) if cal_end > 1 else 1.0

    _states, cps = cusum_detect(series, k=k, h=h, mu_0=mu_0)

    # Estimate in-control ARL₀
    # ARL₀ ≈ exp(2hk/σ²) / (2hk/σ²) for small k
    ratio = 2 * h * k / max(std_0**2, 1e-12)
    arl_0 = math.exp(ratio) / max(ratio, 1e-12) if ratio > 0 else float("inf")
    arl_0 = min(arl_0, 1e10)  # cap for numerical sanity

    sha = hashlib.sha256(series.tobytes()).hexdigest()

    return ChangePointSeries(
        dataset_id=dataset_id,
        change_points=tuple(cps),
        n_detected=len(cps),
        cusum_k=k,
        cusum_h=h,
        in_control_mean=mu_0,
        in_control_std=std_0,
        average_run_length_0=arl_0,
        monitoring_sha256=sha,
    )


# ── 2. Rényi entropy ─────────────────────────────────────────────


def renyi_entropy(probs: NDArray[np.float64], alpha: float) -> float:
    """Rényi entropy of order α.

    H_α(X) = 1/(1−α) · log₂(∑ᵢ pᵢ^α)

    Special cases:
    - α → 1: Shannon entropy (handled via limit)
    - α = 0: Hartley entropy (log₂ of support size)
    - α → ∞: min-entropy

    Parameters
    ----------
    probs : array
        Probability distribution (must sum to 1).
    alpha : float
        Order parameter (> 0, ≠ 1 for the general formula).

    Returns
    -------
    float
        Rényi entropy in bits.
    """
    p = np.maximum(probs, 1e-15)
    if abs(alpha - 1.0) < 1e-10:
        # Shannon entropy (limit case)
        return float(-np.sum(p * np.log2(p)))
    return float(np.log2(np.sum(p**alpha)) / (1.0 - alpha))


def compute_alpha_spectrum(
    probs: NDArray[np.float64],
    alphas: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0),
) -> tuple[tuple[float, float], ...]:
    """Compute the full Rényi α-spectrum.

    Returns (α, H_α) pairs characterising the distributional
    complexity at different sensitivity levels.
    """
    return tuple((a, renyi_entropy(probs, a)) for a in alphas)


def complexity_index(probs: NDArray[np.float64]) -> float:
    """Complexity index C = H₀.₅ / H₂.₀.

    Ratio of rare-event sensitivity (α=0.5 emphasises rare events)
    to tail dominance (α=2.0 emphasises frequent events).

    C > 1 implies heavy-tailed / diverse distribution.
    C ≈ 1 implies near-uniform.
    C < 1 is degenerate (not typical in practice).
    """
    h_half = renyi_entropy(probs, 0.5)
    h_two = renyi_entropy(probs, 2.0)
    if abs(h_two) < 1e-12:
        return 0.0
    return h_half / h_two


# ── 3. Regime signature construction ─────────────────────────────


def build_regime_signature(
    signal_segment: NDArray[np.float64],
    segment_start: int,
    segment_end: int,
    source_sha256: str,
    max_level: int = 3,
) -> RegimeSignature:
    """Build a Rényi α-spectrum signature for a signal segment.

    Computes the wavelet packet spectrum and then the full
    α-spectrum + complexity index.
    """
    from sovereign_ops.spectral_tracking import wavelet_packet_spectrum

    spectrum = wavelet_packet_spectrum(signal_segment, max_level=max_level)
    alpha_spec = compute_alpha_spectrum(spectrum)
    shannon = renyi_entropy(spectrum, 1.0)
    ci = complexity_index(spectrum)

    return RegimeSignature(
        segment_start=segment_start,
        segment_end=segment_end,
        n_points=len(signal_segment),
        alpha_entropies=alpha_spec,
        shannon_entropy=shannon,
        complexity_index=ci,
        source_sha256=source_sha256,
    )


# ── 4. PAM clustering ────────────────────────────────────────────


def _signature_distance(s1: RegimeSignature, s2: RegimeSignature) -> float:
    """Euclidean distance in α-entropy space between two signatures."""
    e1 = np.array([h for _, h in s1.alpha_entropies])
    e2 = np.array([h for _, h in s2.alpha_entropies])
    return float(np.sqrt(np.sum((e1 - e2) ** 2)))


def _pam_cluster(
    signatures: list[RegimeSignature],
    k: int,
) -> tuple[list[int], list[int], float]:
    """Partition Around Medoids (PAM) clustering.

    Simple implementation of the PAM algorithm for small n:
    1. Initialise medoids as the k most spread-out points.
    2. Assign each point to its nearest medoid.
    3. For each medoid, try swapping with each non-medoid;
       keep the swap if it reduces total dissimilarity.
    4. Repeat until convergence.

    Returns
    -------
    assignments : list[int]
        Cluster assignment for each signature.
    medoid_indices : list[int]
        Indices of the medoid signatures.
    silhouette : float
        Average silhouette width.
    """
    n = len(signatures)
    if n <= k:
        return list(range(n)), list(range(n)), 0.0

    # Distance matrix
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = _signature_distance(signatures[i], signatures[j])
            dist[i, j] = d
            dist[j, i] = d

    # Initialise: pick the first point, then greedily pick farthest
    medoids = [0]
    for _ in range(1, k):
        min_dists = dist[:, medoids].min(axis=1)
        next_m = int(np.argmax(min_dists))
        if next_m not in medoids:
            medoids.append(next_m)
        else:
            # Fallback: pick any unselected point
            for idx in range(n):
                if idx not in medoids:
                    medoids.append(idx)
                    break

    # Iterate
    for _iteration in range(50):
        # Assign
        assignments = [int(np.argmin([dist[i, m] for m in medoids])) for i in range(n)]

        # Swap
        improved = False
        for mi in range(k):
            current_cost = sum(dist[i, medoids[mi]] for i in range(n) if assignments[i] == mi)
            best_cost = current_cost
            best_swap = medoids[mi]
            for candidate in range(n):
                if candidate in medoids:
                    continue
                cost = sum(dist[i, candidate] for i in range(n) if assignments[i] == mi)
                if cost < best_cost:
                    best_cost = cost
                    best_swap = candidate
                    improved = True
            medoids[mi] = best_swap

        if not improved:
            break

    # Final assignment
    assignments = [int(np.argmin([dist[i, m] for m in medoids])) for i in range(n)]

    # Silhouette
    silhouette = _compute_silhouette(dist, assignments, k)

    return assignments, medoids, silhouette


def _compute_silhouette(
    dist: NDArray[np.float64],
    assignments: list[int],
    k: int,
) -> float:
    """Average silhouette width."""
    n = len(assignments)
    if k <= 1 or n <= 1:
        return 0.0

    sils: list[float] = []
    for i in range(n):
        ci = assignments[i]
        # a(i) = mean distance to same-cluster points
        same = [j for j in range(n) if assignments[j] == ci and j != i]
        if not same:
            sils.append(0.0)
            continue
        a_i = float(np.mean([dist[i, j] for j in same]))

        # b(i) = min mean distance to other clusters
        b_i = float("inf")
        for ck in range(k):
            if ck == ci:
                continue
            others = [j for j in range(n) if assignments[j] == ck]
            if others:
                mean_d = float(np.mean([dist[i, j] for j in others]))
                b_i = min(b_i, mean_d)

        if b_i == float("inf"):
            sils.append(0.0)
        else:
            sils.append((b_i - a_i) / max(a_i, b_i, 1e-12))

    return float(np.mean(sils))


# ── 5. Full regime classification ────────────────────────────────


def _assign_regime_label(
    centroid_complexity: float,
    all_complexities: list[float],
) -> str:
    """Assign a regime label based on complexity index rank.

    nominal:       lowest complexity (most regular)
    degraded:      below median
    anomalous:     above 75th percentile
    transitional:  highest complexity
    """
    if not all_complexities:
        return "nominal"
    sorted_c = sorted(all_complexities)
    rank = sorted_c.index(centroid_complexity) if centroid_complexity in sorted_c else 0
    frac = rank / max(len(sorted_c) - 1, 1)
    if frac <= 0.25:
        return "nominal"
    elif frac <= 0.50:
        return "degraded"
    elif frac <= 0.75:
        return "anomalous"
    else:
        return "transitional"


def classify_regimes(
    signal: NDArray[np.float64],
    change_point_locations: list[int],
    dataset_id: DatasetId,
    source_sha256: str,
    max_regimes: int = 4,
    max_level: int = 3,
) -> RegimeClassificationResult:
    """Full regime classification pipeline.

    1. Segments the signal at change-point locations.
    2. Builds a Rényi α-spectrum signature per segment.
    3. Clusters segments via PAM.
    4. Builds the transition matrix.

    Parameters
    ----------
    signal : array
        Original time-series.
    change_point_locations : list[int]
        Change-point indices from CUSUM detection.
    dataset_id : DatasetId
        Source dataset identifier.
    source_sha256 : str
        SHA-256 of the source data.
    max_regimes : int
        Maximum number of regimes to consider.
    max_level : int
        Wavelet decomposition depth.

    Returns
    -------
    RegimeClassificationResult
        Complete DARP-compliant regime classification.
    """
    n = len(signal)

    # Build segment boundaries
    boundaries = sorted(set([0] + change_point_locations + [n]))
    segments_raw: list[tuple[int, int]] = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        if e - s >= _MIN_SEGMENT_SIZE:
            segments_raw.append((s, e))

    if not segments_raw:
        segments_raw = [(0, n)]

    # Build signatures
    signatures: list[RegimeSignature] = []
    for s, e in segments_raw:
        sig = build_regime_signature(signal[s:e], s, e, source_sha256, max_level=max_level)
        signatures.append(sig)

    # Find optimal k via silhouette
    best_k = 1
    best_sil = -1.0
    best_assignments: list[int] = [0] * len(signatures)
    best_medoids: list[int] = [0]

    for k in range(1, min(max_regimes + 1, len(signatures) + 1)):
        assignments, medoids, sil = _pam_cluster(signatures, k)
        if k == 1:
            best_assignments = assignments
            best_medoids = medoids
            best_sil = 0.0
        elif sil > best_sil:
            best_k = k
            best_sil = sil
            best_assignments = assignments
            best_medoids = medoids

    # Build centroids and assign labels
    complexities = [signatures[m].complexity_index for m in best_medoids]
    centroids: list[RegimeCentroid] = []
    for ci, mi in enumerate(best_medoids):
        label = _assign_regime_label(signatures[mi].complexity_index, complexities)
        members = [j for j, a in enumerate(best_assignments) if a == ci]
        intra_div = (
            float(np.mean([_signature_distance(signatures[j], signatures[mi]) for j in members]))
            if members
            else 0.0
        )

        centroids.append(
            RegimeCentroid(
                regime_id=ci,
                regime_label=label,  # type: ignore[arg-type]
                centroid_entropies=signatures[mi].alpha_entropies,
                centroid_complexity=signatures[mi].complexity_index,
                n_members=len(members),
                intra_cluster_divergence=intra_div,
            )
        )

    # Build regime segments
    regime_segments: list[RegimeSegment] = []
    for sig, cluster_id in zip(signatures, best_assignments, strict=True):
        centroid = centroids[cluster_id]
        dist_to_c = _signature_distance(sig, signatures[best_medoids[cluster_id]])

        regime_segments.append(
            RegimeSegment(
                segment_start=sig.segment_start,
                segment_end=sig.segment_end,
                regime_id=centroid.regime_id,
                regime_label=centroid.regime_label,
                distance_to_centroid=dist_to_c,
                signature=sig,
            )
        )

    # Transition matrix
    transition_matrix = _build_transition_matrix(
        [rs.regime_id for rs in regime_segments],
        best_k,
        dataset_id,
    )

    cls_sha = hashlib.sha256("|".join(s.source_sha256 for s in signatures).encode()).hexdigest()

    return RegimeClassificationResult(
        dataset_id=dataset_id,
        segments=tuple(regime_segments),
        centroids=tuple(centroids),
        transition_matrix=transition_matrix,
        n_regimes=best_k,
        silhouette_score=best_sil,
        n_total_points=n,
        classification_sha256=cls_sha,
    )


def _build_transition_matrix(
    regime_sequence: list[int],
    n_regimes: int,
    dataset_id: DatasetId,
) -> RegimeTransitionMatrix:
    """Build empirical transition probability matrix."""
    counts = [[0] * n_regimes for _ in range(n_regimes)]
    n_transitions = 0
    for i in range(len(regime_sequence) - 1):
        fr, to = regime_sequence[i], regime_sequence[i + 1]
        if 0 <= fr < n_regimes and 0 <= to < n_regimes:
            counts[fr][to] += 1
            n_transitions += 1

    # Normalise to probabilities (row-stochastic)
    probs = []
    for row in counts:
        total = sum(row)
        if total > 0:
            probs.append(tuple(c / total for c in row))
        else:
            # Uniform if no transitions observed from this state
            probs.append(tuple(1.0 / n_regimes for _ in row))

    # Stationary distribution via eigenvalue
    p_matrix = np.array(probs)
    try:
        eigenvalues, eigenvectors = np.linalg.eig(p_matrix.T)
        # Find eigenvalue closest to 1
        idx_1 = int(np.argmin(np.abs(eigenvalues - 1.0)))
        pi = np.real(eigenvectors[:, idx_1])
        pi = np.abs(pi) / np.abs(pi).sum()
        stat_dist = tuple(float(x) for x in pi)
    except np.linalg.LinAlgError:
        stat_dist = tuple(1.0 / n_regimes for _ in range(n_regimes))

    # Stationarity index: 1 − |λ₂|/|λ₁|
    try:
        evals = sorted(np.abs(eigenvalues), reverse=True)
        if len(evals) >= 2 and evals[0] > 1e-12:
            stat_idx = 1.0 - evals[1] / evals[0]
        else:
            stat_idx = 1.0
    except Exception:
        stat_idx = 0.5

    return RegimeTransitionMatrix(
        dataset_id=dataset_id,
        n_regimes=n_regimes,
        transition_counts=tuple(tuple(row) for row in counts),
        transition_probabilities=tuple(probs),
        stationary_distribution=stat_dist,
        stationarity_index=max(0.0, min(1.0, stat_idx)),
        n_transitions=n_transitions,
    )
