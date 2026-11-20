"""Evidence-led read model for the redesigned case workspace.

The service computes review-priority scores from persisted verification states.
It never turns a score into a credit decision, a green-compliance probability,
or a greenwashing probability.  Missing applicable items remain unscored.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote

from green_model.agent.storage import SQLiteRepository


RISK_DIMENSIONS: tuple[tuple[str, str, str], ...] = (
    (
        "claim_credibility",
        "绿色主张可信性",
        "核对企业或项目的绿色表述是否能落到具体活动、项目事实和可定位证据。",
    ),
    (
        "project_boundary_and_use",
        "项目边界与融资用途",
        "核对融资对象、建设范围、资金用途和支付对象是否指向同一项目。",
    ),
    (
        "technical_and_compliance",
        "行业技术与合规落实",
        "核对行业技术标准、依法适用手续和项目阶段要求是否有证据支持。",
    ),
    (
        "implementation_and_funds",
        "项目实施与资金执行",
        "核对建设进度、设备投入、合同和资金支付是否与申报安排一致。",
    ),
    (
        "performance_and_continuing_compliance",
        "绩效兑现与持续合规",
        "核对基准、目标、实际绩效和合规事件是否同口径、可持续跟踪。",
    ),
)

DIMENSION_ALIASES = {
    "project_boundary": "project_boundary_and_use",
    "industry_compliance": "technical_and_compliance",
    "execution_funds": "implementation_and_funds",
    "performance_compliance": "performance_and_continuing_compliance",
    "industry_policy": "technical_and_compliance",
    "green_substance": "project_boundary_and_use",
    "compliance": "technical_and_compliance",
    "data_evidence": "project_boundary_and_use",
    "postloan": "performance_and_continuing_compliance",
}


def _canonical_dimension(value: Any) -> str | None:
    code = str(value or "").strip()
    return DIMENSION_ALIASES.get(code, code or None)

STATUS_POINTS = {
    "satisfied": 10,
    "attribute_only": 25,
    "pending_verification": 55,
    "cannot_determine": 65,
    "evidence_conflict": 80,
    "not_satisfied": 100,
}

STATUS_LABELS = {
    "satisfied": "已证明",
    "attribute_only": "属性说明",
    "pending_verification": "待核实",
    "cannot_determine": "无法判断",
    "evidence_conflict": "证据冲突",
    "not_satisfied": "不满足",
    "not_applicable": "不适用",
}

INDUSTRY_TEAMS = (
    (("风电", "光伏", "储能", "新能源", "电力"), "新能源行业组"),
    (("钢铁", "冶炼"), "钢铁与装备行业组"),
    (("水泥", "建材"), "建材行业组"),
    (("新材料", "化工"), "新材料与化工行业组"),
)


def _manager_team(industry: str | None) -> str:
    text = industry or ""
    for keys, team in INDUSTRY_TEAMS:
        if any(key in text for key in keys):
            return team
    return "综合行业组（待行业确认）"


def _level(score: int | None) -> tuple[str, str]:
    if score is None:
        return "待计算", "unknown"
    if score <= 25:
        return "低关注", "low"
    if score <= 50:
        return "一般关注", "medium"
    if score <= 75:
        return "重点关注", "high"
    return "优先复核", "critical"


@dataclass(frozen=True)
class RiskAxis:
    code: str
    label: str
    definition: str
    score: int | None
    level: str
    tone: str
    applicable_count: int
    unresolved_count: int
    basis: str
    items: list[dict[str, Any]]
    score_source: str


class CaseIntelligence:
    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def build(self, case_id: str) -> dict[str, Any] | None:
        case = self.repository.get("cases", case_id)
        if case is None:
            return None
        documents = self.repository.find(
            "documents", filters={"case_id": case_id}, order_by="-updated_at"
        )
        extraction_runs = self.repository.find(
            "extraction_runs", filters={"case_id": case_id}, order_by="-created_at"
        )
        facts = self.repository.find(
            "project_facts", filters={"case_id": case_id}, order_by="created_at"
        )
        evidence = self.repository.find(
            "evidence_snippets", filters={"case_id": case_id}, order_by="created_at"
        )
        verifications = self.repository.find(
            "verification_items", filters={"case_id": case_id, "is_current": 1}, order_by="created_at"
        )
        findings = self.repository.find(
            "risk_findings", filters={"case_id": case_id, "is_current": 1}, order_by="created_at"
        )
        conflicts = self.repository.find(
            "conflict_logs", filters={"case_id": case_id, "is_current": 1}, order_by="created_at"
        )
        tasks = self.repository.find(
            "tasks", filters={"case_id": case_id}, order_by="-updated_at"
        )
        audits = self.repository.find(
            "audit_logs", filters={"case_id": case_id}, order_by="-occurred_at"
        )
        human_decisions = self.repository.find(
            "human_decisions", filters={"case_id": case_id}, order_by="-decided_at"
        )
        report_snapshots = self.repository.find(
            "report_snapshots", filters={"case_id": case_id}, order_by="-snapshot_revision"
        )
        indicators = self.repository.find(
            "bta_indicators", filters={"case_id": case_id}, order_by="created_at"
        )
        model_runs = self.repository.find(
            "model_runs", filters={"case_id": case_id}, order_by="-created_at"
        )
        rules = {row["rule_version_id"]: row for row in self.repository.find("rule_versions")}
        docs = {row["doc_id"]: row for row in documents}
        sources = {row["source_id"]: row for row in self.repository.find("source_records")}
        source_manifest = {
            row["source_id"]: row for row in self.repository.find("source_manifest")
        }
        facts_by_id = {str(row["fact_id"]): row for row in facts}
        evidence_by_id = {str(row["evidence_id"]): row for row in evidence}
        verification_ids = {str(row["verification_id"]) for row in verifications}
        verification_fact_links = [
            row for row in self.repository.find("verification_fact_links")
            if str(row.get("verification_id")) in verification_ids
        ]
        verification_evidence_links = [
            row for row in self.repository.find("verification_evidence_links")
            if str(row.get("verification_id")) in verification_ids
        ]
        verification_requirement_links = [
            row for row in self.repository.find("verification_requirement_links")
            if str(row.get("verification_id")) in verification_ids
        ]
        task_verification_links = [
            row for row in self.repository.find("task_verification_links")
            if str(row.get("verification_id")) in verification_ids
        ]
        requirements = {
            str(row["evidence_requirement_id"]): row
            for row in self.repository.find("evidence_requirements")
        }

        latest_run_by_doc: dict[str, dict[str, Any]] = {}
        latest_completed_by_doc: dict[str, dict[str, Any]] = {}
        for run in extraction_runs:
            doc_key = str(run.get("doc_id"))
            latest_run_by_doc.setdefault(doc_key, run)
            if run.get("status") == "completed":
                latest_completed_by_doc.setdefault(doc_key, run)
        active_run_ids = {
            str(run.get("extraction_run_id"))
            for run in latest_completed_by_doc.values()
        }
        facts = [
            fact for fact in facts
            if not fact.get("extraction_run_id")
            or str(fact.get("extraction_run_id")) in active_run_ids
        ]
        evidence = [
            item for item in evidence
            if not item.get("extraction_run_id")
            or str(item.get("extraction_run_id")) in active_run_ids
        ]
        facts_by_id = {str(row["fact_id"]): row for row in facts}
        evidence_by_id = {str(row["evidence_id"]): row for row in evidence}
        document_view = [
            {**document, "latest_parse_run": latest_run_by_doc.get(str(document.get("doc_id")))}
            for document in documents
            if document.get("record_origin") not in {"legacy_json", "legacy_demo"}
        ]
        visible_doc_ids = {str(item.get("doc_id")) for item in document_view}

        evidence_view = []
        for item in evidence:
            doc_id = item.get("doc_id")
            if doc_id and str(doc_id) not in visible_doc_ids:
                continue
            if not doc_id and item.get("record_origin") in {"legacy_json", "legacy_demo"}:
                continue
            document = docs.get(item.get("doc_id"))
            source = sources.get(item.get("source_id") or (document or {}).get("source_id"))
            evidence_view.append(
                {
                    **item,
                    "file_name": (document or {}).get("file_name") or (source or {}).get("title") or "来源待确认",
                    "source_title": (source or {}).get("title"),
                    "source_url": (source or {}).get("source_url"),
                }
            )

        verification_view = []
        for item in verifications:
            if item.get("risk_dimension") == "legacy_condition":
                continue
            rule = rules.get(item.get("rule_version_id")) or {}
            verification_id = str(item["verification_id"])
            linked_facts = [
                facts_by_id[str(link["fact_id"])]
                for link in verification_fact_links
                if str(link.get("verification_id")) == verification_id
                and str(link.get("fact_id")) in facts_by_id
            ]
            linked_evidence = [
                evidence_by_id[str(link["evidence_id"])]
                for link in verification_evidence_links
                if str(link.get("verification_id")) == verification_id
                and str(link.get("evidence_id")) in evidence_by_id
            ]
            requirement_links = [
                link for link in verification_requirement_links
                if str(link.get("verification_id")) == verification_id
            ]
            linked_task_ids = [
                str(link.get("task_id"))
                for link in task_verification_links
                if str(link.get("verification_id")) == verification_id
                and link.get("task_id")
            ]
            required_evidence = []
            for link in requirement_links:
                definition = requirements.get(str(link.get("evidence_requirement_id"))) or {}
                required_evidence.append({
                    "label": definition.get("evidence_object")
                    or definition.get("requirement_text")
                    or "证据要求待补充",
                    "requirement": definition.get("requirement_text"),
                    "acceptable": definition.get("acceptable_evidence"),
                    "status": link.get("requirement_status") or "pending",
                })
            manifest = source_manifest.get(item.get("source_manifest_id")) or {}
            is_mock = bool(item.get("is_mock"))
            status_label = (
                "待核实" if is_mock else
                STATUS_LABELS.get(item.get("status"), item.get("status") or "未核验")
            )
            evidence_locations = []
            for linked in linked_evidence:
                document = docs.get(linked.get("doc_id")) or {}
                evidence_locations.append({
                    "evidence_id": linked.get("evidence_id"),
                    "file_name": document.get("file_name") or "项目材料",
                    "page_number": linked.get("page_number"),
                    "excerpt": linked.get("raw_excerpt"),
                })
            verification_view.append(
                {
                    **item,
                    "risk_dimension": _canonical_dimension(item.get("risk_dimension")),
                    "status_label": status_label,
                    "rule_id": rule.get("rule_id"),
                    "rule_name": rule.get("rule_name"),
                    "rule_version": rule.get("version_label"),
                    "rule_requirement": rule.get("requirement_text"),
                    "evidence_requirement": rule.get("evidence_requirement"),
                    "is_bank_internal": bool(rule.get("is_bank_internal")),
                    "is_mock": is_mock,
                    "mock_label": "示例规则" if is_mock else None,
                    "source_title": (
                        "示例规则（非正式依据）" if is_mock
                        else manifest.get("source_name")
                    ),
                    "source_url": (
                        manifest.get("source_url")
                        if str(manifest.get("source_url") or "").startswith(("http://", "https://"))
                        else None
                    ),
                    "fact_summary": "；".join(
                        str(row.get("raw_value") or row.get("normalized_value") or "")
                        for row in linked_facts
                        if row.get("raw_value") or row.get("normalized_value")
                    ),
                    "evidence_locations": evidence_locations,
                    "required_evidence": required_evidence,
                    "missing_evidence_count": sum(
                        1 for row in required_evidence if row["status"] == "pending"
                    ),
                    # Keep the compact coverage view aligned with the actual
                    # many-to-many task link table.  Earlier versions looked
                    # for a non-existent verification_items.task_id column,
                    # which made task coverage appear as zero even when the
                    # closed-loop tasks were correctly persisted.
                    "task_id": linked_task_ids[0] if linked_task_ids else None,
                    "task_ids": linked_task_ids,
                }
            )

        risk_axes = self._risk_axes(case, verification_view, findings)
        scored = [axis.score for axis in risk_axes if axis.score is not None]
        overall_score = max(scored) if scored else None
        overall_level, overall_tone = _level(overall_score)
        unresolved = sum(axis.unresolved_count for axis in risk_axes)
        open_tasks = [task for task in tasks if task.get("status") != "closed"]
        open_conflicts = [
            item
            for item in conflicts
            if str(item.get("status") or "").lower() not in {"closed", "resolved", "dismissed"}
        ]

        stage_basis = self._stage_basis(case, facts)
        enterprise_stage_basis = self._enterprise_stage_basis(case, facts)
        project_stage_basis = self._project_stage_basis(case, facts)
        observations = self._bta_observations(indicators)
        industry_text = " ".join(str(case.get(key) or "") for key in (
            "primary_industry", "project_activity"
        ))
        industry_match = re.search(r"(?<!\d)(\d{4})(?!\d)", industry_text)
        industry_code = industry_match.group(1) if industry_match else None
        term_cards = self.repository.find(
            "term_cards", filters={"industry_code": industry_code}
        ) if industry_code else []
        postloan_evaluations = self.repository.find(
            "postloan_evaluations", filters={"case_id": case_id, "is_current": 1},
            order_by="created_at",
        )
        conflict_view = []
        for conflict in conflicts:
            left = evidence_by_id.get(str(conflict.get("evidence_id_a") or "")) or {}
            right = evidence_by_id.get(str(conflict.get("evidence_id_b") or "")) or {}
            left_doc = docs.get(left.get("doc_id")) or {}
            right_doc = docs.get(right.get("doc_id")) or {}
            conflict_view.append({
                **conflict,
                "evidence_a": {
                    "file_name": left_doc.get("file_name") or "材料 A",
                    "page_number": left.get("page_number"),
                    "excerpt": left.get("raw_excerpt"),
                },
                "evidence_b": {
                    "file_name": right_doc.get("file_name") or "材料 B",
                    "page_number": right.get("page_number"),
                    "excerpt": right.get("raw_excerpt"),
                },
            })
        task_funnel = Counter(str(row.get("status") or "pending") for row in tasks)
        evidence_distribution = Counter(
            str(row.get("file_name") or "未命名材料") for row in evidence_view
        )
        verification_coverage = {
            "rules": len(verification_view),
            "facts": sum(1 for row in verification_view if row.get("fact_summary")),
            "evidence": sum(1 for row in verification_view if row.get("evidence_locations")),
            "tasks": sum(1 for row in verification_view if row.get("task_id")),
        }
        workflow = self._workflow(case, documents, verification_view, open_tasks)
        return {
            "case": case,
            "workflow": workflow,
            "classification": {
                "industry": case.get("primary_industry") or "待行业定标",
                "project_activity": case.get("project_activity") or "待从项目材料确认",
                "industry_basis": self._industry_basis(case, facts, verification_view),
                "manager": case.get("assignee") or "待分配",
                "recommended_team": _manager_team(case.get("primary_industry")),
                "enterprise_stage": case.get("enterprise_stage") or "待判断",
                "project_stage": case.get("project_stage") or "待判断",
                "loan_stage": case.get("loan_stage") or "贷前调查",
                "stage_basis": stage_basis,
                "enterprise_stage_basis": enterprise_stage_basis,
                "project_stage_basis": project_stage_basis,
                "bank_rule_state": "银行内部规则未接入，无法判断",
            },
            "risk_axes": risk_axes,
            "risk_findings": [
                {**row, "risk_dimension": _canonical_dimension(row.get("risk_dimension"))}
                for row in findings
            ],
            "overall_score": overall_score,
            "overall_level": overall_level,
            "overall_tone": overall_tone,
            "risk_standard": (
                "复核优先级按核验状态映射：已证明10、属性说明25、待核实55、"
                "无法判断65、证据冲突80、不满足100；不适用项不计分。"
            ),
            "risk_boundary": "分值用于安排人工复核顺序，不是违约概率、合规概率、绿色概率或授信结论。",
            "verification_items": verification_view,
            "documents": document_view,
            "extraction_runs": extraction_runs,
            "facts": facts,
            "evidence": evidence_view,
            "conflicts": conflict_view,
            "tasks": tasks,
            "open_tasks": open_tasks,
            "open_conflicts": open_conflicts,
            "audits": audits,
            "human_decisions": human_decisions,
            "report_snapshots": report_snapshots,
            "bta_indicators": indicators,
            "bta_observations": observations,
            "postloan_evaluations": postloan_evaluations,
            "term_cards": term_cards,
            "task_funnel": dict(task_funnel),
            "evidence_distribution": dict(evidence_distribution),
            "verification_coverage": verification_coverage,
            "model_runs": model_runs,
            "model_state": self._model_state(model_runs),
            "counts": {
                "documents": len(document_view),
                "evidence": len(evidence_view),
                "verification": len(verification_view),
                "unresolved": unresolved,
                "tasks": len(open_tasks),
                "conflicts": len(open_conflicts),
            },
            "is_legacy_demo": case.get("record_origin") == "legacy_demo",
        }

    @staticmethod
    def _model_state(model_runs: list[dict[str, Any]]) -> dict[str, str]:
        if not model_runs:
            return {
                "label": "未运行",
                "detail": "尚未对本案已解析文本运行企业披露筛查模型。",
                "tone": "muted",
            }
        run = model_runs[0]
        status = run.get("status")
        if status == "completed" and run.get("is_real_model_result"):
            return {
                "label": "真实模型已运行",
                "detail": "结果仅用于企业披露阅读排序，不进入项目核验结论。",
                "tone": "ok",
            }
        if status == "completed" and not run.get("is_real_model_result"):
            return {
                "label": "离线演示结果",
                "detail": str(
                    run.get("degradation_reason")
                    or "合成披露文本的预计算结果，仅用于展示风险线索和人工复核流程。"
                ),
                "tone": "muted",
            }
        if status == "not_run":
            return {
                "label": "未运行",
                "detail": str(run.get("degradation_reason") or "模型依赖或输入尚未就绪。"),
                "tone": "muted",
            }
        return {
            "label": "运行失败",
            "detail": str(run.get("degradation_reason") or "请检查模型依赖和本地资产。"),
            "tone": "danger",
        }

    def _risk_axes(
        self,
        case: dict[str, Any],
        verifications: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> list[RiskAxis]:
        findings_by_dimension: dict[str, list[dict[str, Any]]] = {}
        for item in findings:
            dimension = _canonical_dimension(item.get("risk_dimension"))
            if dimension:
                findings_by_dimension.setdefault(dimension, []).append(item)
        axes: list[RiskAxis] = []
        for code, label, definition in RISK_DIMENSIONS:
            items = [item for item in verifications if item.get("risk_dimension") == code]
            applicable = [item for item in items if item.get("status") != "not_applicable"]
            points = [
                STATUS_POINTS[item["status"]]
                for item in applicable
                if not item.get("is_mock") and item.get("status") in STATUS_POINTS
            ]
            dimension_findings = findings_by_dimension.get(code, [])
            points.extend(
                int(item["review_priority"])
                for item in dimension_findings
                if item.get("coverage_status") == "assessed"
                and item.get("review_priority") is not None
                and item.get("record_origin") != "legacy_demo"
            )
            score_source = "核验状态实时计算"
            score = round(sum(points) / len(points)) if points else None
            if score is None:
                score_source = "仅有示例规则或证据不足，保持待计算"
            level, tone = _level(score)
            unresolved_count = sum(
                1
                for item in applicable
                if item.get("status")
                in {"pending_verification", "cannot_determine", "evidence_conflict", "not_satisfied"}
            )
            basis_parts = []
            for finding in dimension_findings[:2]:
                if finding.get("finding_text"):
                    basis_parts.append(finding["finding_text"])
            if items:
                basis_parts.append(
                    "；".join(
                        f"{item.get('rule_name') or item.get('requirement_text') or '行业核验项'}：{item.get('status_label')}"
                        for item in items[:3]
                    )
                )
            axes.append(
                RiskAxis(
                    code=code,
                    label=label,
                    definition=definition,
                    score=score,
                    level=level,
                    tone=tone,
                    applicable_count=len(applicable),
                    unresolved_count=unresolved_count,
                    basis="；".join(basis_parts) or "无可计分核验项，保持待计算。",
                    items=items,
                    score_source=score_source,
                )
            )
        return axes

    @staticmethod
    def _fact_basis(facts: list[dict[str, Any]], categories: set[str]) -> str:
        values = [
            str(item.get("raw_value"))
            for item in facts
            if item.get("fact_category") in categories and item.get("raw_value")
        ]
        return "；".join(values[:3]) or "缺少可定位的行业与活动事实，需人工确认。"

    @classmethod
    def _industry_basis(
        cls,
        case: dict[str, Any],
        facts: list[dict[str, Any]],
        verifications: list[dict[str, Any]],
    ) -> str:
        direct = cls._fact_basis(facts, {"industry", "project_activity"})
        if not direct.startswith("缺少"):
            return direct
        for item in verifications:
            if item.get("rule_id") in {"G01", "G02", "H01", "J01"} and item.get("applicability_reason"):
                text = str(item["applicability_reason"])
                return text[:240] + ("…" if len(text) > 240 else "")
        if case.get("primary_industry") or case.get("project_activity"):
            return (
                f"当前案件字段：行业={case.get('primary_industry') or '待定'}，"
                f"项目活动={case.get('project_activity') or '待定'}；正式业务需回到材料原文复核。"
            )
        return direct

    @staticmethod
    def _stage_basis(case: dict[str, Any], facts: list[dict[str, Any]]) -> str:
        values = [
            str(item.get("match_basis") or item.get("raw_value"))
            for item in facts
            if item.get("fact_category") in {"enterprise_stage", "project_stage"}
            and (item.get("match_basis") or item.get("raw_value"))
        ]
        if values:
            return "；".join(values[:3])
        if case.get("enterprise_stage") or case.get("project_stage"):
            return "当前阶段来自历史案例人工结构化结果，正式业务需回到成立年限、产业化状态、项目手续和实施进度证据复核。"
        return "需补充成立年限、营收/产能、订单、项目手续和建设进度后判断。"

    @staticmethod
    def _enterprise_stage_basis(case: dict[str, Any], facts: list[dict[str, Any]]) -> str:
        values = [
            str(item.get("match_basis") or item.get("raw_value"))
            for item in facts
            if item.get("fact_category") == "enterprise_stage"
            and (item.get("match_basis") or item.get("raw_value"))
        ]
        if values:
            return "；".join(values[:3])
        if case.get("enterprise_stage"):
            return "当前值来自历史案件结构化字段；需用成立年限、营收或产能、订单与产业化状态材料复核。"
        return "尚无可定位依据；需补充成立年限、营收或产能、订单与产业化状态材料。"

    @staticmethod
    def _project_stage_basis(case: dict[str, Any], facts: list[dict[str, Any]]) -> str:
        values = [
            str(item.get("match_basis") or item.get("raw_value"))
            for item in facts
            if item.get("fact_category") == "project_stage"
            and (item.get("match_basis") or item.get("raw_value"))
        ]
        if values:
            return "；".join(values[:3])
        if case.get("project_stage"):
            return "当前值来自历史案件结构化字段；需用备案、审批、合同、开工或运行证据复核。"
        return "尚无可定位依据；需补充备案、审批、合同、开工或运行证据。"

    @staticmethod
    def _workflow(
        case: dict[str, Any],
        documents: list[dict[str, Any]],
        verifications: list[dict[str, Any]],
        open_tasks: list[dict[str, Any]],
    ) -> dict[str, str]:
        status = case.get("failed_from_status") if case.get("status") == "failed" else case.get("status")
        current_label = {
            "draft": "建立案件并补充材料",
            "ingesting": "材料入库",
            "parse_review": "材料解析复核",
            "classifying": "行业与阶段判断",
            "verifying": "风险识别与辅助核验",
            "action_required": "处理补件与核实事项",
            "human_review": "人工确认",
            "monitoring": "贷后持续监测",
            "closed": "案件已归档",
        }.get(status, "案件处理中")
        case_path = quote(str(case.get("case_id") or ""), safe="")
        if open_tasks:
            task = open_tasks[0]
            reason = str(task.get("trigger_reason") or "处理当前待办事项")
            return {
                "current_label": current_label,
                "next_action": reason[:76] + ("…" if len(reason) > 76 else ""),
                "action_label": "查看待办",
                "action_href": "/tasks",
            }
        unresolved = next(
            (
                item for item in verifications
                if item.get("status") in {"pending_verification", "cannot_determine", "evidence_conflict", "not_satisfied"}
            ),
            None,
        )
        if unresolved:
            action = str(unresolved.get("next_action") or "核对待核实指标与证据")
            return {
                "current_label": current_label,
                "next_action": action,
                "action_label": "进入辅助核验",
                "action_href": f"/cases/{case_path}/verification",
            }
        if not documents:
            return {
                "current_label": current_label,
                "next_action": "登记项目材料，建立可追溯证据台账",
                "action_label": "上传材料",
                "action_href": f"/cases/{case_path}/documents#supplement",
            }
        if not case.get("primary_industry") or not case.get("enterprise_stage") or not case.get("project_stage"):
            return {
                "current_label": current_label,
                "next_action": "补齐行业、企业阶段和项目阶段的判断依据",
                "action_label": "核对定标依据",
                "action_href": f"/cases/{case_path}/classification",
            }
        if status == "monitoring":
            return {
                "current_label": current_label,
                "next_action": "登记本期实际数据并核对偏离事项",
                "action_label": "进入贷后监测",
                "action_href": f"/cases/{case_path}/monitoring",
            }
        return {
            "current_label": current_label,
            "next_action": "复核行业规则、项目事实与证据对应关系",
            "action_label": "进入辅助核验",
            "action_href": f"/cases/{case_path}/verification",
        }

    def _bta_observations(self, indicators: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for indicator in indicators:
            observations = self.repository.find(
                "bta_observations",
                filters={"indicator_id": indicator["indicator_id"]},
                order_by="created_at",
            )
            values = {item["series_type"]: item for item in observations}
            result.append({"indicator": indicator, "series": values})
        return result


def task_status_counts(tasks: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("status") or "unknown") for item in tasks)
