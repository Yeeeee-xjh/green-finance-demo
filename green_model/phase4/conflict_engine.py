"""Cross-document fact comparison with explicit comparability rules."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from green_model.agent.domain.enums import RiskLevel

from .contracts import ConflictCandidate


@dataclass(frozen=True)
class ConflictPolicy:
    """Operational review thresholds, not regulatory or credit thresholds."""

    medium_ratio: Decimal = Decimal("0.05")
    high_ratio: Decimal = Decimal("0.10")
    critical_ratio: Decimal = Decimal("0.20")


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _key(*parts: Any) -> str:
    raw = "|".join("" if value is None else str(value) for value in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _risk_level(ratio: Decimal, policy: ConflictPolicy) -> RiskLevel:
    if ratio >= policy.critical_ratio:
        return RiskLevel.CRITICAL
    if ratio >= policy.high_ratio:
        return RiskLevel.HIGH
    if ratio >= policy.medium_ratio:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def detect_numeric_conflicts(
    facts: Iterable[dict[str, Any]],
    fact_evidence_links: Iterable[dict[str, Any]],
    evidence: Iterable[dict[str, Any]],
    *,
    policy: ConflictPolicy | None = None,
) -> list[ConflictCandidate]:
    """Compare like-for-like numeric facts from different documents.

    Values with different units, periods, subjects or scopes are not silently
    compared.  This function emits only actual comparable mismatches; missing
    comparability is handled by verification coverage, not labelled a conflict.
    """

    policy = policy or ConflictPolicy()
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    evidence_ids_by_fact: dict[str, list[str]] = defaultdict(list)
    for link in fact_evidence_links:
        evidence_ids_by_fact[str(link["fact_id"])].append(str(link["evidence_id"]))

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        value = _decimal(fact.get("normalized_value"))
        if value is None:
            continue
        group_key = (
            fact.get("fact_category"),
            fact.get("subject_id"),
            fact.get("scope_text"),
            fact.get("period_start"),
            fact.get("period_end"),
            fact.get("unit"),
        )
        groups[group_key].append({**fact, "_decimal": value})

    output: list[ConflictCandidate] = []
    seen_pairs: set[tuple[str, str]] = set()
    for group_key, rows in groups.items():
        if len(rows) < 2:
            continue
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1 :]:
                pair = tuple(sorted((str(left["fact_id"]), str(right["fact_id"]))))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                left_evidence = evidence_ids_by_fact.get(str(left["fact_id"]), [])
                right_evidence = evidence_ids_by_fact.get(str(right["fact_id"]), [])
                evidence_a = left_evidence[0] if left_evidence else None
                evidence_b = right_evidence[0] if right_evidence else None
                doc_a = evidence_by_id.get(evidence_a or "", {}).get("doc_id")
                doc_b = evidence_by_id.get(evidence_b or "", {}).get("doc_id")
                if not doc_a or not doc_b or doc_a == doc_b:
                    continue
                value_a: Decimal = left["_decimal"]
                value_b: Decimal = right["_decimal"]
                if value_a == value_b:
                    continue
                difference = abs(value_a - value_b)
                denominator = min(abs(value_a), abs(value_b))
                ratio = difference / denominator if denominator else Decimal("1")
                semantic_key = _key("numeric", *pair, group_key, value_a, value_b)
                output.append(ConflictCandidate(
                    semantic_key=semantic_key,
                    field_name=str(left.get("fact_category") or "unknown_field"),
                    conflict_type="cross_document_numeric_mismatch",
                    fact_a_id=str(left["fact_id"]),
                    fact_b_id=str(right["fact_id"]),
                    evidence_a_id=evidence_a,
                    evidence_b_id=evidence_b,
                    raw_value_a=left.get("raw_value"),
                    raw_value_b=right.get("raw_value"),
                    normalized_value_a=str(value_a),
                    normalized_value_b=str(value_b),
                    difference_value=str(difference),
                    difference_unit=left.get("unit"),
                    denominator_value=str(denominator),
                    difference_ratio=str(ratio),
                    comparison_method=(
                        "同字段、同主体、同边界、同期间、同单位的跨文件数值比较；"
                        "差异比例=绝对差额/较小绝对值。分级为系统复核排序参数，非监管阈值。"
                    ),
                    risk_level=_risk_level(ratio, policy),
                ))
    return sorted(output, key=lambda item: (item.field_name, item.semantic_key))

