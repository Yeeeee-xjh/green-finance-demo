"""Rule -> fact -> evidence verification without invented defaults."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from green_model.agent.domain.enums import RiskDimension, VerificationStatus

from .contracts import ConflictCandidate, VerificationCandidate


INDICATOR_FACT_ALIASES = (
    (("装机容量", "建设容量"), "installed_capacity"),
    (("发电量", "上网电量"), "annual_generation"),
    (("综合能耗", "能耗"), "energy_consumption"),
    (("碳排放", "二氧化碳排放"), "carbon_emission"),
    (("投资额", "总投资"), "investment_amount"),
    (("建设进度", "工程进度"), "construction_progress"),
)


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


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _semantic_key(*parts: Any) -> str:
    value = "|".join("" if item is None else str(item) for item in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dimension(rule: dict[str, Any], threshold: dict[str, Any]) -> RiskDimension:
    explicit = threshold.get("risk_dimension")
    if explicit:
        try:
            return RiskDimension(str(explicit))
        except ValueError:
            pass
    text = " ".join(str(rule.get(key) or "") for key in (
        "rule_name", "requirement_text", "evidence_requirement", "activity"
    ))
    if any(term in text for term in ("资金", "发票", "合同", "融资用途", "支付")):
        return RiskDimension.PROJECT_BOUNDARY_AND_USE
    if any(term in text for term in ("进度", "施工", "投产", "竣工")):
        return RiskDimension.IMPLEMENTATION_AND_FUNDS
    if any(term in text for term in ("贷后", "实际", "绩效", "排放量", "发电量")):
        return RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE
    return RiskDimension.TECHNICAL_AND_COMPLIANCE


def _evaluate(operator: str, actual: Decimal, expected: Decimal) -> bool | None:
    normalized = operator.strip().lower()
    operations = {
        "<=": lambda a, b: a <= b,
        "≤": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "≥": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "=": lambda a, b: a == b,
        "==": lambda a, b: a == b,
        "eq": lambda a, b: a == b,
    }
    operation = operations.get(normalized)
    return operation(actual, expected) if operation else None


def _industry_code(case: dict[str, Any]) -> str | None:
    for value in (case.get("primary_industry"), case.get("project_activity")):
        match = re.search(r"(?<!\d)(\d{4})(?!\d)", str(value or ""))
        if match:
            return match.group(1)
    return None


def _fact_category_for_indicator(name: str) -> str | None:
    for aliases, category in INDICATOR_FACT_ALIASES:
        if any(alias in name for alias in aliases):
            return category
    return None


def build_master_verification_candidates(
    *,
    case: dict[str, Any],
    master: dict[str, list[dict[str, Any]]],
    facts: Iterable[dict[str, Any]],
    documents: Iterable[dict[str, Any]],
    evidence: Iterable[dict[str, Any]],
    fact_evidence_links: Iterable[dict[str, Any]],
    conflicts: Iterable[ConflictCandidate],
) -> list[VerificationCandidate]:
    """Adapt the case-independent Phase 3.5 master into case verification rows."""

    industry_code = _industry_code(case)
    if not industry_code:
        return []
    sources = {row["source_id"]: row for row in master.get("source_manifest", [])}
    facts_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact.get("fact_category"):
            facts_by_category[str(fact["fact_category"])].append(fact)
    evidence_by_fact: dict[str, list[str]] = defaultdict(list)
    for link in fact_evidence_links:
        evidence_by_fact[str(link["fact_id"])].append(str(link["evidence_id"]))
    evidence_by_doc: dict[str, list[str]] = defaultdict(list)
    for row in evidence:
        if row.get("doc_id"):
            evidence_by_doc[str(row["doc_id"])].append(str(row["evidence_id"]))
    conflicted_facts = {
        value for item in conflicts for value in (item.fact_a_id, item.fact_b_id)
    }
    output: list[VerificationCandidate] = []

    indicators = {
        row["indicator_definition_id"]: row
        for row in master.get("indicator_definitions", [])
        if row.get("industry_code") == industry_code
    }
    for threshold in master.get("threshold_definitions", []):
        if threshold.get("industry_code") != industry_code:
            continue
        if threshold.get("scope_status") != "core" or threshold.get("threshold_kind") != "explicit_numeric":
            continue
        indicator = indicators.get(threshold.get("indicator_definition_id"))
        if not indicator or not indicator.get("formal_rule_eligible"):
            continue
        source = sources.get(threshold.get("source_id"))
        master_id = str(threshold["threshold_id"])
        requirement = str(threshold.get("threshold_text") or indicator.get("indicator_name"))
        common = {
            "semantic_key": _semantic_key("master_threshold", master_id),
            "rule_version_id": None,
            "dimension": RiskDimension.TECHNICAL_AND_COMPLIANCE,
            "requirement_text": requirement,
            "master_rule_type": "threshold",
            "master_rule_id": master_id,
            "source_manifest_id": threshold.get("source_id"),
        }
        if not source or source.get("availability_status") != "full_text_obtained" or not source.get("formal_rule_eligible"):
            output.append(VerificationCandidate(
                **common,
                status=VerificationStatus.CANNOT_DETERMINE.value,
                applicability_reason="阈值条目尚无可用的官方全文与页码链，不参与自动比较。",
                next_action="获取官方全文并核对适用范围、生效时间和页码。",
            ))
            continue
        category = _fact_category_for_indicator(str(indicator.get("indicator_name") or ""))
        if not category:
            output.append(VerificationCandidate(
                **common,
                status=VerificationStatus.PENDING_VERIFICATION.value,
                applicability_reason="规则阈值已结构化，但项目事实字段映射尚未配置。",
                next_action=f"人工核对指标“{indicator.get('indicator_name')}”的统计口径和原始证据。",
            ))
            continue
        matching = facts_by_category.get(category, [])
        if not matching:
            output.append(VerificationCandidate(
                **common,
                status=VerificationStatus.PENDING_VERIFICATION.value,
                applicability_reason=f"未找到指标“{indicator.get('indicator_name')}”对应的项目事实。",
                next_action=f"补充“{indicator.get('indicator_name')}”的原始数据、期间、单位和统计边界。",
            ))
            continue
        fact_ids = tuple(str(row["fact_id"]) for row in matching)
        evidence_ids = tuple(sorted({
            item for fact_id in fact_ids for item in evidence_by_fact.get(fact_id, [])
        }))
        if any(fact_id in conflicted_facts for fact_id in fact_ids):
            status = VerificationStatus.EVIDENCE_CONFLICT.value
            reason = "阈值对应的项目事实存在跨文件冲突。"
            action = "先核对冲突文件，再重新执行阈值比较。"
        else:
            expected = _decimal(threshold.get("threshold_value"))
            operator = str(threshold.get("operator") or "")
            expected_unit = threshold.get("unit")
            decisions: list[bool] = []
            for fact in matching:
                actual = _decimal(fact.get("normalized_value"))
                if actual is None or expected is None:
                    continue
                if expected_unit and fact.get("unit") and str(expected_unit) != str(fact.get("unit")):
                    continue
                decision = _evaluate(operator, actual, expected)
                if decision is not None:
                    decisions.append(decision)
            if not decisions:
                status = VerificationStatus.CANNOT_DETERMINE.value
                reason = "项目事实与阈值的单位、操作符或数值无法同口径比较。"
                action = "核对单位换算和适用口径，不使用无来源默认换算。"
            elif all(decisions):
                status = VerificationStatus.SATISFIED.value
                reason = "同口径项目事实满足官方明文数值阈值。"
                action = None
            else:
                status = VerificationStatus.NOT_SATISFIED.value
                reason = "至少一条同口径项目事实不满足官方明文数值阈值。"
                action = "人工核对原始证据、适用范围及有效的例外或调整依据。"
        output.append(VerificationCandidate(
            **common,
            status=status,
            applicability_reason=reason,
            next_action=action,
            fact_ids=fact_ids,
            evidence_ids=evidence_ids,
        ))

    def source_available(source_id: Any) -> bool:
        source = sources.get(source_id)
        return bool(
            source
            and source.get("availability_status") == "full_text_obtained"
            and source.get("formal_rule_eligible")
        )

    for table_key, id_key, rule_type, name_key, text_key in (
        ("permit_requirements", "permit_requirement_id", "permit", "permit_name", "requirement_text"),
        ("document_requirements", "document_requirement_id", "document", "document_name", "requirement_text"),
        ("evidence_requirements", "evidence_requirement_id", "evidence", "evidence_object", "requirement_text"),
    ):
        for item in master.get(table_key, []):
            if item.get("industry_code") != industry_code or item.get("scope_status") != "core":
                continue
            master_id = str(item[id_key])
            source_id = item.get("source_id")
            requirement = str(item.get(text_key) or item.get(name_key) or "")
            status = VerificationStatus.PENDING_VERIFICATION.value
            reason = "规则已匹配当前行业，需结合项目原件逐项核对。"
            action = f"核对“{item.get(name_key)}”及其页码、有效期和项目边界。"
            evidence_ids: tuple[str, ...] = ()
            if not source_available(source_id):
                status = VerificationStatus.CANNOT_DETERMINE.value
                reason = "当前条目的官方全文或形式核验未完成。"
                action = "获取并核对官方原文后重算。"
            elif rule_type == "document":
                target = str(item.get("document_name") or "").replace(" ", "")
                matched_docs = [
                    row for row in documents
                    if target and target in (
                        str(row.get("file_type") or "") + str(row.get("file_name") or "")
                    ).replace(" ", "")
                ]
                evidence_ids = tuple(sorted({
                    evidence_id
                    for row in matched_docs
                    for evidence_id in evidence_by_doc.get(str(row["doc_id"]), [])
                }))
                if matched_docs:
                    reason = "已发现同类材料，但文件存在不等于内容满足，仍需人工核对。"
                    action = "打开原文，核对发布主体、项目范围、版本、有效期与具体要求。"
            output.append(VerificationCandidate(
                semantic_key=_semantic_key("master", rule_type, master_id),
                rule_version_id=None,
                dimension=RiskDimension.TECHNICAL_AND_COMPLIANCE,
                requirement_text=requirement,
                status=status,
                applicability_reason=reason,
                next_action=action,
                evidence_ids=evidence_ids,
                master_rule_type=rule_type,
                master_rule_id=master_id,
                source_manifest_id=source_id,
            ))
    return output


def build_verification_candidates(
    *,
    case: dict[str, Any],
    rules: Iterable[dict[str, Any]],
    sources: Iterable[dict[str, Any]],
    facts: Iterable[dict[str, Any]],
    fact_evidence_links: Iterable[dict[str, Any]],
    conflicts: Iterable[ConflictCandidate],
) -> list[VerificationCandidate]:
    source_by_id = {row["source_id"]: row for row in sources}
    facts_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact.get("fact_category"):
            facts_by_category[str(fact["fact_category"])].append(fact)
    evidence_by_fact: dict[str, list[str]] = defaultdict(list)
    for link in fact_evidence_links:
        evidence_by_fact[str(link["fact_id"])].append(str(link["evidence_id"]))
    conflicted_fact_ids = {
        fact_id
        for conflict in conflicts
        for fact_id in (conflict.fact_a_id, conflict.fact_b_id)
    }

    industry = str(case.get("primary_industry") or "")
    project_stage = str(case.get("project_stage") or "")
    output: list[VerificationCandidate] = []
    for rule in rules:
        rule_industry = str(rule.get("industry") or "")
        if rule_industry and industry and rule_industry not in industry and industry not in rule_industry:
            continue
        status_text = str(rule.get("status") or "").lower()
        if status_text in {"superseded", "invalid", "inactive"}:
            continue
        applicable_stage = str(rule.get("applicable_stage") or "")
        if applicable_stage and project_stage and applicable_stage not in project_stage:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "not_applicable", project_stage),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=_dimension(rule, {}),
                requirement_text=str(rule.get("requirement_text") or rule.get("rule_name") or ""),
                status=VerificationStatus.NOT_APPLICABLE.value,
                applicability_reason=f"规则适用阶段为“{applicable_stage}”，当前项目阶段为“{project_stage}”。",
                next_action=None,
            ))
            continue

        source = source_by_id.get(rule.get("source_id"))
        threshold = _json_object(rule.get("threshold_json"))
        dimension = _dimension(rule, threshold)
        requirement = str(rule.get("requirement_text") or rule.get("rule_name") or "未命名规则")
        source_status = str((source or {}).get("status") or "")
        if rule.get("is_bank_internal") and source is None:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "bank_not_connected"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.CANNOT_DETERMINE.value,
                applicability_reason="银行内部规则未接入，系统不生成准入、额度或授信判断。",
                next_action="由经办人按当前有效行内制度核对。",
            ))
            continue
        if source is None:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "source_missing"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.CANNOT_DETERMINE.value,
                applicability_reason="规则条目未绑定可追溯原始来源，不用于判定满足。",
                next_action="补充官方原文、版本、页码和SHA-256后重新核验。",
            ))
            continue
        if source_status == "candidate":
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "source_candidate"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.CANNOT_DETERMINE.value,
                applicability_reason="规则来源仍处于候选状态，未完成版本和有效性核验。",
                next_action="完成来源核验后重新运行。",
            ))
            continue
        if source_status in {"unavailable", "invalid", "superseded", "public_channel_not_obtained"}:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "source_unavailable"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.CANNOT_DETERMINE.value,
                applicability_reason="规则原文当前不可用或已失效，不据此下结论。",
                next_action="获取当前有效的官方原文并完成版本复核。",
            ))
            continue

        metric = threshold.get("fact_category") or threshold.get("metric") or threshold.get("indicator")
        if not metric:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], "manual_evidence"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.PENDING_VERIFICATION.value,
                applicability_reason="规则已入库，但尚未配置可执行指标；不使用模型猜测默认值。",
                next_action=rule.get("evidence_requirement") or "按规则原文补充项目事实与证据。",
            ))
            continue

        matching_facts = facts_by_category.get(str(metric), [])
        if not matching_facts:
            output.append(VerificationCandidate(
                semantic_key=_semantic_key(rule["rule_version_id"], metric, "missing"),
                rule_version_id=str(rule["rule_version_id"]),
                dimension=dimension,
                requirement_text=requirement,
                status=VerificationStatus.PENDING_VERIFICATION.value,
                applicability_reason=f"未在当前材料中找到可核验事实“{metric}”。",
                next_action=rule.get("evidence_requirement") or f"补充能证明“{metric}”的原始材料。",
            ))
            continue

        fact_ids = tuple(str(row["fact_id"]) for row in matching_facts)
        evidence_ids = tuple(sorted({
            evidence_id for fact_id in fact_ids for evidence_id in evidence_by_fact.get(fact_id, [])
        }))
        if any(fact_id in conflicted_fact_ids for fact_id in fact_ids):
            status = VerificationStatus.EVIDENCE_CONFLICT.value
            reason = "对应项目事实存在跨文件冲突，在人工确认前不判定满足。"
            next_action = "核对变更批复、统计口径和有效版本。"
        else:
            expected = _decimal(threshold.get("value") if "value" in threshold else threshold.get("threshold_value"))
            operator = str(threshold.get("operator") or "")
            expected_unit = threshold.get("unit")
            evaluated: list[bool] = []
            incompatible_unit = False
            for fact in matching_facts:
                actual = _decimal(fact.get("normalized_value"))
                if actual is None or expected is None:
                    continue
                if expected_unit and fact.get("unit") and str(expected_unit) != str(fact.get("unit")):
                    incompatible_unit = True
                    continue
                result = _evaluate(operator, actual, expected)
                if result is not None:
                    evaluated.append(result)
            if incompatible_unit and not evaluated:
                status = VerificationStatus.CANNOT_DETERMINE.value
                reason = "指标单位与规则阈值不一致，且未接入有来源的换算规则。"
                next_action = "核对统计口径并提供可追溯的单位换算依据。"
            elif expected is None or not operator or not evaluated:
                status = VerificationStatus.PENDING_VERIFICATION.value
                reason = "已找到项目事实，但规则未提供可执行的明文数值阈值。"
                next_action = "人工对照规则原文核验，不使用模型设计值。"
            elif all(evaluated):
                status = VerificationStatus.SATISFIED.value
                reason = "项目事实在同口径下满足已入库的明文阈值。"
                next_action = None
            else:
                status = VerificationStatus.NOT_SATISFIED.value
                reason = "至少一条同口径项目事实不满足明文阈值。"
                next_action = "人工复核原始证据、适用范围和是否存在有效调整依据。"

        output.append(VerificationCandidate(
            semantic_key=_semantic_key(rule["rule_version_id"], metric, status, *fact_ids),
            rule_version_id=str(rule["rule_version_id"]),
            dimension=dimension,
            requirement_text=requirement,
            status=status,
            applicability_reason=reason,
            next_action=next_action,
            fact_ids=fact_ids,
            evidence_ids=evidence_ids,
        ))
    return output
