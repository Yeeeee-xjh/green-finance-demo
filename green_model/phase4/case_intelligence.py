"""Transactional case intelligence service for green-credit review."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from green_model.agent.domain.enums import (
    CoverageStatus,
    DataOrigin,
    RiskDimension,
    RiskLevel,
    RoleType,
    TaskStatus,
    VerificationStatus,
)
from green_model.agent.domain.models import (
    AnalysisRun,
    AuditLog,
    ClaimSignal,
    ConflictLog,
    HumanDecision,
    RiskFinding,
    Task,
    VerificationItem,
    stable_id,
    utc_now,
)
from green_model.agent.storage import SQLiteRepository
from green_model.phase3.bert_adapter import BertInferenceAdapter

from .claim_extraction import BertClaimExtractor
from .conflict_engine import detect_numeric_conflicts
from .contracts import (
    AssessmentResult,
    AxisAssessment,
    ClaimExtractor,
    ConflictCandidate,
    EvidenceInput,
    RiskClue,
    VerificationCandidate,
)
from .unified_risk import (
    RiskSourceCoverage,
    build_unified_risk_assessment,
    risk_items_to_clues,
)
from .rule_materializer import (
    CONTEXT_MODULES,
    SUPPORTED_INDUSTRY_CODES,
    materialize_case_rule_candidates,
)
from .verification_engine import (
    build_master_verification_candidates,
    build_verification_candidates,
)


ENGINE_NAME = "green-credit-risk-and-verification-engine"
ENGINE_VERSION = "4.1.0"

PRESCRIBED_TASK_TYPES = {
    "补件": "supplement_request",
    "冲突核实": "conflict_review",
    "规则核验": "verification_review",
    "现场核验": "onsite_verification",
    "贷后预警": "postloan_alert",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _case_industry_code(case: dict[str, Any]) -> str | None:
    for field in ("primary_industry", "project_activity"):
        for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", str(case.get(field) or "")):
            if match.group(1) in SUPPORTED_INDUSTRY_CODES:
                return match.group(1)
    return None


class CaseIntelligenceService:
    """Build current risk/verification ledgers while preserving history."""

    def __init__(
        self,
        repository: SQLiteRepository,
        claim_extractor: ClaimExtractor | None = None,
    ):
        self.repository = repository
        self.claim_extractor = claim_extractor or BertClaimExtractor(
            BertInferenceAdapter(repository)
        )

    def assess(
        self,
        case_id: str,
        *,
        run_kind: str = "initial_assessment",
        trigger_reason: str | None = None,
        simulation: bool = False,
        actor: str = "system",
    ) -> AssessmentResult:
        case = self.repository.get("cases", case_id)
        if case is None:
            raise LookupError(f"案件不存在：{case_id}")
        if run_kind not in {"initial_assessment", "supplement_reassessment", "manual_rerun"}:
            raise ValueError(f"不支持的分析类型：{run_kind}")

        snapshot = self._snapshot(case_id)
        input_hash = self._input_hash(case, snapshot, simulation=simulation)
        existing = self.repository.find(
            "analysis_runs",
            filters={
                "case_id": case_id,
                "engine_version": ENGINE_VERSION,
                "input_hash": input_hash,
                "run_kind": run_kind,
                "is_simulation": simulation,
            },
            order_by="-created_at",
            limit=1,
        )
        if existing and existing[0]["status"] == "completed":
            return self._result_from_run(existing[0], reused=True)

        if existing:
            run_id = str(existing[0]["analysis_run_id"])
            run = self.repository.update(
                "analysis_runs",
                run_id,
                {
                    "status": "running",
                    "trigger_reason": trigger_reason,
                    "error_message": None,
                    "started_at": utc_now(),
                    "finished_at": None,
                },
                expected_version=existing[0]["row_version"],
            )
        else:
            created = AnalysisRun(
                case_id=case_id,
                run_kind=run_kind,
                engine_name=ENGINE_NAME,
                engine_version=ENGINE_VERSION,
                input_hash=input_hash,
                trigger_reason=trigger_reason,
                base_case_revision=int(case.get("current_revision") or 0),
                status="running",
                is_simulation=simulation,
            )
            run = self.repository.add(created)
            run_id = created.analysis_run_id

        try:
            evidence_inputs = tuple(
                EvidenceInput(
                    evidence_id=str(row["evidence_id"]),
                    text=str(row.get("raw_excerpt") or ""),
                    doc_id=row.get("doc_id"),
                    page_number=row.get("page_number"),
                )
                for row in snapshot["evidence"]
                if row.get("raw_excerpt")
            )
            claim_result = self.claim_extractor.extract(case_id, evidence_inputs)
            conflicts = detect_numeric_conflicts(
                snapshot["facts"],
                snapshot["fact_evidence_links"],
                snapshot["evidence"],
            )
            verifications = build_verification_candidates(
                case=case,
                rules=snapshot["rules"],
                sources=snapshot["sources"],
                facts=snapshot["facts"],
                fact_evidence_links=snapshot["fact_evidence_links"],
                conflicts=conflicts,
            )
            industry_code = _case_industry_code(case)
            registered_phase36_items = [
                row
                for row in snapshot["phase36_rule_items"]
                if str(row.get("industry_code") or "") == str(industry_code or "")
            ]
            if registered_phase36_items:
                verifications.extend(materialize_case_rule_candidates(
                    case=case,
                    phase36_items=registered_phase36_items,
                    application_mappings=snapshot["rule_application_mappings"],
                    evidence_requirements=snapshot["master"]["evidence_requirements"],
                    density_assessments=snapshot["industry_density_assessments"],
                    master_records=snapshot["master"],
                    facts=snapshot["facts"],
                    documents=snapshot["documents"],
                    evidence=snapshot["evidence"],
                    conflicts=conflicts,
                    fact_evidence_links=snapshot["fact_evidence_links"],
                    rule_application_evidence_links=(
                        snapshot["rule_application_evidence_links"]
                    ),
                ))
            else:
                # Phase 3.5 remains a compatibility path only for industries
                # that do not yet have a Phase 3.6 registry.  This avoids two
                # contradictory verification rows for the same underlying rule.
                verifications.extend(build_master_verification_candidates(
                    case=case,
                    master=snapshot["master"],
                    facts=snapshot["facts"],
                    documents=snapshot["documents"],
                    evidence=snapshot["evidence"],
                    fact_evidence_links=snapshot["fact_evidence_links"],
                    conflicts=conflicts,
                ))
            unified_risks = build_unified_risk_assessment(
                claim_result=claim_result,
                conflicts=conflicts,
                verifications=verifications,
                indicators=snapshot["indicators"],
                observations=snapshot["observations"],
                facts=snapshot["facts"],
                fact_evidence_links=snapshot["fact_evidence_links"],
                rule_count=len(snapshot["rules"]) + len(verifications),
            )
            clues = risk_items_to_clues(unified_risks.risk_items)
            axes = list(unified_risks.axes)
            task_count = self._persist(
                run_id=run_id,
                case=case,
                snapshot=snapshot,
                claim_result=claim_result,
                conflicts=conflicts,
                verifications=verifications,
                clues=clues,
                axes=axes,
                source_coverages=list(unified_risks.source_coverages),
                simulation=simulation,
                actor=actor,
            )
            completed = self.repository.get("analysis_runs", run_id)
            if completed is None:
                raise RuntimeError("分析运行记录丢失")
            result = self._result_from_run(completed, reused=False)
            if result.task_count != task_count:
                raise RuntimeError("分析任务计数与持久化摘要不一致")
            return result
        except Exception as exc:
            current = self.repository.get("analysis_runs", run_id)
            if current is not None:
                self.repository.update(
                    "analysis_runs",
                    run_id,
                    {
                        "status": "failed",
                        "finished_at": utc_now(),
                        "error_message": str(exc)[:1000],
                    },
                    expected_version=current["row_version"],
                )
            raise

    def submit_supplement_for_reassessment(
        self,
        task_id: str,
        *,
        evidence_ids: list[str],
        actor: str,
        simulation: bool = False,
    ) -> AssessmentResult:
        """Reassess a supplement and move the task to review, never to closed."""

        task = self.repository.get("tasks", task_id)
        if task is None:
            raise LookupError(f"任务不存在：{task_id}")
        if task["status"] != TaskStatus.IN_PROGRESS.value:
            raise ValueError("补件提交前任务必须处于“处理中”，不得跳过状态机。")
        if not evidence_ids:
            raise ValueError("补件证据不能为空")
        for evidence_id in evidence_ids:
            evidence = self.repository.get("evidence_snippets", evidence_id)
            if evidence is None or evidence.get("case_id") != task["case_id"]:
                raise ValueError(f"补件证据不属于当前案件：{evidence_id}")

        result = self.assess(
            str(task["case_id"]),
            run_kind="supplement_reassessment",
            trigger_reason=f"任务{task_id}补件后重算",
            simulation=simulation,
            actor=actor,
        )
        if result.simulation:
            raise ValueError("模拟分析结果不得推进真实业务任务。")
        with self.repository.transaction() as uow:
            current = uow.require("tasks", task_id)
            if current["status"] != TaskStatus.IN_PROGRESS.value:
                raise ValueError("任务状态已变更，请刷新后重试。")
            for evidence_id in evidence_ids:
                uow.insert("task_evidence_links", {
                    "task_id": task_id,
                    "evidence_id": evidence_id,
                    "link_role": "supplement",
                }, on_conflict="ignore")
            uow.update(
                "tasks",
                task_id,
                {
                    "status": TaskStatus.PENDING_REVIEW.value,
                    "recompute_analysis_run_id": result.analysis_run_id,
                },
                expected_version=current["row_version"],
            )
            uow.add(AuditLog(
                case_id=str(task["case_id"]),
                action="supplement_reassessed_pending_human_review",
                actor=actor,
                before_state=TaskStatus.IN_PROGRESS.value,
                after_state=TaskStatus.PENDING_REVIEW.value,
                details_json={
                    "task_id": task_id,
                    "analysis_run_id": result.analysis_run_id,
                    "evidence_ids": evidence_ids,
                    "automatic_close": False,
                },
            ))
        return result

    def record_human_confirmation(
        self,
        *,
        case_id: str,
        target_type: str,
        target_id: str,
        decision: str,
        reason: str,
        actor: str,
        actor_role: RoleType,
    ) -> dict[str, Any]:
        if actor_role not in {
            RoleType.REVIEWER,
            RoleType.APPROVER,
            RoleType.TEAM_LEAD,
            RoleType.ADMINISTRATOR,
        }:
            raise PermissionError("只有复核、审批、团队负责人或管理员角色可确认。")
        table_by_type = {
            "risk": "risk_findings",
            "verification": "verification_items",
            "conflict": "conflict_logs",
            "task": "tasks",
        }
        table = table_by_type.get(target_type)
        if table is None:
            raise ValueError(f"不支持的确认对象：{target_type}")
        target = self.repository.get(table, target_id)
        if target is None or target.get("case_id") != case_id:
            raise LookupError("确认对象不存在或不属于当前案件。")
        human_decision = HumanDecision(
            case_id=case_id,
            target_type=target_type,
            target_id=target_id,
            decision=decision,
            reason=reason,
            actor=actor,
            actor_role=actor_role,
            decided_at=utc_now(),
            based_on_revision=int(target.get("row_version") or 1),
        )
        return self.repository.add(human_decision)

    def current_view(self, case_id: str) -> dict[str, Any]:
        runs = [row for row in self.repository.find(
            "analysis_runs",
            filters={"case_id": case_id, "status": "completed"},
            order_by="-created_at",
        ) if not row.get("is_simulation")]
        return {
            "run": runs[0] if runs else None,
            "claims": self.repository.find(
                "claim_signals", filters={"case_id": case_id, "is_current": 1}
            ),
            "conflicts": self.repository.find(
                "conflict_logs", filters={"case_id": case_id, "is_current": 1}
            ),
            "verifications": self.repository.find(
                "verification_items", filters={"case_id": case_id, "is_current": 1}
            ),
            "risks": self.repository.find(
                "risk_findings", filters={"case_id": case_id, "is_current": 1}
            ),
            "tasks": self.repository.find("tasks", filters={"case_id": case_id}),
            "human_confirmation_required": True,
            "automatic_credit_decision": False,
        }

    def run_view(self, analysis_run_id: str) -> dict[str, Any]:
        """Return one immutable run, including explicitly marked simulations."""
        run = self.repository.get("analysis_runs", analysis_run_id)
        if run is None:
            raise LookupError(f"分析运行不存在：{analysis_run_id}")
        return {
            "run": run,
            "claims": self.repository.find(
                "claim_signals", filters={"analysis_run_id": analysis_run_id}
            ),
            "conflicts": self.repository.find(
                "conflict_logs", filters={"analysis_run_id": analysis_run_id}
            ),
            "verifications": self.repository.find(
                "verification_items", filters={"analysis_run_id": analysis_run_id}
            ),
            "risks": self.repository.find(
                "risk_findings", filters={"analysis_run_id": analysis_run_id}
            ),
            "simulation": bool(run.get("is_simulation")),
            "eligible_for_business_decision": False,
        }

    def _snapshot(self, case_id: str) -> dict[str, Any]:
        indicators = self.repository.find("bta_indicators", filters={"case_id": case_id})
        indicator_ids = {row["indicator_id"] for row in indicators}
        observations = [
            row for row in self.repository.find("bta_observations")
            if row.get("indicator_id") in indicator_ids
        ]
        facts = self.repository.find("project_facts", filters={"case_id": case_id})
        fact_ids = {row["fact_id"] for row in facts}
        fact_links = [
            row for row in self.repository.find("fact_evidence_links")
            if row.get("fact_id") in fact_ids
        ]
        evidence = self.repository.find("evidence_snippets", filters={"case_id": case_id})
        rules = self.repository.find("rule_versions")
        source_ids = {row.get("source_id") for row in rules if row.get("source_id")}
        sources = [
            row for row in self.repository.find("source_records")
            if row.get("source_id") in source_ids
        ]
        master_tables = (
            "source_manifest",
            "industry_knowledge_items",
            "industry_standard_links",
            "indicator_definitions",
            "threshold_definitions",
            "permit_requirements",
            "document_requirements",
            "evidence_requirements",
            "industry_risk_points",
            "postloan_indicator_definitions",
            "term_cards",
        )
        return {
            "documents": self.repository.find("documents", filters={"case_id": case_id}),
            "facts": facts,
            "evidence": evidence,
            "fact_evidence_links": fact_links,
            "rules": rules,
            "sources": sources,
            "indicators": indicators,
            "observations": observations,
            "phase36_rule_items": self.repository.find("phase36_rule_items"),
            "rule_application_mappings": self.repository.find(
                "rule_application_mappings"
            ),
            "rule_application_evidence_links": self.repository.find(
                "rule_application_evidence_links"
            ),
            "industry_density_assessments": self.repository.find(
                "industry_density_assessments"
            ),
            "master": {
                table: self.repository.find(table) for table in master_tables
            },
        }

    def _input_hash(
        self,
        case: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        simulation: bool,
    ) -> str:
        material = {
            "case": {
                key: case.get(key) for key in (
                    "case_id", "primary_industry", "project_activity", "enterprise_stage",
                    "project_stage", "loan_stage", "current_revision", "updated_at"
                )
            },
            "documents": [
                (row.get("doc_id"), row.get("sha256"), row.get("parse_status"), row.get("row_version"))
                for row in snapshot["documents"]
            ],
            "facts": [
                (row.get("fact_id"), row.get("normalized_value"), row.get("unit"), row.get("row_version"))
                for row in snapshot["facts"]
            ],
            "evidence": [
                (row.get("evidence_id"), row.get("text_sha256"), row.get("verification_status"), row.get("row_version"))
                for row in snapshot["evidence"]
            ],
            "rules": [
                (row.get("rule_version_id"), row.get("content_hash"), row.get("status"), row.get("row_version"))
                for row in snapshot["rules"]
            ],
            "observations": [
                (row.get("observation_id"), row.get("normalized_value"), row.get("unit"), row.get("row_version"))
                for row in snapshot["observations"]
            ],
            "phase36_rule_items": [
                (
                    row.get("phase36_item_id"), row.get("record_id"),
                    row.get("validation_status"), row.get("formal_density_eligible"),
                    row.get("is_mock"), row.get("row_version"),
                )
                for row in snapshot["phase36_rule_items"]
            ],
            "rule_application_mappings": [
                (
                    row.get("application_mapping_id"), row.get("phase36_item_id"),
                    row.get("evidence_requirement_ids_json"), row.get("task_type"),
                    row.get("is_mock"), row.get("row_version"),
                )
                for row in snapshot["rule_application_mappings"]
            ],
            "rule_application_evidence_links": [
                (row.get("application_mapping_id"), row.get("evidence_requirement_id"))
                for row in snapshot["rule_application_evidence_links"]
            ],
            "industry_density_assessments": [
                (
                    row.get("density_assessment_id"), row.get("industry_code"),
                    row.get("tier"), row.get("density_status"), row.get("row_version"),
                )
                for row in snapshot["industry_density_assessments"]
            ],
            "master": {
                table: [
                    (row.get(next(iter(row))), row.get("row_version"), row.get("updated_at"))
                    for row in rows
                ]
                for table, rows in snapshot["master"].items()
            },
            "extractor": {
                "name": getattr(self.claim_extractor, "name", type(self.claim_extractor).__name__),
                "version": getattr(self.claim_extractor, "version", None),
            },
            "simulation": simulation,
        }
        return hashlib.sha256(_json(material).encode("utf-8")).hexdigest()

    def _persist(
        self,
        *,
        run_id: str,
        case: dict[str, Any],
        snapshot: dict[str, Any],
        claim_result: Any,
        conflicts: list[ConflictCandidate],
        verifications: list[VerificationCandidate],
        clues: list[RiskClue],
        axes: list[AxisAssessment],
        source_coverages: list[RiskSourceCoverage],
        simulation: bool,
        actor: str,
    ) -> int:
        case_id = str(case["case_id"])
        origin = DataOrigin.LEGACY_DEMO if simulation else DataOrigin.SYSTEM_DERIVED
        task_ids: set[str] = set()
        conflict_ids: dict[str, str] = {}
        verification_ids: dict[str, str] = {}
        finding_ids: dict[str, str] = {}
        with self.repository.transaction() as uow:
            if not simulation:
                for table in ("claim_signals", "conflict_logs", "verification_items", "risk_findings"):
                    for row in uow.find(table, filters={"case_id": case_id, "is_current": 1}):
                        uow.update(
                            table,
                            str(row[{"claim_signals": "claim_id", "conflict_logs": "conflict_id", "verification_items": "verification_id", "risk_findings": "finding_id"}[table]]),
                            {"is_current": 0},
                            expected_version=row["row_version"],
                        )

            for document in snapshot["documents"]:
                uow.insert("analysis_run_documents", {
                    "analysis_run_id": run_id,
                    "doc_id": document["doc_id"],
                    "input_sha256": document.get("sha256"),
                }, on_conflict="ignore")

            for index, claim in enumerate(claim_result.claims):
                claim_id = stable_id("claim", f"{run_id}:{index}:{claim.evidence_id}:{claim.text}")
                uow.add(ClaimSignal(
                    claim_id=claim_id,
                    case_id=case_id,
                    analysis_run_id=run_id,
                    evidence_id=claim.evidence_id,
                    model_run_id=claim.model_run_id,
                    claim_text=claim.text,
                    claim_type=claim.claim_type,
                    green_relevance=claim.green_relevance,
                    evidence_strength=claim.evidence_strength,
                    support_status=claim.support_status,
                    extraction_method=claim.extraction_method,
                    is_model_output=claim.is_model_output and not simulation,
                    requires_human_confirmation=True,
                    record_origin=origin,
                    is_current=not simulation,
                ))

            for conflict in conflicts:
                conflict_id = stable_id("conflict", f"{run_id}:{conflict.semantic_key}")
                conflict_ids[conflict.semantic_key] = conflict_id
                uow.add(ConflictLog(
                    conflict_id=conflict_id,
                    case_id=case_id,
                    conflict_type=conflict.conflict_type,
                    field_name=conflict.field_name,
                    comparability_status="comparable_same_scope_period_unit",
                    fact_a_id=conflict.fact_a_id,
                    fact_b_id=conflict.fact_b_id,
                    evidence_a_id=conflict.evidence_a_id,
                    evidence_b_id=conflict.evidence_b_id,
                    raw_value_a=conflict.raw_value_a,
                    raw_value_b=conflict.raw_value_b,
                    normalized_value_a=conflict.normalized_value_a,
                    normalized_value_b=conflict.normalized_value_b,
                    difference_value=conflict.difference_value,
                    difference_unit=conflict.difference_unit,
                    ratio_denominator="smaller_absolute_value",
                    denominator_value=conflict.denominator_value,
                    difference_ratio=conflict.difference_ratio,
                    comparison_method=conflict.comparison_method,
                    risk_level=conflict.risk_level,
                    status="pending_human_review",
                    record_origin=origin,
                    analysis_run_id=run_id,
                    is_current=not simulation,
                ))

            for verification in verifications:
                verification_id = stable_id("verify", f"{run_id}:{verification.semantic_key}")
                verification_ids[verification.semantic_key] = verification_id
                uow.add(VerificationItem(
                    verification_id=verification_id,
                    case_id=case_id,
                    risk_dimension=verification.dimension.value,
                    rule_version_id=verification.rule_version_id,
                    master_rule_type=verification.master_rule_type,
                    master_rule_id=verification.master_rule_id,
                    source_manifest_id=verification.source_manifest_id,
                    phase36_item_id=verification.phase36_item_id,
                    application_mapping_id=verification.application_mapping_id,
                    rule_module=verification.module,
                    source_locator=verification.source_locator,
                    prescribed_task_type=verification.prescribed_task_type,
                    why_verify=verification.why_verify,
                    customer_manager_focus=verification.customer_manager_focus,
                    is_mock=verification.is_mock,
                    requirement_text=verification.requirement_text,
                    status=VerificationStatus(verification.status),
                    next_action=verification.next_action,
                    applicability_reason=verification.applicability_reason,
                    record_origin=origin,
                    analysis_run_id=run_id,
                    is_current=not simulation,
                ))
                for fact_id in verification.fact_ids:
                    uow.insert("verification_fact_links", {
                        "verification_id": verification_id,
                        "fact_id": fact_id,
                        "link_role": "evaluated_fact",
                    }, on_conflict="ignore")
                for evidence_id in verification.evidence_ids:
                    uow.insert("verification_evidence_links", {
                        "verification_id": verification_id,
                        "evidence_id": evidence_id,
                        "link_role": "supporting_evidence",
                    }, on_conflict="ignore")
                valid_requirement_ids = {
                    str(row["evidence_requirement_id"])
                    for row in snapshot["master"]["evidence_requirements"]
                    if row.get("evidence_requirement_id")
                }
                for requirement_id in verification.required_evidence_ids:
                    if requirement_id not in valid_requirement_ids:
                        continue
                    now = utc_now()
                    uow.insert("verification_requirement_links", {
                        "verification_id": verification_id,
                        "evidence_requirement_id": requirement_id,
                        # Candidate document/text matching only supports assisted
                        # reading; it cannot close a requirement automatically.
                        "requirement_status": "pending",
                        "matched_evidence_id": None,
                        "created_at": now,
                        "updated_at": now,
                        "row_version": 1,
                    }, on_conflict="ignore")

            for clue in clues:
                finding_id = stable_id("risk", f"{run_id}:{clue.semantic_key}")
                finding_ids[clue.semantic_key] = finding_id
                uow.add(RiskFinding(
                    finding_id=finding_id,
                    case_id=case_id,
                    risk_dimension=clue.dimension.value,
                    trigger_type=clue.trigger_type,
                    risk_level=clue.level,
                    review_priority=clue.priority,
                    finding_text=clue.text,
                    coverage_status=clue.coverage_status.value,
                    handling_status="pending_human_confirmation",
                    record_origin=origin,
                    is_model_result=clue.is_model_result and not simulation,
                    eligible_for_decision=False,
                    legacy_note=("模拟输入，不作为真实模型或业务结果。" if simulation else None),
                    analysis_run_id=run_id,
                    provenance_kind=clue.provenance_kind,
                    model_run_id=(None if simulation else clue.model_run_id),
                    inference_policy_version=clue.inference_policy_version,
                    is_current=not simulation,
                ))
                for evidence_id in clue.evidence_ids:
                    uow.insert("risk_evidence_links", {
                        "finding_id": finding_id,
                        "evidence_id": evidence_id,
                        "link_role": "trigger_evidence",
                    }, on_conflict="ignore")
                for fact_id in clue.fact_ids:
                    uow.insert("risk_fact_links", {
                        "finding_id": finding_id,
                        "fact_id": fact_id,
                        "link_role": "trigger_fact",
                    }, on_conflict="ignore")
                for rule_id in clue.rule_version_ids:
                    uow.insert("risk_rule_links", {
                        "finding_id": finding_id,
                        "rule_version_id": rule_id,
                        "link_role": "trigger_rule",
                    }, on_conflict="ignore")

            for conflict in ([] if simulation else conflicts):
                conflict_id = conflict_ids[conflict.semantic_key]
                task_id = self._ensure_task(
                    uow,
                    case_id=case_id,
                    run_id=run_id,
                    task_type="conflict_review",
                    semantic_key=conflict.semantic_key,
                    reason=f"核实跨文件字段“{conflict.field_name}”差异",
                    related_type="conflict",
                    related_id=conflict_id,
                    closure="核对有效版本、变更文件和口径后，由复核人确认。",
                )
                task_ids.add(task_id)
                uow.insert("task_conflict_links", {
                    "task_id": task_id, "conflict_id": conflict_id, "link_role": "trigger"
                }, on_conflict="ignore")

            verification_task_groups: dict[str, list[VerificationCandidate]] = {}
            for verification in ([] if simulation else verifications):
                if verification.status in {
                    "satisfied", "not_applicable", "attribute_only"
                }:
                    continue
                if verification.is_mock and verification.status != "pending_verification":
                    raise ValueError("示例规则支撑的核验项只能处于待核实状态")
                if verification.module in CONTEXT_MODULES:
                    # Context rows feed assisted reading and classification,
                    # never a duplicate operational task.
                    continue
                group_key = verification.task_bundle_key or verification.semantic_key
                verification_task_groups.setdefault(group_key, []).append(verification)

            for group_key, members in verification_task_groups.items():
                first = members[0]
                task_type = PRESCRIBED_TASK_TYPES.get(
                    str(first.prescribed_task_type or ""),
                    str(first.prescribed_task_type or ""),
                ) or (
                    "supplement_request"
                    if first.status == "pending_verification"
                    else "verification_review"
                )
                verification_id = verification_ids[first.semantic_key]
                missing_count = len({
                    requirement_id
                    for member in members
                    for requirement_id in member.missing_evidence_ids
                })
                reason = first.next_action or first.applicability_reason
                if len(members) > 1:
                    reason = f"合并处理 {len(members)} 项核验要求；{reason}"
                if missing_count:
                    reason = f"{reason} 当前共有 {missing_count} 项证据要求待核实。"
                task_id = self._ensure_task(
                    uow,
                    case_id=case_id,
                    run_id=run_id,
                    task_type=task_type,
                    semantic_key=group_key,
                    reason=reason,
                    related_type="verification_bundle",
                    related_id=verification_id,
                    closure="补齐证据、完成规则适用性复核并提交审核后，由复核人确认。",
                )
                task_ids.add(task_id)
                for member in members:
                    uow.insert("task_verification_links", {
                        "task_id": task_id,
                        "verification_id": verification_ids[member.semantic_key],
                        "link_role": "trigger",
                    }, on_conflict="ignore")

            for clue in ([] if simulation else clues):
                if clue.trigger_type.startswith("cross_document") or clue.trigger_type.startswith("rule_"):
                    continue
                finding_id = finding_ids[clue.semantic_key]
                task_id = self._ensure_task(
                    uow,
                    case_id=case_id,
                    run_id=run_id,
                    task_type="risk_clue_review",
                    semantic_key=clue.semantic_key,
                    reason=clue.text,
                    related_type="risk",
                    related_id=finding_id,
                    closure="完成原文、项目边界和实质证据复核后，由复核人确认。",
                )
                task_ids.add(task_id)
                uow.insert("task_risk_links", {
                    "task_id": task_id, "finding_id": finding_id, "link_role": "trigger"
                }, on_conflict="ignore")

            coverage = {
                "axes": [
                    {
                        "dimension": axis.dimension.value,
                        "coverage_status": axis.coverage_status.value,
                        "attention_score": axis.attention_score,
                        "risk_level": axis.risk_level.value,
                        "finding_count": axis.finding_count,
                        "summary": axis.summary,
                    }
                    for axis in axes
                ],
                "counts": {
                    "claims": len(claim_result.claims),
                    "conflicts": len(conflicts),
                    "verifications": len(verifications),
                    "tasks": len(task_ids),
                },
                "claim_extraction": {
                    "coverage_status": claim_result.coverage_status.value,
                    "message": claim_result.message,
                },
                "risk_sources": [
                    {
                        "source_type": item.source_type.value,
                        "coverage_status": item.coverage_status.value,
                        "message": item.message,
                        "input_count": item.input_count,
                        "finding_count": item.finding_count,
                        "model_run_id": item.model_run_id,
                    }
                    for item in source_coverages
                ],
                "score_definition": "关注指数只用于复核排序，非违约、合规、漂绿或批贷概率。",
                "human_confirmation_required": True,
            }
            current_run = uow.require("analysis_runs", run_id)
            previous_runs = uow.find(
                "analysis_runs", filters={"case_id": case_id, "status": "completed"}
            )
            next_revision = max(
                [int(item.get("output_revision") or 0) for item in previous_runs] + [0]
            ) + 1
            uow.update(
                "analysis_runs",
                run_id,
                {
                    "status": "completed",
                    "model_run_id": claim_result.model_run_id,
                    "output_revision": next_revision,
                    "coverage_json": _json(coverage),
                    "finished_at": utc_now(),
                },
                expected_version=current_run["row_version"],
            )
            uow.add(AuditLog(
                case_id=case_id,
                action="case_intelligence_completed",
                actor=actor,
                actor_role=RoleType.SYSTEM if actor == "system" else None,
                model_run_id=claim_result.model_run_id,
                details_json={
                    "analysis_run_id": run_id,
                    "simulation": simulation,
                    "counts": coverage["counts"],
                    "automatic_credit_decision": False,
                },
            ))
        return len(task_ids)

    @staticmethod
    def _ensure_task(
        uow: Any,
        *,
        case_id: str,
        run_id: str,
        task_type: str,
        semantic_key: str,
        reason: str,
        related_type: str,
        related_id: str,
        closure: str,
    ) -> str:
        base_id = stable_id("task", f"{case_id}:{task_type}:{semantic_key}")
        existing = uow.get("tasks", base_id)
        task_id = base_id
        if existing and existing["status"] == TaskStatus.CLOSED.value:
            task_id = stable_id("task", f"{case_id}:{task_type}:{semantic_key}:{run_id}")
            existing = uow.get("tasks", task_id)
        if existing:
            uow.update(
                "tasks",
                task_id,
                {
                    "trigger_reason": reason,
                    "related_entity_type": related_type,
                    "related_entity_id": related_id,
                    "analysis_run_id": run_id,
                },
                expected_version=existing["row_version"],
            )
        else:
            uow.add(Task(
                task_id=task_id,
                case_id=case_id,
                task_type=task_type,
                trigger_reason=reason,
                related_entity_type=related_type,
                related_entity_id=related_id,
                status=TaskStatus.PENDING,
                closure_condition=closure,
                analysis_run_id=run_id,
            ))
        return task_id

    @staticmethod
    def _result_from_run(run: dict[str, Any], *, reused: bool) -> AssessmentResult:
        coverage = _json_object(run.get("coverage_json"))
        axes = tuple(
            AxisAssessment(
                dimension=RiskDimension(item["dimension"]),
                coverage_status=CoverageStatus(item["coverage_status"]),
                attention_score=item.get("attention_score"),
                risk_level=RiskLevel(item.get("risk_level") or "unknown"),
                finding_count=int(item.get("finding_count") or 0),
                summary=str(item.get("summary") or ""),
            )
            for item in coverage.get("axes", [])
        )
        counts = coverage.get("counts") or {}
        return AssessmentResult(
            analysis_run_id=str(run["analysis_run_id"]),
            case_id=str(run["case_id"]),
            reused=reused,
            simulation=bool(run.get("is_simulation")),
            axes=axes,
            conflict_count=int(counts.get("conflicts") or 0),
            verification_count=int(counts.get("verifications") or 0),
            claim_count=int(counts.get("claims") or 0),
            task_count=int(counts.get("tasks") or 0),
            model_run_id=run.get("model_run_id"),
        )
