"""DARP Decision Engine — maps detector evidence to the five-outcome taxonomy.

The decision engine is the protocol's core: it takes one or more
``ModelEvidence`` records from a single domain and produces a
``DecisionEnvelope`` with the appropriate outcome.

**Decision rules** (in priority order):

1. **BLOCK_DATA_INTEGRITY** — data quality below threshold or evidence
   chain integrity check fails.
2. **DEGRADED_SERVICE** — required detector components missing or
   evaluation metrics below minimum thresholds.
3. **ABSTAIN_INSUFFICIENT_EVIDENCE** — not enough decisive evidence
   (high abstention rate or no confident signals).
4. **SUPPORTED_ALERT** — high-confidence anomaly detection with
   corroborating evidence.
5. **INVESTIGATE** — anomaly signals present but confidence below
   the alert threshold.

**Domain isolation** is enforced structurally: the engine refuses
to process evidence from multiple domains in a single decision.
"""

from __future__ import annotations

from sovereign_ops.contracts import (
    AbstentionReason,
    CaseRecord,
    DatasetId,
    DecisionEnvelope,
    EvaluationResult,
    Fraction,
    Identifier,
)
from sovereign_ops.pipeline import PipelineResult

__all__ = [
    "DecisionPolicy",
    "make_decision",
    "make_case",
]


# ---------------------------------------------------------------------------
# Policy configuration
# ---------------------------------------------------------------------------


class DecisionPolicy:
    """Immutable thresholds governing the decision mapping.

    Attributes
    ----------
    min_coverage : float
        Minimum coverage (1 − abstention_rate) to avoid DEGRADED_SERVICE.
    min_f1 : float
        Minimum F1 score to avoid DEGRADED_SERVICE.
    alert_confidence : float
        Score threshold above which SUPPORTED_ALERT is issued.
    investigate_confidence : float
        Score threshold above which INVESTIGATE is issued
        (must be < ``alert_confidence``).
    max_abstention_rate : float
        Above this abstention rate, ABSTAIN_INSUFFICIENT_EVIDENCE.
    """

    min_coverage: float
    min_f1: float
    alert_confidence: float
    investigate_confidence: float
    max_abstention_rate: float

    def __init__(
        self,
        *,
        min_coverage: float = 0.7,
        min_f1: float = 0.3,
        alert_confidence: float = 0.8,
        investigate_confidence: float = 0.5,
        max_abstention_rate: float = 0.5,
    ) -> None:
        if investigate_confidence >= alert_confidence:
            raise ValueError("investigate_confidence must be less than alert_confidence")
        if not (0.0 <= min_coverage <= 1.0):
            raise ValueError("min_coverage must be in [0, 1]")
        if not (0.0 <= max_abstention_rate <= 1.0):
            raise ValueError("max_abstention_rate must be in [0, 1]")

        object.__setattr__(self, "min_coverage", min_coverage)
        object.__setattr__(self, "min_f1", min_f1)
        object.__setattr__(self, "alert_confidence", alert_confidence)
        object.__setattr__(self, "investigate_confidence", investigate_confidence)
        object.__setattr__(self, "max_abstention_rate", max_abstention_rate)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("DecisionPolicy is immutable")


# Default research-mode policy
DEFAULT_POLICY = DecisionPolicy()


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def make_decision(
    result: PipelineResult,
    *,
    asset_id: Identifier = "system",
    policy: DecisionPolicy | None = None,
) -> DecisionEnvelope:
    """Map a pipeline result to a ``DecisionEnvelope``.

    Parameters
    ----------
    result:
        A completed single-domain pipeline result.
    asset_id:
        The asset (subsystem/component) this decision covers.
    policy:
        Decision thresholds.  Defaults to ``DEFAULT_POLICY``.

    Returns
    -------
    DecisionEnvelope
        One of the five DARP outcomes.
    """
    if policy is None:
        policy = DEFAULT_POLICY

    dataset_id: DatasetId = result.dataset_id
    evidence = result.evidence
    evaluation = result.evaluation

    # --- Priority 1: Data integrity ---
    # If evaluation produced zero decided samples, we have no basis
    decided = (
        evaluation.true_positives
        + evaluation.false_positives
        + evaluation.true_negatives
        + evaluation.false_negatives
    )
    if decided == 0:
        return DecisionEnvelope(
            dataset_id=dataset_id,
            asset_id=asset_id,
            outcome="BLOCK_DATA_INTEGRITY",
            confidence=None,
            evidence=(),
            reasons=(AbstentionReason.DATA_INTEGRITY,),
        )

    # --- Priority 2: Degraded service ---
    # Coverage or model quality below minimum thresholds
    degraded_reasons: list[AbstentionReason] = []

    if evaluation.coverage < policy.min_coverage:
        degraded_reasons.append(AbstentionReason.COMPONENT_UNAVAILABLE)

    effective_f1 = evaluation.f1 if evaluation.f1 is not None else 0.0
    if effective_f1 < policy.min_f1:
        degraded_reasons.append(AbstentionReason.INSUFFICIENT_EVIDENCE)

    if degraded_reasons:
        return DecisionEnvelope(
            dataset_id=dataset_id,
            asset_id=asset_id,
            outcome="DEGRADED_SERVICE",
            confidence=_compute_confidence(evaluation),
            evidence=(evidence,),
            reasons=tuple(degraded_reasons),
        )

    # --- Priority 3: Abstention ---
    if evaluation.abstention_rate > policy.max_abstention_rate:
        return DecisionEnvelope(
            dataset_id=dataset_id,
            asset_id=asset_id,
            outcome="ABSTAIN_INSUFFICIENT_EVIDENCE",
            confidence=_compute_confidence(evaluation),
            evidence=(),
            reasons=(AbstentionReason.INSUFFICIENT_EVIDENCE,),
        )

    # --- Priority 4 & 5: Actionable outcomes ---
    confidence = _compute_confidence(evaluation)

    if confidence is not None and confidence >= policy.alert_confidence:
        return DecisionEnvelope(
            dataset_id=dataset_id,
            asset_id=asset_id,
            outcome="SUPPORTED_ALERT",
            confidence=confidence,
            evidence=(evidence,),
            reasons=(),
        )

    if confidence is not None and confidence >= policy.investigate_confidence:
        return DecisionEnvelope(
            dataset_id=dataset_id,
            asset_id=asset_id,
            outcome="INVESTIGATE",
            confidence=confidence,
            evidence=(evidence,),
            reasons=(),
        )

    # Confidence below investigate threshold → abstain
    return DecisionEnvelope(
        dataset_id=dataset_id,
        asset_id=asset_id,
        outcome="ABSTAIN_INSUFFICIENT_EVIDENCE",
        confidence=confidence,
        evidence=(),
        reasons=(AbstentionReason.INSUFFICIENT_EVIDENCE,),
    )


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------


def make_case(
    *,
    decision: DecisionEnvelope,
    case_id: Identifier,
    actor_id: Identifier = "sovereign-ops-pipeline",
    created_at: str | None = None,
) -> CaseRecord:
    """Create an audit-trail ``CaseRecord`` from a decision.

    Parameters
    ----------
    decision:
        The ``DecisionEnvelope`` to persist.
    case_id:
        Unique identifier for this case.
    actor_id:
        Who/what created the case.
    created_at:
        ISO-8601 timestamp.  Defaults to now (UTC).

    Returns
    -------
    CaseRecord
        In ``DRAFT`` status (the only valid initial state).
    """
    from datetime import UTC, datetime

    if created_at is None:
        ts = datetime.now(UTC)
    else:
        ts = datetime.fromisoformat(created_at)

    return CaseRecord(
        case_id=case_id,
        actor_id=actor_id,
        created_at=ts,
        status="DRAFT",
        decision=decision,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_confidence(evaluation: EvaluationResult) -> Fraction | None:
    """Derive a confidence score from evaluation metrics.

    Uses ``coverage × f1`` as the confidence proxy — a detector that
    abstains on many cases or scores poorly gets a lower confidence
    regardless of which metric is weak.

    Returns ``None`` if F1 is undefined.
    """
    if evaluation.f1 is None:
        return None

    raw = float(evaluation.f1) * float(evaluation.coverage)
    # Clamp to [0, 1]
    return max(0.0, min(1.0, raw))
