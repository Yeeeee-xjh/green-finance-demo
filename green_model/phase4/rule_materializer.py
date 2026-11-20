"""Materialise Phase 3.6 industry rules into case verification candidates.

This module is intentionally repository-agnostic.  Callers provide rows from
the Phase 3.6 registry and the current case snapshot, which keeps the rule to
case connection independently testable and lets the persistence service own
transactions and task creation.

The materialiser is fail closed:

* only density-qualified formal rows or explicitly marked mock rows load;
* mock rows never become ``satisfied`` (or any other conclusive status);
* no row is auto-passed merely because a similarly named document exists;
* context modules never prescribe a task;
* post-loan rows are actionable only when the case is in a post-loan stage.

Mock and real rows travel through the same arguments and candidate contract.
Replacing a mock package therefore changes data rows, not this execution path.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from green_model.agent.domain.enums import RiskDimension, VerificationStatus

from .contracts import ConflictCandidate, VerificationCandidate


SUPPORTED_INDUSTRY_CODES = frozenset({"3011", "3110", "4415"})

# These modules describe the industry or help the reader interpret a rule.
# They can be shown beside the case, but must not create workflow tasks.
CONTEXT_MODULES = frozenset(
    {"process", "equipment", "standard", "indicator", "term", "route"}
)
ACTIONABLE_MODULES = frozenset(
    {"threshold", "permit", "document", "evidence", "risk", "postloan"}
)

MODULE_RECORD_KEYS = {
    "process": ("industry_knowledge_items", "knowledge_id"),
    "equipment": ("industry_knowledge_items", "knowledge_id"),
    "route": ("industry_knowledge_items", "knowledge_id"),
    "standard": ("industry_standard_links", "link_id"),
    "indicator": ("indicator_definitions", "indicator_definition_id"),
    "threshold": ("threshold_definitions", "threshold_id"),
    "permit": ("permit_requirements", "permit_requirement_id"),
    "document": ("document_requirements", "document_requirement_id"),
    "evidence": ("evidence_requirements", "evidence_requirement_id"),
    "risk": ("industry_risk_points", "risk_point_id"),
    "term": ("term_cards", "term_id"),
    "postloan": ("postloan_indicator_definitions", "postloan_indicator_id"),
}

_MODULE_WHY = {
    "threshold": "核对项目事实是否与规则明文阈值采用同一统计口径。",
    "permit": "核对项目手续的主体、范围、版本和有效期是否覆盖本项目。",
    "document": "确认规则要求的材料已提供，且材料内容而非文件名称能够支持判断。",
    "evidence": "确认项目主张有可定位、可复核的原始证据支撑。",
    "risk": "针对行业高频风险点核对项目边界、事实与证据是否一致。",
    "postloan": "持续核对项目实际表现与基准、目标及合规要求的偏离。",
}

_FACT_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("装机容量", "建设容量", "核准容量"), "installed_capacity"),
    (("发电量", "上网电量"), "annual_generation"),
    (("综合能耗", "能源消耗", "能耗"), "energy_consumption"),
    (("碳排放", "二氧化碳排放"), "carbon_emission"),
    (("投资额", "总投资"), "investment_amount"),
    (("贷款金额", "融资金额"), "loan_amount"),
    (("合同金额",), "contract_amount"),
    (("发票金额",), "invoice_amount"),
    (("支付金额", "资金支付"), "payment_amount"),
    (("建设进度", "工程进度", "施工进度"), "construction_progress"),
    (("产量", "产能"), "production_output"),
)

_DOCUMENT_TERMS = (
    "核准", "备案", "环评", "排污许可", "可研", "合同", "发票", "支付",
    "竣工", "验收", "能耗", "排放", "发电量", "设备", "产量", "土地",
    "并网", "施工", "监测", "台账", "营业执照", "财务报表", "审计报告",
)


def _record(value: Any) -> dict[str, Any]:
    """Return a plain row mapping for dict/sqlite-row/dataclass inputs."""

    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    to_record = getattr(value, "to_record", None)
    if callable(to_record):
        return dict(to_record())
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {
            name: getattr(value, name)
            for name in dir(value)
            if not name.startswith("_") and not callable(getattr(value, name))
        }


def _rows(values: Any) -> list[dict[str, Any]]:
    """Normalise a row, keyed row mapping, or iterable of rows."""

    if values is None:
        return []
    if hasattr(values, "keys") and not isinstance(values, Mapping):
        # ``sqlite3.Row`` exposes ``keys`` but does not register as Mapping.
        return [_record(values)]
    if isinstance(values, Mapping):
        if "industry_code" in values or any(
            key in values
            for key in (
                "phase36_item_id", "application_mapping_id",
                "evidence_requirement_id", "fact_id", "doc_id", "evidence_id",
            )
        ):
            return [dict(values)]
        return [_record(value) for value in values.values()]
    if isinstance(values, (str, bytes)):
        return []
    return [_record(value) for value in values]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().casefold() in {
        "1", "true", "yes", "y", "mock", "simulation",
    }


def _json_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [piece.strip() for piece in value.split(",") if piece.strip()]
    if not isinstance(parsed, (list, tuple, set)):
        return []
    return [str(item) for item in parsed if item not in (None, "")]


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if value not in (None, "")))


def _industry_code(case: Mapping[str, Any]) -> str | None:
    explicit = str(case.get("industry_code") or "").strip()
    if explicit in SUPPORTED_INDUSTRY_CODES:
        return explicit
    for field in ("primary_industry", "project_activity", "industry"):
        for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", str(case.get(field) or "")):
            if match.group(1) in SUPPORTED_INDUSTRY_CODES:
                return match.group(1)
    return None


def _is_mock(item: Mapping[str, Any]) -> bool:
    # ``lineage_kind=simulation`` alone is not enough: the explicit marker is
    # the authority used by persistence and presentation ("示例规则").
    return _truthy(item.get("is_mock"))


def _mock_item_valid(item: Mapping[str, Any]) -> bool:
    return (
        _is_mock(item)
        and str(item.get("lineage_kind") or "").casefold() == "simulation"
        and not _truthy(item.get("formal_density_eligible"))
        and str(item.get("validation_status") or "").casefold() != "qualified"
    )


def _is_postloan_case(case: Mapping[str, Any]) -> bool:
    machine_tokens = ("postloan", "post_loan", "post-loan", "monitoring")
    chinese_tokens = ("贷后", "存续期", "运营期", "投产运营", "还款期")
    loan_stage = str(case.get("loan_stage") or "").strip().casefold()
    if loan_stage:
        return any(token in loan_stage for token in (*machine_tokens, "贷后", "还款期"))
    fallback_stage = " ".join(
        str(case.get(field) or "") for field in ("project_stage", "status")
    ).casefold()
    return any(token in fallback_stage for token in (*machine_tokens, *chinese_tokens))


def _stage_applicable(case: Mapping[str, Any], stage_values: Iterable[Any]) -> bool:
    """Conservatively apply explicit loan/project stage restrictions."""

    stages = [str(value).strip() for value in stage_values if str(value or "").strip()]
    if not stages:
        return True
    requirement = "/".join(stages)
    if any(token in requirement for token in ("全流程", "各阶段", "全阶段", "按事项触发")):
        return True

    loan_stage = str(case.get("loan_stage") or "").strip()
    mentioned_loan_stages = [token for token in ("贷前", "贷中", "贷后") if token in requirement]
    if mentioned_loan_stages and loan_stage:
        return any(token in loan_stage for token in mentioned_loan_stages)

    project_stage = str(case.get("project_stage") or "").strip()
    if not project_stage:
        return True
    stage_groups = {
        "设计": ("设计", "立项", "登记", "审批", "建设前"),
        "准备": ("设计", "立项", "登记", "审批", "建设前", "准备"),
        "建设": ("建设", "实施", "施工"),
        "投产": ("投产", "运行", "运营", "核查", "排污"),
        "运行": ("投产", "运行", "运营", "核查", "排污"),
        "运营": ("投产", "运行", "运营", "核查", "排污"),
    }
    for case_token, accepted_tokens in stage_groups.items():
        if case_token in project_stage:
            return any(token in requirement for token in accepted_tokens)
    # Unknown free-text stages are not guessed into inapplicability.
    return True


def _unmet_gates(assessment: Mapping[str, Any]) -> list[Any]:
    value = assessment.get("unmet_gates")
    if value is None:
        value = assessment.get("unmet_gates_json")
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _density_allows_module(
    assessment: Mapping[str, Any] | None,
    module: str,
) -> bool:
    """Check assessment coherence without hiding valid rules in other modules.

    ``formal_density_eligible`` is an item-level result produced by the density
    assessor.  A package-wide 100% gate must not suppress such a row merely
    because an unrelated module is incomplete.  When per-module counts are
    available, however, a zero-qualified count is an explicit contradiction.
    """

    if not assessment:
        return False
    counts = _json_object(
        assessment.get("module_counts") or assessment.get("module_counts_json")
    )
    module_count = counts.get(module)
    if isinstance(module_count, Mapping) and "qualified" in module_count:
        try:
            return int(module_count.get("qualified") or 0) > 0
        except (TypeError, ValueError):
            return False
    return True


def _formal_item_qualified(item: Mapping[str, Any]) -> bool:
    return (
        _truthy(item.get("formal_density_eligible"))
        and str(item.get("validation_status") or "").casefold() == "qualified"
        and str(item.get("lineage_kind") or "").casefold() != "simulation"
    )


def _underlying(item: Mapping[str, Any]) -> dict[str, Any]:
    record = item.get("record")
    if isinstance(record, Mapping):
        return {**dict(item), **dict(record)}
    if isinstance(record, str):
        try:
            parsed = json.loads(record)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping):
            return {**dict(item), **dict(parsed)}
    return dict(item)


def _master_record_index(
    master_records: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Index Phase 3.5 business rows referenced by raw Phase 3.6 items."""

    if not master_records:
        return {}
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for table, key_name in dict.fromkeys(MODULE_RECORD_KEYS.values()):
        if table not in master_records:
            continue
        for row in _rows(master_records.get(table)):
            if row.get(key_name):
                indexed[(table, str(row[key_name]))] = row
    return indexed


def _rule_text(item: Mapping[str, Any], mapping: Mapping[str, Any]) -> str:
    row = _underlying(item)
    for field in (
        "threshold_text", "requirement_text", "risk_description", "review_focus",
        "definition_text", "content", "applicability", "title", "risk_title",
        "permit_name", "document_name", "evidence_object", "indicator_name", "term",
    ):
        if row.get(field):
            return str(row[field]).strip()
    return str(mapping.get("verification_item_template") or "待核验行业规则").strip()


def _rule_name(item: Mapping[str, Any]) -> str:
    row = _underlying(item)
    for field in (
        "risk_title", "permit_name", "document_name", "evidence_object",
        "indicator_name", "threshold_text", "term", "title",
    ):
        if row.get(field):
            return str(row[field]).strip()
    return str(item.get("record_id") or item.get("phase36_item_id") or "规则项")


def _dimension(item: Mapping[str, Any], evidence_rows: Iterable[Mapping[str, Any]]) -> RiskDimension:
    module = str(item.get("module") or "")
    if module == "postloan":
        return RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE
    text = " ".join(
        [_rule_text(item, {})]
        + [
            " ".join(
                str(row.get(field) or "")
                for field in ("evidence_object", "requirement_text", "acceptable_evidence")
            )
            for row in evidence_rows
        ]
    )
    if any(token in text for token in ("融资用途", "资金用途", "项目边界", "合同", "发票")):
        return RiskDimension.PROJECT_BOUNDARY_AND_USE
    if any(token in text for token in ("建设进度", "施工进度", "支付", "拨付", "实施")):
        return RiskDimension.IMPLEMENTATION_AND_FUNDS
    if any(token in text for token in ("贷后", "实际绩效", "持续合规", "运营", "偏离")):
        return RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE
    return RiskDimension.TECHNICAL_AND_COMPLIANCE


def _candidate_fact_categories(item: Mapping[str, Any], evidence_rows: Iterable[Mapping[str, Any]]) -> set[str]:
    row = _underlying(item)
    categories = {
        str(row[field])
        for field in ("fact_category", "metric", "indicator_key")
        if row.get(field)
    }
    text = " ".join(
        str(row.get(field) or "")
        for field in (
            "threshold_text", "requirement_text", "risk_description", "review_focus",
            "definition_text", "content", "indicator_name", "evidence_object",
        )
    )
    text += " " + " ".join(
        " ".join(
            str(req.get(field) or "")
            for field in ("evidence_object", "requirement_text", "acceptable_evidence")
        )
        for req in evidence_rows
    )
    for aliases, category in _FACT_ALIASES:
        if any(alias in text for alias in aliases):
            categories.add(category)
    return categories


def _linked_requirement_ids(row: Mapping[str, Any]) -> set[str]:
    linked: set[str] = set()
    for field in (
        "evidence_requirement_id", "required_evidence_id", "requirement_id",
        "evidence_requirement_ids", "required_evidence_ids",
        "evidence_requirement_ids_json", "required_evidence_ids_json",
    ):
        value = row.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, (list, tuple, set)) or field.endswith("_json"):
            linked.update(_json_list(value))
        else:
            linked.add(str(value))
    return linked


def _terms(requirement: Mapping[str, Any]) -> tuple[str, ...]:
    text = " ".join(
        str(requirement.get(field) or "")
        for field in (
            "evidence_object", "requirement_text", "acceptable_evidence",
        )
    )
    return tuple(term for term in _DOCUMENT_TERMS if term in text)


def _haystack(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(field) or "")
        for field in (
            "file_name", "file_type", "document_type", "title", "raw_excerpt",
            "table_cell", "scope_text", "raw_value", "match_basis",
        )
    ).replace(" ", "")


def _conflict_value(conflict: Any, name: str) -> Any:
    if isinstance(conflict, Mapping):
        return conflict.get(name)
    return getattr(conflict, name, None)


def _has_conflict(
    conflicts: Iterable[ConflictCandidate | Mapping[str, Any]],
    fact_ids: set[str],
    evidence_ids: set[str],
) -> bool:
    for conflict in conflicts:
        conflict_fact_ids = {
            str(value)
            for value in (
                _conflict_value(conflict, "fact_a_id"),
                _conflict_value(conflict, "fact_b_id"),
            )
            if value not in (None, "")
        }
        conflict_evidence_ids = {
            str(value)
            for value in (
                _conflict_value(conflict, "evidence_a_id"),
                _conflict_value(conflict, "evidence_b_id"),
            )
            if value not in (None, "")
        }
        if conflict_fact_ids & fact_ids or conflict_evidence_ids & evidence_ids:
            return True
    return False


def _semantic_key(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _task_bundle_key(
    *,
    case_id: str,
    task_type: str | None,
    item_id: str,
    missing_ids: tuple[str, ...],
) -> str | None:
    """Return the stable grouping key used for merged evidence-gap tasks."""

    if not task_type:
        return None
    # Shared gaps should produce one task across several rules.  If a rule has
    # no gap, retain the item ID so unrelated manual reviews are not collapsed.
    grouping_value = ",".join(sorted(missing_ids)) if missing_ids else item_id
    return _semantic_key("phase36_task_bundle", case_id, task_type, grouping_value)


def _make_candidate(**values: Any) -> VerificationCandidate:
    """Construct against both the current and the extended contract.

    ``contracts.VerificationCandidate`` is being extended by the integration
    layer.  The compatibility branch keeps this standalone module testable
    before that additive contract change lands; it disappears naturally once
    those fields are declared on the dataclass.
    """

    declared = {field.name for field in fields(VerificationCandidate)}
    candidate = VerificationCandidate(
        **{key: value for key, value in values.items() if key in declared}
    )
    for key, value in values.items():
        if key not in declared:
            object.__setattr__(candidate, key, value)
    return candidate


def materialize_case_rule_candidates(
    *,
    case: Mapping[str, Any] | Any,
    phase36_items: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    application_mappings: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    evidence_requirements: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    density_assessments: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    master_records: Mapping[str, Any] | None = None,
    facts: Iterable[Mapping[str, Any]] = (),
    documents: Iterable[Mapping[str, Any]] = (),
    evidence: Iterable[Mapping[str, Any]] = (),
    conflicts: Iterable[ConflictCandidate | Mapping[str, Any]] = (),
    fact_evidence_links: Iterable[Mapping[str, Any]] = (),
    rule_application_evidence_links: Iterable[Mapping[str, Any]] = (),
) -> list[VerificationCandidate]:
    """Build traceable case verification candidates from a Phase 3.6 pack.

    Formal rules require both an item-level qualification and a passing
    industry density assessment.  Explicit mock rows bypass only that density
    gate; they retain the exact same mapping/evidence path and always remain
    pending when applicable.
    """

    case_row = _record(case)
    industry_code = _industry_code(case_row)
    if industry_code is None:
        return []
    case_id = str(case_row.get("case_id") or "")

    assessments = {
        str(row.get("industry_code") or ""): row
        for row in _rows(density_assessments)
    }
    density_assessment = assessments.get(industry_code)
    supplied_master_records = dict(master_records or {})
    supplied_master_records.setdefault("evidence_requirements", evidence_requirements)
    business_records = _master_record_index(supplied_master_records)

    mappings = {
        str(row.get("phase36_item_id") or ""): row
        for row in _rows(application_mappings)
        if str(row.get("industry_code") or industry_code) == industry_code
    }
    requirements = {
        str(row.get("evidence_requirement_id") or ""): row
        for row in _rows(evidence_requirements)
        if str(row.get("industry_code") or industry_code) == industry_code
    }

    def same_case(row: Mapping[str, Any]) -> bool:
        return not case_id or not row.get("case_id") or str(row.get("case_id")) == case_id

    fact_rows = [row for row in _rows(facts) if same_case(row)]
    document_rows = [row for row in _rows(documents) if same_case(row)]
    evidence_rows = [row for row in _rows(evidence) if same_case(row)]
    conflict_rows: list[dict[str, Any]] = []
    for conflict in conflicts:
        row = _record(conflict)
        if not same_case(row):
            continue
        is_current = row.get("is_current")
        if str("1" if is_current is None else is_current).casefold() in {
            "0", "false", "no",
        }:
            continue
        conflict_rows.append(row)
    link_rows = [row for row in _rows(fact_evidence_links)]
    mapping_requirement_ids: dict[str, list[str]] = defaultdict(list)
    for link in _rows(rule_application_evidence_links):
        if link.get("application_mapping_id") and link.get("evidence_requirement_id"):
            mapping_requirement_ids[str(link["application_mapping_id"])].append(
                str(link["evidence_requirement_id"])
            )

    facts_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in fact_rows:
        if fact.get("fact_category"):
            facts_by_category[str(fact["fact_category"])].append(fact)

    evidence_by_id = {
        str(row.get("evidence_id")): row
        for row in evidence_rows
        if row.get("evidence_id")
    }
    evidence_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        if row.get("doc_id"):
            evidence_by_doc[str(row["doc_id"])].append(row)
    evidence_ids_by_fact: dict[str, set[str]] = defaultdict(set)
    for link in link_rows:
        if link.get("fact_id") and link.get("evidence_id"):
            evidence_ids_by_fact[str(link["fact_id"])].add(str(link["evidence_id"]))

    output: list[VerificationCandidate] = []
    ordered_items = sorted(
        _rows(phase36_items), key=lambda row: str(row.get("phase36_item_id") or "")
    )
    for item in ordered_items:
        if str(item.get("industry_code") or "") != industry_code:
            continue
        item_id = str(item.get("phase36_item_id") or "")
        module = str(item.get("module") or "")
        if not item_id or module not in CONTEXT_MODULES | ACTIONABLE_MODULES:
            continue
        expected_table, _ = MODULE_RECORD_KEYS[module]
        if str(item.get("record_table") or "") != expected_table:
            continue
        business_record = business_records.get(
            (expected_table, str(item.get("record_id") or ""))
        )
        if not business_record:
            continue
        if str(business_record.get("industry_code") or "") != industry_code:
            continue
        if (
            business_record.get("source_id")
            and str(business_record.get("source_id")) != str(item.get("source_id") or "")
        ):
            continue
        if business_record.get("scope_status") not in (None, "core"):
            continue
        if module in {"process", "equipment", "route"} and str(
            business_record.get("module") or ""
        ) != module:
            continue
        mock = _is_mock(item)
        if mock and not _mock_item_valid(item):
            continue
        if not mock and not (
            _formal_item_qualified(item)
            and _density_allows_module(density_assessment, module)
        ):
            continue

        hydrated_item = {**item, "record": business_record}

        mapping = mappings.get(item_id)
        # The mapping is part of the common formal/mock schema.  Loading a row
        # without it would invent both a verification template and a task.
        if not mapping or not mapping.get("application_mapping_id"):
            continue

        declared_ids = _unique(_json_list(mapping.get("evidence_requirement_ids_json")))
        normalized_ids = _unique(
            mapping_requirement_ids.get(str(mapping["application_mapping_id"]), [])
        )
        if declared_ids and normalized_ids and set(declared_ids) != set(normalized_ids):
            continue
        required_ids = declared_ids or normalized_ids
        linked_requirements = [requirements[value] for value in required_ids if value in requirements]
        missing_requirement_rows = [value for value in required_ids if value not in requirements]

        if module in {"permit", "document", "evidence"}:
            applicable_stages = [
                _underlying(hydrated_item).get("applicable_stage"),
                *(row.get("applicable_stage") for row in linked_requirements),
            ]
            # Out-of-stage rows do not enter the case at all.  This preserves
            # the mock invariant that every materialised mock stays pending.
            if not _stage_applicable(case_row, applicable_stages):
                continue

        fact_categories = _candidate_fact_categories(hydrated_item, linked_requirements)
        matched_facts = [
            fact
            for category in sorted(fact_categories)
            for fact in facts_by_category.get(category, [])
        ]
        fact_ids = {
            str(fact["fact_id"]) for fact in matched_facts if fact.get("fact_id")
        }

        matched_project_evidence: set[str] = set()
        covered_requirement_ids: set[str] = set()
        matched_document_names: set[str] = set()
        for requirement in linked_requirements:
            requirement_id = str(requirement["evidence_requirement_id"])
            terms = _terms(requirement)
            explicitly_linked = {
                str(row["evidence_id"])
                for row in evidence_rows
                if row.get("evidence_id")
                and requirement_id in _linked_requirement_ids(row)
            }
            explicit_document_ids = {
                str(row["doc_id"])
                for row in document_rows
                if row.get("doc_id")
                and requirement_id in _linked_requirement_ids(row)
            }
            heuristic_documents = [
                row
                for row in document_rows
                if terms and any(term in _haystack(row) for term in terms)
            ]
            heuristic_document_ids = {
                str(row["doc_id"])
                for row in heuristic_documents
                if row.get("doc_id")
            }
            for row in heuristic_documents:
                if row.get("file_name"):
                    matched_document_names.add(str(row["file_name"]))
            document_ids = explicit_document_ids | heuristic_document_ids
            document_evidence = {
                str(row["evidence_id"])
                for doc_id in document_ids
                for row in evidence_by_doc.get(doc_id, [])
                if row.get("evidence_id")
            }
            text_evidence = {
                str(row["evidence_id"])
                for row in evidence_rows
                if row.get("evidence_id")
                and terms
                and any(term in _haystack(row) for term in terms)
            }
            found = explicitly_linked | document_evidence | text_evidence
            # Filename/text heuristics identify candidate pages for assisted
            # reading; only an explicit requirement link can close the gap.
            if explicitly_linked:
                covered_requirement_ids.add(requirement_id)
            if found:
                matched_project_evidence.update(found)

        for fact_id in fact_ids:
            matched_project_evidence.update(evidence_ids_by_fact.get(fact_id, set()))
        # Do not persist dangling IDs supplied by malformed links.
        matched_project_evidence.intersection_update(evidence_by_id)

        missing_evidence_ids = [
            requirement_id
            for requirement_id in required_ids
            if requirement_id not in covered_requirement_ids
        ]
        conflict_found = _has_conflict(
            conflict_rows, fact_ids, matched_project_evidence
        )
        source_locator = str(item.get("source_locator") or "").strip()
        rule_name = _rule_name(hydrated_item)
        requirement_text = _rule_text(hydrated_item, mapping)

        # A mock-backed verification row is database-guarded to stay strictly
        # ``pending_verification``.  An out-of-stage mock therefore does not
        # materialise at all; the indicator definition remains available for
        # later loan-stage loading without creating a misleading status row.
        if mock and module == "postloan" and not _is_postloan_case(case_row):
            continue

        if module == "postloan" and not _is_postloan_case(case_row):
            status = VerificationStatus.NOT_APPLICABLE.value
            reason = "当前案件尚未进入贷后/运营监测阶段；保留指标定义但不生成任务。"
            next_action = None
            prescribed_task_type = None
        elif module in CONTEXT_MODULES and not mock:
            status = VerificationStatus.ATTRIBUTE_ONLY.value
            reason = "该条目用于行业上下文与辅助阅读，不直接形成核验结论或任务。"
            next_action = None
            prescribed_task_type = None
        else:
            # Mock rows are deliberately pinned here.  Formal rows may surface
            # a conflict, but never auto-pass merely because evidence exists.
            status = (
                VerificationStatus.PENDING_VERIFICATION.value
                if mock or not conflict_found
                else VerificationStatus.EVIDENCE_CONFLICT.value
            )
            prescribed_task_type = (
                None if module in CONTEXT_MODULES else str(mapping.get("task_type") or "") or None
            )
            reason_parts = [
                "示例规则仅用于演示连接能力，必须由人工核实。"
                if mock
                else "正式规则已匹配案件，仍须人工核实项目事实与原始证据。"
            ]
            if conflict_found:
                reason_parts.append("关联事实或证据存在跨文件冲突，禁止自动判定通过。")
            if missing_evidence_ids:
                names = [
                    str(requirements[value].get("evidence_object") or value)
                    if value in requirements else value
                    for value in missing_evidence_ids
                ]
                reason_parts.append("证据缺口：" + "、".join(names) + "。")
            elif required_ids:
                reason_parts.append("已发现候选材料，但材料存在不等于规则满足，需核对原文页码与口径。")
            else:
                reason_parts.append("应用映射尚未配置证据清单，需人工补充核验依据。")
            if missing_requirement_rows:
                reason_parts.append(
                    "证据主数据缺失：" + "、".join(missing_requirement_rows) + "。"
                )
            reason = "".join(reason_parts)

            actions: list[str] = []
            if missing_evidence_ids:
                actions.append("补充所列原始材料并保留文件哈希、页码和摘录")
            elif matched_project_evidence:
                actions.append("打开候选证据逐项核对主体、范围、版本、期间与统计口径")
            else:
                actions.append("按规则映射补充可定位的项目事实与原始证据")
            if conflict_found:
                actions.append("先核对冲突原文及有效版本，再重新计算")
            if source_locator:
                actions.append(f"对照规则原文定位“{source_locator}”")
            next_action = "；".join(actions) + "。"

        underlying = _underlying(hydrated_item)
        why_verify = str(
            underlying.get("why_verify")
            or underlying.get("risk_description")
            or _MODULE_WHY.get(module)
            or "帮助客户经理理解行业规则与项目事实的对应关系。"
        )
        customer_manager_focus = str(
            underlying.get("customer_manager_focus")
            or underlying.get("review_focus")
            or underlying.get("status_note")
            or next(
                (
                    req.get("acceptable_evidence")
                    for req in linked_requirements
                    if req.get("acceptable_evidence")
                ),
                None,
            )
            or (
                "关注材料主体、项目范围、版本、有效期、统计期间、单位和原文页码。"
            )
        )
        if matched_document_names:
            customer_manager_focus += " 已发现候选文件：" + "、".join(
                sorted(matched_document_names)
            ) + "；仍需打开原文核实。"

        legacy_master_type = {
            "threshold": "threshold",
            "permit": "permit",
            "document": "document",
            "evidence": "evidence",
            "risk": "industry_risk",
        }.get(module)
        missing_ids_tuple = _unique(missing_evidence_ids)
        task_bundle_key = _task_bundle_key(
            case_id=case_id,
            task_type=prescribed_task_type,
            item_id=item_id,
            missing_ids=missing_ids_tuple,
        )
        output.append(_make_candidate(
            semantic_key=_semantic_key(
                "phase36", case_id, item_id, mapping.get("application_mapping_id")
            ),
            rule_version_id=None,
            dimension=_dimension(hydrated_item, linked_requirements),
            requirement_text=requirement_text,
            status=status,
            applicability_reason=reason,
            next_action=next_action,
            fact_ids=_unique(sorted(fact_ids)),
            evidence_ids=_unique(sorted(matched_project_evidence)),
            # Keep the legacy field within its persisted CHECK constraint;
            # ``module`` carries the complete Phase 3.6 vocabulary.
            master_rule_type=legacy_master_type,
            master_rule_id=str(item.get("record_id") or item_id),
            source_manifest_id=(
                str(item.get("source_id")) if item.get("source_id") else None
            ),
            phase36_item_id=item_id,
            application_mapping_id=str(mapping["application_mapping_id"]),
            source_locator=source_locator or None,
            prescribed_task_type=prescribed_task_type,
            required_evidence_ids=required_ids,
            missing_evidence_ids=missing_ids_tuple,
            task_bundle_key=task_bundle_key,
            is_mock=mock,
            module=module,
            why_verify=why_verify,
            customer_manager_focus=customer_manager_focus,
        ))

    return output


# Descriptive aliases ease integration without creating a service dependency.
build_phase36_verification_candidates = materialize_case_rule_candidates
materialize_rule_candidates = materialize_case_rule_candidates


__all__ = [
    "ACTIONABLE_MODULES",
    "CONTEXT_MODULES",
    "MODULE_RECORD_KEYS",
    "SUPPORTED_INDUSTRY_CODES",
    "build_phase36_verification_candidates",
    "materialize_case_rule_candidates",
    "materialize_rule_candidates",
]
