"""Unified, evidence-first risk contract and five-source aggregation engine.

The module deliberately separates a *risk item* from source coverage.  A
source that did not run (most importantly the optional BERT runtime) produces
only :class:`RiskSourceCoverage`; it must never be represented as a low/zero
risk finding.  Likewise, a missing document may create an ``unknown`` item
with ``insufficient_evidence`` coverage, but never a synthetic pass/fail.

``RiskClue`` remains the persistence compatibility boundary for the phase-4
case service.  New callers should consume :class:`UnifiedRiskAssessment`.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from green_model.agent.domain.enums import CoverageStatus, RiskDimension, RiskLevel

from .contracts import (
    AxisAssessment,
    ClaimExtractionResult,
    ConflictCandidate,
    RiskClue,
    VerificationCandidate,
)


class RiskSourceType(str, Enum):
    """Stable machine codes for the five independent risk sources."""

    BERT_TEXT = "bert_text"
    RULE = "rule"
    DATA_CONFLICT = "data_conflict"
    FUND_IMPLEMENTATION = "fund_implementation"
    POSTLOAN_DEVIATION = "postloan_deviation"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RiskItem:
    """One traceable review item, never an automatic credit decision.

    ``basis`` explains why the item exists.  The four lineage collections
    point to the concrete evidence/facts/rules/model run that support it.  A
    review priority is only a work-queue ordering aid; it is not a probability
    of default, approval, non-compliance, or greenwashing.
    """

    semantic_key: str
    source_type: RiskSourceType
    risk_dimension: RiskDimension
    trigger_type: str
    level: RiskLevel
    basis: str
    coverage_status: CoverageStatus
    review_priority: int | None = None
    evidence_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    model_run_id: str | None = None
    inference_policy_version: str | None = None
    is_model_result: bool = False
    requires_human_confirmation: bool = True
    eligible_for_decision: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.semantic_key:
            raise ValueError("RiskItem.semantic_key 不能为空")
        if not self.basis.strip():
            raise ValueError("RiskItem.basis 不能为空")
        if self.review_priority is not None and not 0 <= self.review_priority <= 100:
            raise ValueError("RiskItem.review_priority 必须位于 0 到 100")
        if self.coverage_status in {
            CoverageStatus.MODEL_NOT_RUN,
            CoverageStatus.MODEL_ABSTAINED,
        }:
            raise ValueError("模型未运行/弃权只能登记为来源覆盖状态，不能伪装成风险项")
        if (
            self.coverage_status is not CoverageStatus.ASSESSED
            and self.level is not RiskLevel.UNKNOWN
        ):
            raise ValueError("未完成评估或证据不足时，风险等级必须为 unknown")
        if not self.requires_human_confirmation:
            raise ValueError("统一风险项必须等待人工确认")
        if self.eligible_for_decision:
            raise ValueError("风险线索不得直接用于自动授信决策")
        if self.source_type is RiskSourceType.BERT_TEXT and self.is_model_result:
            # A real model item may legitimately lack the run id in a legacy
            # adapter, but it must retain the explicit model provenance flag.
            return
        if self.is_model_result:
            raise ValueError("只有 BERT 文本来源可以标记为模型结果")


@dataclass(frozen=True)
class RiskSourceCoverage:
    """Coverage of one source even when it yielded no risk item."""

    source_type: RiskSourceType
    coverage_status: CoverageStatus
    message: str
    input_count: int = 0
    finding_count: int = 0
    model_run_id: str | None = None


@dataclass(frozen=True)
class UnifiedRiskAssessment:
    risk_items: tuple[RiskItem, ...]
    axes: tuple[AxisAssessment, ...]
    source_coverages: tuple[RiskSourceCoverage, ...]

    def coverage_for(self, source_type: RiskSourceType) -> RiskSourceCoverage:
        for coverage in self.source_coverages:
            if coverage.source_type is source_type:
                return coverage
        raise KeyError(source_type.value)


FIELD_DIMENSIONS = {
    "investment_amount": RiskDimension.PROJECT_BOUNDARY_AND_USE,
    "financing_amount": RiskDimension.PROJECT_BOUNDARY_AND_USE,
    "funding_purpose": RiskDimension.PROJECT_BOUNDARY_AND_USE,
    "project_scope": RiskDimension.PROJECT_BOUNDARY_AND_USE,
    "project_name": RiskDimension.PROJECT_BOUNDARY_AND_USE,
    "installed_capacity": RiskDimension.TECHNICAL_AND_COMPLIANCE,
    "energy_consumption": RiskDimension.TECHNICAL_AND_COMPLIANCE,
    "emission": RiskDimension.TECHNICAL_AND_COMPLIANCE,
    "project_stage": RiskDimension.IMPLEMENTATION_AND_FUNDS,
    "construction_progress": RiskDimension.IMPLEMENTATION_AND_FUNDS,
    "payment_amount": RiskDimension.IMPLEMENTATION_AND_FUNDS,
    "invoice_amount": RiskDimension.IMPLEMENTATION_AND_FUNDS,
    "contract_amount": RiskDimension.IMPLEMENTATION_AND_FUNDS,
    "actual_performance": RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE,
}

_SOURCE_PROVENANCE = {
    RiskSourceType.BERT_TEXT: "model",
    RiskSourceType.RULE: "rule",
    RiskSourceType.DATA_CONFLICT: "deterministic_comparison",
    RiskSourceType.FUND_IMPLEMENTATION: "deterministic_comparison",
    RiskSourceType.POSTLOAN_DEVIATION: "deterministic_bta",
}


def _key(*parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _risk_from_priority(priority: int) -> RiskLevel:
    if priority >= 85:
        return RiskLevel.CRITICAL
    if priority >= 70:
        return RiskLevel.HIGH
    if priority >= 45:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _claim_items(
    result: ClaimExtractionResult,
) -> tuple[list[RiskItem], RiskSourceCoverage]:
    if result.coverage_status in {
        CoverageStatus.MODEL_NOT_RUN,
        CoverageStatus.MODEL_ABSTAINED,
    }:
        return [], RiskSourceCoverage(
            source_type=RiskSourceType.BERT_TEXT,
            coverage_status=result.coverage_status,
            message=result.message,
            input_count=len(result.predictions),
            finding_count=0,
            model_run_id=result.model_run_id,
        )

    items: list[RiskItem] = []
    for claim in result.claims:
        if claim.support_status in {"supported", "model_unavailable"}:
            continue
        priority = {
            "contradicted": 90,
            "unsupported": 70,
            "pending_review": 45,
        }.get(claim.support_status, 45)
        negative_event = bool(
            claim.claim_type
            and any(term in claim.claim_type for term in ("负面风险", "处罚"))
        )
        basis = {
            "contradicted": "绿色主张与当前已获取事实存在矛盾线索。",
            "unsupported": "绿色主张暂未找到可定位的实质证据支持。",
            "pending_review": "绿色承诺或目标需继续核对量化数据、行动和项目边界。",
        }.get(claim.support_status, "绿色主张需人工复核。")
        if negative_event:
            basis = "模型识别到负面环境风险或处罚文本，需回到原文并与外部官方记录核对。"
        items.append(RiskItem(
            semantic_key=_key("claim", claim.evidence_id, claim.text, claim.support_status),
            source_type=RiskSourceType.BERT_TEXT,
            risk_dimension=RiskDimension.CLAIM_CREDIBILITY,
            trigger_type=(
                "negative_environment_event"
                if negative_event
                else f"claim_{claim.support_status}"
            ),
            level=_risk_from_priority(priority),
            review_priority=priority,
            basis=basis,
            coverage_status=CoverageStatus.ASSESSED,
            evidence_ids=(claim.evidence_id,) if claim.evidence_id else (),
            model_run_id=claim.model_run_id or result.model_run_id,
            inference_policy_version=claim.inference_policy_version,
            is_model_result=claim.is_model_output,
            metadata={
                "claim_text": claim.text,
                "claim_type": claim.claim_type,
                "green_relevance": claim.green_relevance,
                "evidence_strength": claim.evidence_strength,
                "support_status": claim.support_status,
                "prediction_id": claim.prediction_id,
            },
        ))
    return items, RiskSourceCoverage(
        source_type=RiskSourceType.BERT_TEXT,
        coverage_status=result.coverage_status,
        message=result.message,
        input_count=len(result.claims) or len(result.predictions),
        finding_count=len(items),
        model_run_id=result.model_run_id,
    )


def _rule_items(
    verifications: Sequence[VerificationCandidate],
    *,
    rule_count: int,
) -> tuple[list[RiskItem], RiskSourceCoverage]:
    items: list[RiskItem] = []
    for item in verifications:
        if item.status in {"satisfied", "not_applicable", "attribute_only"} or item.module in {
            "process", "equipment", "standard", "indicator", "term", "route"
        }:
            continue
        priority, level, coverage = {
            "not_satisfied": (80, RiskLevel.HIGH, CoverageStatus.ASSESSED),
            "evidence_conflict": (75, RiskLevel.HIGH, CoverageStatus.ASSESSED),
            "pending_verification": (
                50,
                RiskLevel.UNKNOWN,
                CoverageStatus.INSUFFICIENT_EVIDENCE,
            ),
            "cannot_determine": (
                45,
                RiskLevel.UNKNOWN,
                CoverageStatus.RULE_NOT_AVAILABLE,
            ),
        }.get(
            item.status,
            (45, RiskLevel.UNKNOWN, CoverageStatus.INSUFFICIENT_EVIDENCE),
        )
        rule_ids = tuple(dict.fromkeys(
            str(value)
            for value in (item.rule_version_id, item.master_rule_id)
            if value
        ))
        items.append(RiskItem(
            semantic_key=_key("verification", item.semantic_key),
            source_type=RiskSourceType.RULE,
            risk_dimension=item.dimension,
            trigger_type=f"rule_{item.status}",
            level=level,
            review_priority=priority,
            basis=(
                item.applicability_reason
                or item.requirement_text
                or "适用规则尚未完成核验。"
            ),
            coverage_status=coverage,
            evidence_ids=item.evidence_ids,
            fact_ids=item.fact_ids,
            rule_ids=rule_ids,
            metadata={
                "requirement_text": item.requirement_text,
                "next_action": item.next_action,
                "rule_version_id": item.rule_version_id,
                "master_rule_type": item.master_rule_type,
                "master_rule_id": item.master_rule_id,
                "source_manifest_id": item.source_manifest_id,
            },
        ))

    if not verifications and rule_count == 0:
        coverage = CoverageStatus.RULE_NOT_AVAILABLE
        message = "当前行业规则未接入；不生成技术合规风险结论。"
    elif any(item.coverage_status is CoverageStatus.INSUFFICIENT_EVIDENCE for item in items):
        coverage = CoverageStatus.INSUFFICIENT_EVIDENCE
        message = "适用规则已装载，但仍有核验项缺少证据。"
    elif any(item.coverage_status is CoverageStatus.RULE_NOT_AVAILABLE for item in items):
        coverage = CoverageStatus.RULE_NOT_AVAILABLE
        message = "部分核验项缺少可执行规则或明确阈值。"
    else:
        coverage = CoverageStatus.ASSESSED
        message = "适用规则核验已执行；风险项仍需人工确认。"
    return items, RiskSourceCoverage(
        source_type=RiskSourceType.RULE,
        coverage_status=coverage,
        message=message,
        input_count=len(verifications),
        finding_count=len(items),
    )


def _conflict_items(
    conflicts: Sequence[ConflictCandidate],
    *,
    facts: Sequence[Mapping[str, Any]],
) -> tuple[list[RiskItem], RiskSourceCoverage]:
    level_priority = {
        RiskLevel.LOW: 30,
        RiskLevel.MEDIUM: 55,
        RiskLevel.HIGH: 75,
        RiskLevel.CRITICAL: 90,
        RiskLevel.UNKNOWN: 45,
    }
    items = [
        RiskItem(
            semantic_key=_key("conflict", conflict.semantic_key),
            source_type=RiskSourceType.DATA_CONFLICT,
            risk_dimension=FIELD_DIMENSIONS.get(
                conflict.field_name, RiskDimension.PROJECT_BOUNDARY_AND_USE
            ),
            trigger_type=conflict.conflict_type,
            level=conflict.risk_level,
            review_priority=level_priority[conflict.risk_level],
            basis=(
                f"字段“{conflict.field_name}”存在跨文件数值差异，需核对项目边界、"
                "统计口径、文件版本和变更批复。"
            ),
            coverage_status=CoverageStatus.ASSESSED,
            evidence_ids=tuple(
                value
                for value in (conflict.evidence_a_id, conflict.evidence_b_id)
                if value
            ),
            fact_ids=(conflict.fact_a_id, conflict.fact_b_id),
            metadata={
                "raw_value_a": conflict.raw_value_a,
                "raw_value_b": conflict.raw_value_b,
                "normalized_value_a": conflict.normalized_value_a,
                "normalized_value_b": conflict.normalized_value_b,
                "difference_value": conflict.difference_value,
                "difference_unit": conflict.difference_unit,
                "difference_ratio": conflict.difference_ratio,
                "comparison_method": conflict.comparison_method,
            },
        )
        for conflict in conflicts
    ]
    facts_by_category: dict[str, int] = defaultdict(int)
    for fact in facts:
        category = fact.get("fact_category")
        if category:
            facts_by_category[str(category)] += 1
    has_comparable_candidates = bool(conflicts) or any(
        count >= 2 for count in facts_by_category.values()
    )
    coverage = (
        CoverageStatus.ASSESSED
        if has_comparable_candidates
        else CoverageStatus.INSUFFICIENT_EVIDENCE
    )
    message = (
        "跨文件同口径比较已执行。"
        if coverage is CoverageStatus.ASSESSED
        else "可比较事实不足，不能据此推断不存在数据冲突。"
    )
    return items, RiskSourceCoverage(
        source_type=RiskSourceType.DATA_CONFLICT,
        coverage_status=coverage,
        message=message,
        input_count=len(facts),
        finding_count=len(items),
    )


def _fact_evidence_index(
    links: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[str, ...]]:
    indexed: dict[str, list[str]] = defaultdict(list)
    for link in links:
        fact_id = link.get("fact_id")
        evidence_id = link.get("evidence_id")
        if fact_id and evidence_id and str(evidence_id) not in indexed[str(fact_id)]:
            indexed[str(fact_id)].append(str(evidence_id))
    return {key: tuple(values) for key, values in indexed.items()}


def _unambiguous_fact(
    facts_by_category: Mapping[str, list[Mapping[str, Any]]],
    category: str,
) -> tuple[Mapping[str, Any], Decimal] | None:
    candidates: list[tuple[Mapping[str, Any], Decimal]] = []
    for fact in facts_by_category.get(category, []):
        value = _decimal(fact.get("normalized_value"))
        if value is not None:
            candidates.append((fact, value))
    distinct = {value for _, value in candidates}
    if len(distinct) != 1 or not candidates:
        return None
    return candidates[-1]


def _implementation_items(
    facts: Sequence[Mapping[str, Any]],
    fact_evidence_links: Sequence[Mapping[str, Any]],
) -> tuple[list[RiskItem], RiskSourceCoverage]:
    relevant_categories = {
        "investment_amount",
        "financing_amount",
        "contract_amount",
        "invoice_amount",
        "payment_amount",
        "construction_progress",
        "funding_purpose",
        "project_stage",
    }
    relevant = [
        fact for fact in facts if str(fact.get("fact_category")) in relevant_categories
    ]
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fact in relevant:
        grouped[str(fact.get("fact_category"))].append(fact)
    evidence_by_fact = _fact_evidence_index(fact_evidence_links)

    numeric = {
        category: _unambiguous_fact(grouped, category)
        for category in (
            "investment_amount",
            "financing_amount",
            "contract_amount",
            "invoice_amount",
            "payment_amount",
            "construction_progress",
        )
    }
    items: list[RiskItem] = []

    def add_comparison(
        *,
        left_category: str,
        right_category: str,
        trigger_type: str,
        label: str,
        minimum_priority: int = 75,
    ) -> None:
        left = numeric[left_category]
        right = numeric[right_category]
        if left is None or right is None:
            return
        left_fact, left_value = left
        right_fact, right_value = right
        left_unit = left_fact.get("unit")
        right_unit = right_fact.get("unit")
        if left_unit and right_unit and left_unit != right_unit:
            return
        if left_value <= right_value:
            return
        denominator = abs(right_value)
        ratio = (left_value - right_value) / denominator if denominator else Decimal("1")
        priority = max(
            minimum_priority,
            90 if ratio >= Decimal("0.20") else 80 if ratio >= Decimal("0.10") else 70,
        )
        fact_ids = tuple(
            str(value)
            for value in (left_fact.get("fact_id"), right_fact.get("fact_id"))
            if value
        )
        evidence_ids = tuple(dict.fromkeys(
            evidence_id
            for fact_id in fact_ids
            for evidence_id in evidence_by_fact.get(fact_id, ())
        ))
        items.append(RiskItem(
            semantic_key=_key(
                "funds", trigger_type, left_fact.get("fact_id"), right_fact.get("fact_id")
            ),
            source_type=RiskSourceType.FUND_IMPLEMENTATION,
            risk_dimension=RiskDimension.IMPLEMENTATION_AND_FUNDS,
            trigger_type=trigger_type,
            level=_risk_from_priority(priority),
            review_priority=priority,
            basis=(
                f"{label}：{left_category}={left_value}{left_unit or ''}，"
                f"{right_category}={right_value}{right_unit or ''}；"
                "需核对合同、发票、付款凭证、受款对象及资金用途。"
            ),
            coverage_status=CoverageStatus.ASSESSED,
            evidence_ids=evidence_ids,
            fact_ids=fact_ids,
            metadata={
                "left_category": left_category,
                "left_value": str(left_value),
                "right_category": right_category,
                "right_value": str(right_value),
                "difference_ratio": str(ratio),
                "unit": left_unit or right_unit,
            },
        ))

    add_comparison(
        left_category="financing_amount",
        right_category="investment_amount",
        trigger_type="financing_exceeds_total_investment",
        label="融资金额超过项目总投资",
        minimum_priority=80,
    )
    add_comparison(
        left_category="invoice_amount",
        right_category="contract_amount",
        trigger_type="invoice_exceeds_contract",
        label="发票金额超过合同金额",
    )
    add_comparison(
        left_category="payment_amount",
        right_category="invoice_amount",
        trigger_type="payment_exceeds_invoice",
        label="已支付金额超过发票金额",
    )
    add_comparison(
        left_category="payment_amount",
        right_category="contract_amount",
        trigger_type="payment_exceeds_contract",
        label="已支付金额超过合同金额",
        minimum_priority=80,
    )

    payment = numeric["payment_amount"]
    contract = numeric["contract_amount"]
    progress = numeric["construction_progress"]
    if payment is not None and contract is not None and progress is not None:
        payment_fact, payment_value = payment
        contract_fact, contract_value = contract
        progress_fact, progress_value = progress
        if (
            contract_value > 0
            and payment_fact.get("unit") == contract_fact.get("unit")
            and Decimal("0") <= progress_value <= Decimal("100")
        ):
            payment_progress = payment_value / contract_value * Decimal("100")
            gap = payment_progress - progress_value
            if gap > Decimal("20"):
                priority = 80 if gap >= Decimal("40") else 70
                fact_ids = tuple(
                    str(value)
                    for value in (
                        payment_fact.get("fact_id"),
                        contract_fact.get("fact_id"),
                        progress_fact.get("fact_id"),
                    )
                    if value
                )
                evidence_ids = tuple(dict.fromkeys(
                    evidence_id
                    for fact_id in fact_ids
                    for evidence_id in evidence_by_fact.get(fact_id, ())
                ))
                items.append(RiskItem(
                    semantic_key=_key("funds", "payment_progress_mismatch", *fact_ids),
                    source_type=RiskSourceType.FUND_IMPLEMENTATION,
                    risk_dimension=RiskDimension.IMPLEMENTATION_AND_FUNDS,
                    trigger_type="payment_ahead_of_construction_progress",
                    level=_risk_from_priority(priority),
                    review_priority=priority,
                    basis=(
                        f"按合同金额计算的付款进度为{payment_progress:.2f}%，"
                        f"高于材料披露建设进度{progress_value}%约{gap:.2f}个百分点；"
                        "需核对付款节点、工程量确认和受款对象。"
                    ),
                    coverage_status=CoverageStatus.ASSESSED,
                    evidence_ids=evidence_ids,
                    fact_ids=fact_ids,
                    metadata={
                        "payment_progress_percent": str(payment_progress),
                        "construction_progress_percent": str(progress_value),
                        "gap_percentage_points": str(gap),
                    },
                ))

    comparable_pairs = (
        ("financing_amount", "investment_amount"),
        ("invoice_amount", "contract_amount"),
        ("payment_amount", "invoice_amount"),
        ("payment_amount", "contract_amount"),
    )
    has_comparable_pair = any(
        numeric[left] is not None
        and numeric[right] is not None
        and (
            not numeric[left][0].get("unit")
            or not numeric[right][0].get("unit")
            or numeric[left][0].get("unit") == numeric[right][0].get("unit")
        )
        for left, right in comparable_pairs
    )
    coverage = (
        CoverageStatus.ASSESSED
        if has_comparable_pair
        else CoverageStatus.INSUFFICIENT_EVIDENCE
    )
    message = (
        "资金与实施金额关系已执行同口径比较。"
        if coverage is CoverageStatus.ASSESSED
        else "缺少可同口径比较的投资、融资、合同、发票或支付事实。"
    )
    return items, RiskSourceCoverage(
        source_type=RiskSourceType.FUND_IMPLEMENTATION,
        coverage_status=coverage,
        message=message,
        input_count=len(relevant),
        finding_count=len(items),
    )


def _postloan_items(
    indicators: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> tuple[list[RiskItem], RiskSourceCoverage]:
    observations_by_indicator: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for observation in observations:
        observations_by_indicator[str(observation.get("indicator_id"))][
            str(observation.get("series_type"))
        ].append(observation)

    items: list[RiskItem] = []
    comparable_count = 0
    for indicator in indicators:
        indicator_id = str(indicator.get("indicator_id"))
        grouped = observations_by_indicator.get(indicator_id, {})
        targets = grouped.get("target", [])
        actuals = grouped.get("actual", [])
        if not targets or not actuals:
            continue
        target = targets[-1]
        actual = actuals[-1]
        target_value = _decimal(target.get("normalized_value"))
        actual_value = _decimal(actual.get("normalized_value"))
        if target_value is None or actual_value is None:
            continue
        unit = indicator.get("unit") or target.get("unit")
        if target.get("unit") and actual.get("unit") and target.get("unit") != actual.get("unit"):
            continue
        if (
            target.get("statistical_scope")
            and actual.get("statistical_scope")
            and target.get("statistical_scope") != actual.get("statistical_scope")
        ):
            continue
        comparable_count += 1
        direction = str(indicator.get("direction") or "").lower()
        adverse = (
            direction in {"higher_is_better", "minimum", "up"}
            and actual_value < target_value
        ) or (
            direction in {"lower_is_better", "maximum", "down"}
            and actual_value > target_value
        )
        if not adverse:
            continue
        denominator = abs(target_value)
        ratio = (
            abs(actual_value - target_value) / denominator
            if denominator
            else Decimal("1")
        )
        priority = 80 if ratio >= Decimal("0.20") else 70 if ratio >= Decimal("0.10") else 50
        evidence_ids = tuple(
            str(value)
            for value in (target.get("evidence_id"), actual.get("evidence_id"))
            if value
        )
        items.append(RiskItem(
            semantic_key=_key("bta", indicator_id, target_value, actual_value),
            source_type=RiskSourceType.POSTLOAN_DEVIATION,
            risk_dimension=RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE,
            trigger_type="target_actual_adverse_deviation",
            level=_risk_from_priority(priority),
            review_priority=priority,
            basis=(
                f"指标“{indicator.get('indicator_name') or indicator_id}”实际值"
                f"{actual_value}{unit or ''}较目标值{target_value}{unit or ''}出现不利偏离；"
                "偏离只触发人工复核，不直接等同违约或漂绿。"
            ),
            coverage_status=CoverageStatus.ASSESSED,
            evidence_ids=evidence_ids,
            metadata={
                "indicator_id": indicator_id,
                "target_observation_id": target.get("observation_id"),
                "actual_observation_id": actual.get("observation_id"),
                "target_value": str(target_value),
                "actual_value": str(actual_value),
                "deviation_ratio": str(ratio),
                "direction": direction,
                "unit": unit,
            },
        ))

    coverage = (
        CoverageStatus.ASSESSED
        if comparable_count
        else CoverageStatus.INSUFFICIENT_EVIDENCE
    )
    message = (
        "已完成同单位、同统计范围的目标值与实际值比较。"
        if coverage is CoverageStatus.ASSESSED
        else "尚未形成可同口径比较的 Target 与 Actual 记录。"
    )
    return items, RiskSourceCoverage(
        source_type=RiskSourceType.POSTLOAN_DEVIATION,
        coverage_status=coverage,
        message=message,
        input_count=len(observations),
        finding_count=len(items),
    )


def _axis_assessments(
    items: Sequence[RiskItem],
    coverages: Mapping[RiskSourceType, RiskSourceCoverage],
    *,
    fact_categories: set[str],
    rule_count: int,
) -> tuple[AxisAssessment, ...]:
    by_dimension: dict[RiskDimension, list[RiskItem]] = defaultdict(list)
    for item in items:
        by_dimension[item.risk_dimension].append(item)

    axes: list[AxisAssessment] = []
    for dimension in RiskDimension:
        dimension_items = by_dimension.get(dimension, [])
        if dimension_items:
            score = max(
                (item.review_priority or 0 for item in dimension_items),
                default=None,
            )
            known_levels = [
                item.level for item in dimension_items if item.level is not RiskLevel.UNKNOWN
            ]
            level = _risk_from_priority(score or 0) if known_levels else RiskLevel.UNKNOWN
            coverage = (
                CoverageStatus.ASSESSED
                if any(
                    item.coverage_status is CoverageStatus.ASSESSED
                    for item in dimension_items
                )
                else dimension_items[0].coverage_status
            )
            summary = f"形成{len(dimension_items)}条可追溯风险线索，等待人工复核。"
        else:
            score = None
            level = RiskLevel.UNKNOWN
            if dimension is RiskDimension.CLAIM_CREDIBILITY:
                source = coverages[RiskSourceType.BERT_TEXT]
                coverage, summary = source.coverage_status, source.message
            elif dimension is RiskDimension.TECHNICAL_AND_COMPLIANCE and rule_count == 0:
                source = coverages[RiskSourceType.RULE]
                coverage, summary = source.coverage_status, source.message
            elif dimension is RiskDimension.IMPLEMENTATION_AND_FUNDS:
                source = coverages[RiskSourceType.FUND_IMPLEMENTATION]
                coverage, summary = source.coverage_status, source.message
            elif dimension is RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE:
                source = coverages[RiskSourceType.POSTLOAN_DEVIATION]
                coverage, summary = source.coverage_status, source.message
            elif dimension is RiskDimension.PROJECT_BOUNDARY_AND_USE and not fact_categories.intersection({
                "investment_amount",
                "financing_amount",
                "funding_purpose",
                "project_scope",
            }):
                coverage = CoverageStatus.INSUFFICIENT_EVIDENCE
                summary = "缺少项目边界或融资用途事实，不作低风险推断。"
            else:
                coverage = CoverageStatus.ASSESSED
                summary = "当前已处理材料未触发该维度风险线索。"
        axes.append(AxisAssessment(
            dimension=dimension,
            coverage_status=coverage,
            attention_score=score,
            risk_level=level,
            finding_count=len(dimension_items),
            summary=summary,
        ))
    return tuple(axes)


def build_unified_risk_assessment(
    *,
    claim_result: ClaimExtractionResult,
    conflicts: Iterable[ConflictCandidate],
    verifications: Iterable[VerificationCandidate],
    indicators: Iterable[Mapping[str, Any]],
    observations: Iterable[Mapping[str, Any]],
    facts: Iterable[Mapping[str, Any]],
    fact_evidence_links: Iterable[Mapping[str, Any]] = (),
    rule_count: int,
) -> UnifiedRiskAssessment:
    """Aggregate all five sources without converting missing coverage to risk."""

    conflicts = list(conflicts)
    verifications = list(verifications)
    indicators = list(indicators)
    observations = list(observations)
    facts = list(facts)
    fact_evidence_links = list(fact_evidence_links)

    claim_items, claim_coverage = _claim_items(claim_result)
    rule_items, rule_coverage = _rule_items(verifications, rule_count=rule_count)
    conflict_items, conflict_coverage = _conflict_items(
        conflicts, facts=facts
    )
    implementation_items, implementation_coverage = _implementation_items(
        facts, fact_evidence_links
    )
    postloan_items, postloan_coverage = _postloan_items(indicators, observations)

    items = tuple(
        claim_items
        + rule_items
        + conflict_items
        + implementation_items
        + postloan_items
    )
    source_coverages = (
        claim_coverage,
        rule_coverage,
        conflict_coverage,
        implementation_coverage,
        postloan_coverage,
    )
    coverage_index = {
        coverage.source_type: coverage for coverage in source_coverages
    }
    axes = _axis_assessments(
        items,
        coverage_index,
        fact_categories={str(row.get("fact_category")) for row in facts},
        rule_count=rule_count,
    )
    return UnifiedRiskAssessment(
        risk_items=items,
        axes=axes,
        source_coverages=source_coverages,
    )


def risk_item_to_clue(item: RiskItem) -> RiskClue:
    """Adapt the new contract to the existing phase-4 persistence boundary."""

    # ``risk_rule_links`` currently points only to ``rule_versions``.  Master
    # rule identifiers remain explicit on RiskItem.metadata but must not be
    # inserted into that foreign key until a later schema migration adds a
    # polymorphic rule link.
    rule_version_id = item.metadata.get("rule_version_id")
    persistent_rule_ids = (
        (str(rule_version_id),)
        if rule_version_id
        else (() if item.metadata.get("master_rule_id") else item.rule_ids)
    )

    return RiskClue(
        semantic_key=item.semantic_key,
        dimension=item.risk_dimension,
        trigger_type=item.trigger_type,
        level=item.level,
        priority=item.review_priority or 0,
        text=item.basis,
        coverage_status=item.coverage_status,
        evidence_ids=item.evidence_ids,
        fact_ids=item.fact_ids,
        rule_version_ids=persistent_rule_ids,
        is_model_result=item.is_model_result,
        provenance_kind=_SOURCE_PROVENANCE[item.source_type],
        model_run_id=item.model_run_id,
        inference_policy_version=item.inference_policy_version,
    )


def risk_items_to_clues(items: Iterable[RiskItem]) -> list[RiskClue]:
    return [risk_item_to_clue(item) for item in items]


__all__ = [
    "RiskItem",
    "RiskSourceCoverage",
    "RiskSourceType",
    "UnifiedRiskAssessment",
    "build_unified_risk_assessment",
    "risk_item_to_clue",
    "risk_items_to_clues",
]
