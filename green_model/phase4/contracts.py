"""Contracts for case-level green-credit intelligence.

The contracts deliberately distinguish a *risk clue* from a credit decision.
No extractor or rule evaluator is permitted to approve/reject a loan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from green_model.agent.domain.enums import CoverageStatus, RiskDimension, RiskLevel


@dataclass(frozen=True)
class EvidenceInput:
    evidence_id: str
    text: str
    doc_id: str | None = None
    page_number: int | None = None


@dataclass(frozen=True)
class ExtractedClaim:
    text: str
    claim_type: str | None
    green_relevance: str | None
    evidence_strength: str | None
    support_status: str
    evidence_id: str | None
    extraction_method: str
    is_model_output: bool
    model_run_id: str | None = None
    prediction_id: str | None = None
    inference_policy_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelPredictionDecision:
    """Governed sentence-level model output retained for audit and coverage."""

    prediction_id: str
    model_run_id: str
    sentence_index: int
    sentence_sha256: str
    text: str
    decision_status: str
    inference_policy_version: str
    evidence_id: str | None = None
    doc_id: str | None = None
    page_number: int | None = None
    abstention_reason: str | None = None
    green_relevance: str | None = None
    green_relevance_confidence: float | None = None
    green_relevance_margin: float | None = None
    evidence_strength: str | None = None
    evidence_strength_confidence: float | None = None
    claim_type: str | None = None
    claim_type_confidence: float | None = None
    class_probabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimExtractionResult:
    claims: tuple[ExtractedClaim, ...]
    coverage_status: CoverageStatus
    message: str
    model_run_id: str | None = None
    predictions: tuple[ModelPredictionDecision, ...] = ()


class ClaimExtractor(Protocol):
    """Pluggable extractor contract used by the risk engine."""

    name: str
    version: str

    def extract(
        self, case_id: str, evidence: Sequence[EvidenceInput]
    ) -> ClaimExtractionResult:
        ...


@dataclass(frozen=True)
class ConflictCandidate:
    semantic_key: str
    field_name: str
    conflict_type: str
    fact_a_id: str
    fact_b_id: str
    evidence_a_id: str | None
    evidence_b_id: str | None
    raw_value_a: str | None
    raw_value_b: str | None
    normalized_value_a: str | None
    normalized_value_b: str | None
    difference_value: str | None
    difference_unit: str | None
    denominator_value: str | None
    difference_ratio: str | None
    comparison_method: str
    risk_level: RiskLevel


@dataclass(frozen=True)
class VerificationCandidate:
    semantic_key: str
    rule_version_id: str | None
    dimension: RiskDimension
    requirement_text: str
    status: str
    applicability_reason: str
    next_action: str | None
    fact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    master_rule_type: str | None = None
    master_rule_id: str | None = None
    source_manifest_id: str | None = None
    phase36_item_id: str | None = None
    application_mapping_id: str | None = None
    module: str | None = None
    source_locator: str | None = None
    prescribed_task_type: str | None = None
    required_evidence_ids: tuple[str, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    task_bundle_key: str | None = None
    why_verify: str | None = None
    customer_manager_focus: str | None = None
    is_mock: bool = False


@dataclass(frozen=True)
class RiskClue:
    semantic_key: str
    dimension: RiskDimension
    trigger_type: str
    level: RiskLevel
    priority: int
    text: str
    coverage_status: CoverageStatus
    evidence_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    rule_version_ids: tuple[str, ...] = ()
    is_model_result: bool = False
    provenance_kind: str = "manual"
    model_run_id: str | None = None
    inference_policy_version: str | None = None


@dataclass(frozen=True)
class AxisAssessment:
    dimension: RiskDimension
    coverage_status: CoverageStatus
    attention_score: int | None
    risk_level: RiskLevel
    finding_count: int
    summary: str


@dataclass(frozen=True)
class AssessmentResult:
    analysis_run_id: str
    case_id: str
    reused: bool
    simulation: bool
    axes: tuple[AxisAssessment, ...]
    conflict_count: int
    verification_count: int
    claim_count: int
    task_count: int
    model_run_id: str | None
    boundary: str = (
        "系统仅生成风险线索、核验状态与任务，不代替授信审批、"
        "绿色属性最终认定或人工复核。"
    )
