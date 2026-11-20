"""Read-only assessment of source-backed public industry module coverage.

One covered module contributes one twelfth of the percentage, regardless of its
row count.  This is *coverage*, not a claim that a module is exhaustive or that a
loan can be approved.  Classification, catalogue mappings, and cached profile
prose contribute no points.  A manual coverage review is additionally required
before a fully covered profile can be labelled ``depth_public_sources``.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


MODULE_LABELS = {
    "process": "典型生产/服务流程",
    "equipment": "核心设备与设施",
    "standard": "技术标准全文",
    "indicator": "行业指标",
    "threshold": "明文数值阈值",
    "permit": "行业专属审批许可",
    "document": "明文申请材料要求",
    "evidence": "证据要求",
    "risk": "高频风险点",
    "term": "行业术语",
    "postloan": "贷后指标",
    "route": "技术路线",
}

_TABLES = {
    "standard": "industry_standard_links",
    "indicator": "indicator_definitions",
    "threshold": "threshold_definitions",
    "permit": "permit_requirements",
    "document": "document_requirements",
    "evidence": "evidence_requirements",
    "risk": "industry_risk_points",
    "term": "term_cards",
    "postloan": "postloan_indicator_definitions",
}

# These are required *fields*, not invented minimum row counts.  In particular,
# evidence must identify acceptable proof and post-loan monitoring must say what
# is observed, when it is observed, and which evidence supports it.
_REQUIRED_FIELDS = {
    "process": ("title", "content"),
    "equipment": ("title", "content"),
    "route": ("title", "content"),
    "standard": ("applicability",),
    "indicator": ("indicator_name", "definition_text"),
    "threshold": ("threshold_text",),
    "permit": ("permit_name", "requirement_text", "applicable_stage"),
    "document": ("document_name", "requirement_text", "applicable_stage"),
    "evidence": ("evidence_object", "requirement_text", "acceptable_evidence"),
    "risk": ("risk_title", "risk_description", "review_focus"),
    "term": ("term", "definition_text"),
    "postloan": ("indicator_name", "definition_text", "frequency", "evidence_object"),
}

_NUMERIC = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_COMPARATORS = {
    "<", "<=", ">", ">=", "=", "==", "≤", "≥", "＜", "＞", "＝", "≦", "≧",
    "lt", "lte", "le", "gt", "gte", "ge", "eq", "小于", "不大于", "不高于", "低于",
    "不超过", "至多", "大于", "不小于", "不低于", "高于", "至少", "等于", "达到",
    "标杆水平", "基准水平", "先进水平", "标杆值", "基准值", "先进值", "限额值", "限值",
    "准入值", "限定值", "benchmark", "baseline", "upper_bound", "lower_bound",
}
_PLACEHOLDERS = {
    "", "-", "—", "--", "n/a", "na", "none", "null", "未知", "待补充", "待核验", "待核实",
    "待复核", "未获取", "未提供", "暂无", "不详", "待确认", "公开渠道未获取全文，当前仅登记公开可见信息。",
}
BANK_RULE_GAP = "银行内部规则未接入，无法判断。"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _present(value: Any) -> bool:
    return _text(value).lower() not in _PLACEHOLDERS


def _rows(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, params)
    names = [item[0] for item in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _date_issue(record: dict[str, Any], today: date) -> str | None:
    for field, future in (("published_at", True), ("effective_at", True), ("expires_at", False)):
        value = _text(record.get(field))
        if not value:
            continue
        try:
            parsed = date.fromisoformat(value[:10])
        except ValueError:
            return "来源或条目日期无法核验"
        if future and parsed > today:
            return "来源或条目尚未发布/生效"
        if not future and parsed < today:
            return "来源或条目已过有效期"
    return None


def _source_issue(source: dict[str, Any] | None, today: date, *, full_text: bool = False) -> str | None:
    if not source:
        return "缺少可核验来源"
    if source.get("formal_rule_eligible") != 1:
        return "来源未确认可作为现行正式依据"
    if source.get("superseded_by_source_id") or source.get("availability_status") == "superseded":
        return "来源已被替代或废止"
    allowed = {"full_text_obtained"} if full_text else {"full_text_obtained", "official_summary_only"}
    if source.get("availability_status") not in allowed:
        return "来源公开内容未取得" if not full_text else "标准来源未取得全文"
    standard_no = re.sub(r"\s+", "", _text(source.get("standard_no"))).upper()
    if re.match(r"GB/?T?4754(?:\D|$)", standard_no) or "annotation" in _text(source.get("authority_level")).lower():
        return "分类定义和分类注释不计行业内容覆盖"
    return _date_issue(source, today)


def _row_issue(row: dict[str, Any], sources: dict[str, dict[str, Any]], today: date) -> str | None:
    scope = row.get("scope_status", "unreviewed")
    if scope == "adjacent":
        return "相邻活动内容不计本行业覆盖"
    if scope != "core":
        return "本行业核心适用范围尚未复核"
    derivation = _text(row.get("derivation_type"))
    if derivation and derivation not in {"policy_explicit", "source_derived"}:
        return "派生方式未确认或属于相邻活动"
    if not (_present(row.get("source_page")) or _present(row.get("source_locator"))):
        return "缺少来源页码或原文定位"
    return _source_issue(sources.get(_text(row.get("source_id"))), today) or _date_issue(row, today)


def _threshold_issue(row: dict[str, Any]) -> str | None:
    if _text(row.get("threshold_kind")) != "explicit_numeric":
        return "未标记为政策明文数值阈值（文字条件和待拆分记录不计）"
    value = _text(row.get("threshold_value"))
    if not _NUMERIC.fullmatch(value):
        return "阈值未拆分为有限纯数值（文字、标准号和复合字符串不计）"
    try:
        if not Decimal(value).is_finite():
            return "阈值不是有限数值"
    except InvalidOperation:
        return "阈值不是有限数值"
    if not _present(row.get("unit")):
        return "数值阈值缺少单位"
    operator = _text(row.get("operator")).lower()
    if operator not in _COMPARATORS and not re.fullmatch(r"[一二三四五六七八九十0-9]+级(?:水平|限值|能效)?", operator):
        return "数值阈值缺少明确比较或分档含义"
    return None


def _content_issue(
    module: str, row: dict[str, Any], standards: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]], today: date,
) -> str | None:
    missing = [field for field in _REQUIRED_FIELDS[module] if not _present(row.get(field))]
    if missing:
        return "缺少实质内容字段：" + "、".join(missing)
    if module == "threshold":
        return _threshold_issue(row)
    if module == "standard":
        standard = standards.get(_text(row.get("standard_id")))
        if not standard:
            return "缺少标准登记记录"
        if standard.get("full_text_status") == "official_summary_only":
            return "仅取得官方摘要，技术标准全文仍有缺口"
        if standard.get("full_text_status") != "full_text_obtained":
            return "仅登记引用或公开渠道未取得技术标准全文"
        if not _present(standard.get("standard_no")) or not _present(standard.get("standard_name")):
            return "标准名称或标准号不完整"
        return _source_issue(sources.get(_text(standard.get("source_id"))), today, full_text=True) or _date_issue(standard, today)
    return None


def assess_profile(connection: sqlite3.Connection, industry_code: str) -> dict[str, Any]:
    """Return an auditable twelve-module assessment without writing to SQLite.

    Missing tables/columns in older databases fail closed. ``raw_count`` counts
    registered items (unique standards for the standard module);
    ``qualified_count`` requires core scope, usable current source, a locator,
    and the module's substantive fields. Adjacent/unreviewed records remain
    visible as raw records. Even 100% means only public-module coverage.
    """
    code = str(industry_code).strip()
    today = date.today()
    tables = {row["name"] for row in _rows(connection, "SELECT name FROM sqlite_master WHERE type='table'")}

    def industry_rows(table: str) -> list[dict[str, Any]]:
        return _rows(connection, f"SELECT * FROM {table} WHERE industry_code=?", (code,)) if table in tables else []

    sources = {row["source_id"]: row for row in _rows(connection, "SELECT * FROM source_manifest")} if "source_manifest" in tables else {}
    standards = {row["standard_id"]: row for row in _rows(connection, "SELECT * FROM standard_catalog")} if "standard_catalog" in tables else {}
    knowledge = industry_rows("industry_knowledge_items")
    modules: dict[str, dict[str, Any]] = {}
    for module, label in MODULE_LABELS.items():
        rows = [row for row in knowledge if row.get("module") == module] if module in {"process", "equipment", "route"} else industry_rows(_TABLES[module])
        # Multiple applicability links to one standard are one standard, and a
        # reviewed core applicability can qualify even if another is adjacent.
        groups: dict[str, list[dict[str, Any]]] = {}
        for index, row in enumerate(rows):
            key = _text(row.get("standard_id")) if module == "standard" else str(index)
            groups.setdefault(key or f"missing:{index}", []).append(row)
        qualified = 0
        issues: Counter[str] = Counter()
        for group in groups.values():
            failures = []
            for row in group:
                issue = _row_issue(row, sources, today) or _content_issue(module, row, standards, sources, today)
                if issue is None:
                    qualified += 1
                    break
                failures.append(issue)
            else:
                issues["；".join(dict.fromkeys(failures))] += 1
        raw_count = len(groups)
        reasons = [f"{reason}（{count}条）" for reason, count in sorted(issues.items())]
        if qualified:
            reasons.insert(0, f"{qualified}条核心适用内容通过来源与字段校验；仅表示模块已覆盖，不表示内容齐全")
        elif not raw_count:
            reasons.append("尚未登记本模块公开内容")
        modules[module] = {
            "label": label,
            "raw_count": raw_count,
            "qualified_count": qualified,
            "status": "covered" if qualified else "unqualified" if raw_count else "missing",
            "reason": "；".join(reasons),
        }

    covered = sum(module["qualified_count"] > 0 for module in modules.values())
    profiles = industry_rows("industry_rule_profiles")
    reviewed = bool(profiles) and all(row.get("coverage_review_status") == "reviewed" for row in profiles)
    if code == "5413" or not covered:
        build_status = "base_only"
    elif covered == len(MODULE_LABELS) and reviewed:
        build_status = "depth_public_sources"
    else:
        build_status = "partial_public_sources"
    return {
        "completion_percent": round(covered * 100 / len(MODULE_LABELS)),
        "build_status": build_status,
        "missing_modules": [module["label"] for module in modules.values() if not module["qualified_count"]] + [BANK_RULE_GAP],
        "modules": modules,
        "covered_module_count": covered,
        "total_module_count": len(MODULE_LABELS),
        "coverage_review_status": "reviewed" if reviewed else "unreviewed",
        "coverage_note": "百分比仅表示12个公开内容模块的覆盖情况；100%不代表行业规则齐全、项目合规或授信资料完整。银行内部规则不计入分母。",
    }
