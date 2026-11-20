"""Compatibility entry point for the unified five-source risk engine.

New code should call :func:`build_unified_risk_assessment`.  The historical
``build_risk_assessment`` tuple return is preserved for the transactional
case service and other existing callers.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .contracts import (
    AxisAssessment,
    ClaimExtractionResult,
    ConflictCandidate,
    RiskClue,
    VerificationCandidate,
)
from .unified_risk import (
    RiskItem,
    RiskSourceCoverage,
    RiskSourceType,
    UnifiedRiskAssessment,
    build_unified_risk_assessment,
    risk_item_to_clue,
    risk_items_to_clues,
)


def build_risk_assessment(
    *,
    claim_result: ClaimExtractionResult,
    conflicts: Iterable[ConflictCandidate],
    verifications: Iterable[VerificationCandidate],
    indicators: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
    facts: Iterable[Mapping[str, Any]],
    fact_evidence_links: Iterable[Mapping[str, Any]] = (),
    rule_count: int,
) -> tuple[list[RiskClue], list[AxisAssessment]]:
    """Return legacy clues/axes while using the unified engine internally."""

    assessment = build_unified_risk_assessment(
        claim_result=claim_result,
        conflicts=conflicts,
        verifications=verifications,
        indicators=indicators,
        observations=observations,
        facts=facts,
        fact_evidence_links=fact_evidence_links,
        rule_count=rule_count,
    )
    return risk_items_to_clues(assessment.risk_items), list(assessment.axes)


__all__ = [
    "RiskItem",
    "RiskSourceCoverage",
    "RiskSourceType",
    "UnifiedRiskAssessment",
    "build_risk_assessment",
    "build_unified_risk_assessment",
    "risk_item_to_clue",
    "risk_items_to_clues",
]
