"""Typed Phase 1 business objects.

These dataclasses are transport contracts rather than an ORM.  SQLite is the
source of truth; values absent from legacy material remain ``None``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .enums import (
    CaseStatus,
    DataOrigin,
    DocumentParseStatus,
    RiskLevel,
    RoleType,
    SourceStatus,
    TaskStatus,
    VerificationStatus,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def stable_id(prefix: str, namespace: str) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, namespace).hex}"


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


class RecordMixin:
    def to_record(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}


@dataclass(kw_only=True)
class Case(RecordMixin):
    case_id: str = field(default_factory=lambda: new_id("case"))
    case_name: str | None = None
    borrower_name: str | None = None
    project_name: str | None = None
    primary_industry: str | None = None
    green_category: str | None = None
    project_activity: str | None = None
    enterprise_stage: str | None = None
    project_stage: str | None = None
    loan_stage: str | None = None
    status: CaseStatus = CaseStatus.DRAFT
    assignee: str | None = None
    due_at: str | None = None
    conclusion_status: str | None = None
    notes: str | None = None
    current_revision: int = 0
    failed_from_status: str | None = None
    record_origin: DataOrigin = DataOrigin.USER_UPLOAD
    legacy_note: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class Document(RecordMixin):
    doc_id: str = field(default_factory=lambda: new_id("doc"))
    case_id: str
    file_name: str
    file_type: str | None = None
    mime_type: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    original_path: str | None = None
    version_label: str | None = None
    page_count: int | None = None
    sha256: str | None = None
    parse_status: DocumentParseStatus = DocumentParseStatus.UPLOADED
    parse_failure_reason: str | None = None
    parent_doc_id: str | None = None
    record_origin: DataOrigin = DataOrigin.USER_UPLOAD
    legacy_note: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class SourceRecord(RecordMixin):
    source_id: str = field(default_factory=lambda: new_id("src"))
    source_type: str | None = None
    title: str | None = None
    issuer: str | None = None
    source_url: str | None = None
    published_at: str | None = None
    effective_at: str | None = None
    expires_at: str | None = None
    accessed_at: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    status: SourceStatus = SourceStatus.CANDIDATE
    authority_level: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ExtractionRun(RecordMixin):
    extraction_run_id: str = field(default_factory=lambda: new_id("extract"))
    case_id: str
    doc_id: str
    parser_name: str | None = None
    parser_version: str | None = None
    input_sha256: str | None = None
    config_hash: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    parsed_pages: int | None = None
    ocr_status: str | None = None
    error_message: str | None = None
    output_revision: int | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ProjectFact(RecordMixin):
    fact_id: str = field(default_factory=lambda: new_id("fact"))
    case_id: str
    extraction_run_id: str | None = None
    fact_category: str | None = None
    subject_id: str | None = None
    scope_text: str | None = None
    raw_value: str | None = None
    normalized_value: str | None = None
    normalized_scale: int | None = None
    unit: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    value_nature: str | None = None
    method: str | None = None
    confidence: float | None = None
    match_basis: str | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class EvidenceSnippet(RecordMixin):
    evidence_id: str = field(default_factory=lambda: new_id("evidence"))
    case_id: str
    doc_id: str | None = None
    source_id: str | None = None
    extraction_run_id: str | None = None
    page_number: int | None = None
    bbox: dict[str, float] | None = None
    locator_type: str | None = None
    locator: dict[str, Any] | None = None
    raw_excerpt: str | None = None
    text_sha256: str | None = None
    extraction_method: str | None = None
    table_cell: str | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING_VERIFICATION
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class RuleVersion(RecordMixin):
    rule_version_id: str = field(default_factory=lambda: new_id("rulev"))
    rule_id: str
    rule_name: str | None = None
    version_label: str | None = None
    source_id: str | None = None
    published_at: str | None = None
    effective_at: str | None = None
    expires_at: str | None = None
    industry: str | None = None
    activity: str | None = None
    applicable_stage: str | None = None
    requirement_text: str | None = None
    threshold_json: dict[str, Any] | None = None
    evidence_requirement: str | None = None
    is_bank_internal: bool = False
    content_hash: str | None = None
    status: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class RulePack(RecordMixin):
    pack_id: str = field(default_factory=lambda: new_id("rulepack"))
    pack_name: str
    industry: str | None = None
    applicable_region: str | None = None
    version_label: str
    source_id: str | None = None
    effective_at: str | None = None
    expires_at: str | None = None
    status: str = "active_reference"
    content_hash: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class VerificationItem(RecordMixin):
    verification_id: str = field(default_factory=lambda: new_id("verify"))
    case_id: str
    risk_dimension: str | None = None
    rule_version_id: str | None = None
    master_rule_type: str | None = None
    master_rule_id: str | None = None
    source_manifest_id: str | None = None
    phase36_item_id: str | None = None
    application_mapping_id: str | None = None
    rule_module: str | None = None
    source_locator: str | None = None
    prescribed_task_type: str | None = None
    why_verify: str | None = None
    customer_manager_focus: str | None = None
    is_mock: bool = False
    requirement_text: str | None = None
    status: VerificationStatus = VerificationStatus.PENDING_VERIFICATION
    assignee: str | None = None
    next_action: str | None = None
    applicability_reason: str | None = None
    analysis_run_id: str | None = None
    is_current: bool = True
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class RiskFinding(RecordMixin):
    finding_id: str = field(default_factory=lambda: new_id("risk"))
    case_id: str
    risk_dimension: str | None = None
    trigger_type: str | None = None
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    review_priority: int | None = None
    finding_text: str | None = None
    coverage_status: str | None = None
    handling_status: str | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    is_model_result: bool = False
    eligible_for_decision: bool = True
    legacy_note: str | None = None
    analysis_run_id: str | None = None
    provenance_kind: str | None = None
    model_run_id: str | None = None
    inference_policy_version: str | None = None
    is_current: bool = True
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ConflictLog(RecordMixin):
    conflict_id: str = field(default_factory=lambda: new_id("conflict"))
    case_id: str
    conflict_type: str | None = None
    field_name: str | None = None
    comparability_status: str | None = None
    fact_a_id: str | None = None
    fact_b_id: str | None = None
    evidence_a_id: str | None = None
    evidence_b_id: str | None = None
    raw_value_a: str | None = None
    raw_value_b: str | None = None
    normalized_value_a: str | None = None
    normalized_value_b: str | None = None
    difference_value: str | None = None
    difference_unit: str | None = None
    ratio_denominator: str | None = None
    denominator_value: str | None = None
    difference_ratio: str | None = None
    comparison_method: str | None = None
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    status: str | None = None
    task_id: str | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    analysis_run_id: str | None = None
    is_current: bool = True
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class Task(RecordMixin):
    task_id: str = field(default_factory=lambda: new_id("task"))
    case_id: str
    task_type: str | None = None
    trigger_reason: str | None = None
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    assignee: str | None = None
    reviewer: str | None = None
    due_at: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    closure_condition: str | None = None
    handling_log_json: list[dict[str, Any]] | None = None
    closing_evidence_id: str | None = None
    recompute_run_id: str | None = None
    closing_decision_id: str | None = None
    analysis_run_id: str | None = None
    recompute_analysis_run_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class BTAIndicator(RecordMixin):
    indicator_id: str = field(default_factory=lambda: new_id("bta"))
    case_id: str
    definition_id: str | None = None
    indicator_name: str | None = None
    indicator_category: str | None = None
    direction: str | None = None
    unit: str | None = None
    statistical_scope: str | None = None
    reporting_frequency: str | None = None
    warning_deviation_ratio: str | None = None
    critical_deviation_ratio: str | None = None
    measurement_method: str | None = None
    measurement_boundary: str | None = None
    basis_version: str | None = None
    source_manifest_id: str | None = None
    is_mock: bool = False
    status: str | None = None
    review_task_id: str | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ModelRun(RecordMixin):
    model_run_id: str = field(default_factory=lambda: new_id("modelrun"))
    case_id: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    checkpoint_hash: str | None = None
    config_hash: str | None = None
    input_hash: str | None = None
    output_json: dict[str, Any] | None = None
    confidence_definition: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    degradation_reason: str | None = None
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    is_real_model_result: bool = True
    eligible_for_decision: bool = True
    legacy_note: str | None = None
    inference_policy_version: str | None = None
    runtime_metadata_json: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ModelPredictionRecord(RecordMixin):
    """One sentence-level screening decision with complete audit lineage.

    A prediction is deliberately ineligible for a lending decision.  The
    record retains screened-out and abstained sentences as well as accepted
    review candidates so model coverage cannot be overstated.
    """

    prediction_id: str = field(default_factory=lambda: new_id("prediction"))
    model_run_id: str
    case_id: str | None = None
    evidence_id: str | None = None
    doc_id: str | None = None
    page_number: int | None = None
    sentence_index: int
    sentence_sha256: str
    prediction_text: str
    decision_status: str
    abstention_reason: str | None = None
    green_relevance: str | None = None
    green_relevance_confidence: float | None = None
    green_relevance_margin: float | None = None
    evidence_strength: str | None = None
    evidence_strength_confidence: float | None = None
    claim_type: str | None = None
    claim_type_confidence: float | None = None
    class_probabilities_json: dict[str, Any] | None = None
    inference_policy_version: str = "risk-screening-policy/1.0"
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    is_real_model_result: bool = False
    eligible_for_decision: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class AnalysisRun(RecordMixin):
    analysis_run_id: str = field(default_factory=lambda: new_id("analysis"))
    case_id: str
    run_kind: str = "initial_assessment"
    engine_name: str = "green-credit-case-intelligence"
    engine_version: str = "1.0.0"
    input_hash: str
    trigger_reason: str | None = None
    base_case_revision: int = 0
    output_revision: int | None = None
    status: str = "running"
    model_run_id: str | None = None
    is_simulation: bool = False
    coverage_json: dict[str, Any] | None = None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ClaimSignal(RecordMixin):
    claim_id: str = field(default_factory=lambda: new_id("claim"))
    case_id: str
    analysis_run_id: str
    evidence_id: str | None = None
    model_run_id: str | None = None
    claim_text: str
    claim_type: str | None = None
    green_relevance: str | None = None
    evidence_strength: str | None = None
    support_status: str = "pending_review"
    extraction_method: str = "unknown"
    is_model_output: bool = False
    requires_human_confirmation: bool = True
    record_origin: DataOrigin = DataOrigin.SYSTEM_DERIVED
    is_current: bool = True
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class HumanDecision(RecordMixin):
    decision_id: str = field(default_factory=lambda: new_id("decision"))
    case_id: str
    target_type: str | None = None
    target_id: str | None = None
    decision: str | None = None
    reason: str | None = None
    actor: str | None = None
    actor_role: RoleType | None = None
    decided_at: str | None = None
    based_on_revision: int | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class AuditLog(RecordMixin):
    audit_id: str = field(default_factory=lambda: new_id("audit"))
    case_id: str | None = None
    action: str
    actor: str | None = None
    actor_role: RoleType | None = None
    occurred_at: str = field(default_factory=utc_now)
    before_state: str | None = None
    after_state: str | None = None
    rule_version_id: str | None = None
    model_run_id: str | None = None
    file_hash: str | None = None
    evidence_locator_json: dict[str, Any] | None = None
    details_json: dict[str, Any] | None = None
    correlation_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1


@dataclass(kw_only=True)
class ReportSnapshot(RecordMixin):
    report_id: str = field(default_factory=lambda: new_id("report"))
    case_id: str
    snapshot_revision: int
    generated_at: str | None = None
    rule_versions_json: list[str] | None = None
    model_versions_json: list[str] | None = None
    source_manifest_hash: str | None = None
    snapshot_json: dict[str, Any] | None = None
    snapshot_hash: str | None = None
    pdf_path: str | None = None
    pdf_hash: str | None = None
    json_path: str | None = None
    json_hash: str | None = None
    status: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    row_version: int = 1
