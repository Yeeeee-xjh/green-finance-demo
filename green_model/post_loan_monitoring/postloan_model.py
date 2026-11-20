#!/usr/bin/env python3
"""绿色信贷贷后：资金用途、项目进度、环境绩效与环境合规事件的动态预警。

仅使用 Python 标准库。输出是供贷后人员复核的风险线索，不是违约、漂绿或处罚结论。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "weights": {
        "fund_use": 0.30,
        "project_progress": 0.25,
        "environmental_performance": 0.25,
        "compliance_events": 0.20
    },
    "thresholds": {
        "yellow": 30,
        "orange": 55,
        "red": 75,
        "low_confidence": 0.40,
        "persistence_axis_score": 40,
        "persistence_periods": 2
    },
    "fund_use": {
        "warning_diversion_ratio": 0.01,
        "critical_diversion_ratio": 0.10,
        "warning_unverified_ratio": 0.15,
        "critical_unverified_ratio": 0.40
    },
    "progress": {
        "warning_delay_ratio": 0.10,
        "critical_delay_ratio": 0.35
    },
    "kpi_defaults": {
        "warning_deviation_ratio": 0.15,
        "critical_deviation_ratio": 0.40
    },
    "event_scores": {
        "environmental_penalty": {"low": 25, "medium": 55, "high": 85, "critical": 100},
        "permit_change": {"low": 20, "medium": 50, "high": 80, "critical": 100},
        "environmental_accident": {"low": 35, "medium": 70, "high": 95, "critical": 100},
        "shutdown_or_rectification": {"low": 35, "medium": 65, "high": 90, "critical": 100},
        "false_disclosure": {"low": 40, "medium": 70, "high": 95, "critical": 100},
        "environmental_litigation": {"low": 20, "medium": 50, "high": 80, "critical": 100},
        "negative_media": {"low": 10, "medium": 25, "high": 45, "critical": 60},
        "other": {"low": 10, "medium": 30, "high": 60, "critical": 85}
    },
    "hard_red_events": [
        "confirmed_fund_diversion",
        "permit_revoked",
        "major_environmental_accident",
        "confirmed_false_disclosure"
    ]
}


def clamp(x: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(x)))


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def ratio_score(value: float, warning: float, critical: float) -> float:
    """把偏离比例线性映射到 0—100；warning 对应30分，critical对应80分。"""
    value = max(0.0, value)
    if value <= 0:
        return 0.0
    if value <= warning:
        return 30.0 * value / max(warning, 1e-9)
    if value <= critical:
        return 30.0 + 50.0 * (value - warning) / max(critical - warning, 1e-9)
    return clamp(80.0 + 20.0 * (value - critical) / max(critical, 1e-9))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_source_path(input_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (input_path.parent / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"数据源不存在：{path}")
    return path


def load_bank_transactions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"transaction_date", "transaction_type", "amount"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"银行流水缺少列：{sorted(missing)}")
    return rows


def load_preloan_profile(path: Path, case: dict) -> dict:
    if path.suffix.lower() == ".json":
        return load_json(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("贷前画像仅支持JSON或CSV")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selector = case.get("preloan_selector") or {}
    stock_code = str(selector.get("stock_code") or case.get("stock_code") or "").strip()
    company_name = str(selector.get("company_name") or case.get("company_name") or "").strip()
    report_year = str(selector.get("report_year") or "").strip()
    matched = []
    for row in rows:
        code_ok = stock_code and str(row.get("stock_code", "")).strip().zfill(6) == stock_code.zfill(6)
        name_ok = company_name and str(row.get("company_name", "")).strip() == company_name
        if code_ok or name_ok:
            if not report_year or str(row.get("report_year", "")).strip() == report_year:
                matched.append(row)
    if not matched:
        raise ValueError(f"贷前CSV中找不到企业：stock_code={stock_code!r}, company_name={company_name!r}, report_year={report_year!r}")
    matched.sort(key=lambda x: str(x.get("report_year", "")))
    return matched[-1]


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def inject_bank_flow(case: dict, rows: list[dict]) -> None:
    """按每个监测截止日累计汇总脱敏流水；不会覆盖输入中手工填写的字段。"""
    for period in case.get("monitoring_periods", []):
        as_of = str(period.get("as_of_date", ""))
        available = [x for x in rows if str(x.get("transaction_date", "")) <= as_of]
        disbursed = 0.0
        confirmed_ineligible = 0.0
        unverified = 0.0
        account_exception = False
        for row in available:
            amount = number(row.get("amount")) or 0.0
            tx_type = str(row.get("transaction_type", "")).strip().lower()
            eligibility = str(row.get("eligibility_status", "unknown")).strip().lower()
            verification = str(row.get("verification_status", "unverified")).strip().lower()
            if tx_type == "disbursement":
                disbursed += amount
            elif tx_type in {"payment", "spend", "expense"}:
                if eligibility == "ineligible" and verification == "verified":
                    confirmed_ineligible += amount
                elif eligibility in {"unknown", "unverified", ""} or verification != "verified":
                    unverified += amount
            account_exception = account_exception or bool_value(row.get("special_account_exception"))
        fund = period.setdefault("fund_use", {})
        fund.setdefault("cumulative_disbursed", round(disbursed, 2))
        fund.setdefault("confirmed_ineligible_amount", round(confirmed_ineligible, 2))
        fund.setdefault("unverified_amount", round(unverified, 2))
        fund.setdefault("special_account_exception", account_exception)


def hydrate_case(case: dict, input_path: Path) -> dict:
    """根据source_paths接入贷前、贷中、合同和流水，不要求复制上游内容。"""
    case = deepcopy(case)
    source_paths = case.get("source_paths") or {}
    resolved = {}
    if source_paths.get("preloan_profile"):
        path = resolve_source_path(input_path, source_paths["preloan_profile"])
        case["preloan_profile"] = load_preloan_profile(path, case)
        resolved["preloan_profile"] = str(path)
    if source_paths.get("midloan_review"):
        path = resolve_source_path(input_path, source_paths["midloan_review"])
        case["midloan_review"] = load_json(path)
        resolved["midloan_review"] = str(path)
    if source_paths.get("contract"):
        path = resolve_source_path(input_path, source_paths["contract"])
        contract = load_json(path)
        case["contract_metadata"] = {k: v for k, v in contract.items() if k != "commitments"}
        case["commitments"] = contract.get("commitments", contract)
        resolved["contract"] = str(path)
    if source_paths.get("bank_transactions"):
        path = resolve_source_path(input_path, source_paths["bank_transactions"])
        inject_bank_flow(case, load_bank_transactions(path))
        resolved["bank_transactions"] = str(path)
    case["resolved_source_paths"] = resolved
    return case


def deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def evidence_ref(period: dict, field: str) -> list[dict]:
    refs = []
    for item in period.get("evidence_items", []):
        if field in item.get("supports", []):
            refs.append({
                "evidence_id": item.get("evidence_id"),
                "name": item.get("name"),
                "source": item.get("source"),
                "date": item.get("date"),
                "verification_status": item.get("verification_status", "unverified")
            })
    return refs


def evidence_factor(period: dict, field: str) -> float:
    """事实字段存在但证据未核验时仍可预警，只降低结论置信度。"""
    refs = evidence_ref(period, field)
    if not refs:
        return 0.60
    verified = sum(x["verification_status"] == "verified" for x in refs)
    return 0.60 + 0.40 * verified / len(refs)


def score_fund(period: dict, cfg: dict) -> dict:
    data = period.get("fund_use") or {}
    total = number(data.get("cumulative_disbursed"))
    diverted = number(data.get("confirmed_ineligible_amount"))
    unverified = number(data.get("unverified_amount"))
    issues, metrics = [], {}
    components = []
    if total is not None and total > 0 and diverted is not None:
        r = max(0.0, diverted / total)
        metrics["confirmed_diversion_ratio"] = round(r, 6)
        components.append(ratio_score(r, cfg["warning_diversion_ratio"], cfg["critical_diversion_ratio"]))
        if r > 0:
            issues.append(f"已核实不合格用途金额占累计投放 {r:.2%}")
    if total is not None and total > 0 and unverified is not None:
        r = max(0.0, unverified / total)
        metrics["unverified_fund_ratio"] = round(r, 6)
        # 未核实不是挪用：最高只贡献60分，并单独提示。
        components.append(min(60.0, ratio_score(r, cfg["warning_unverified_ratio"], cfg["critical_unverified_ratio"])))
        if r >= cfg["warning_unverified_ratio"]:
            issues.append(f"{r:.2%} 的累计资金尚缺合格用途凭证，不等同于已确认挪用")
    if data.get("special_account_exception") is True:
        components.append(65.0)
        issues.append("专项账户或资金闭环出现异常")
    confidence_fields = [total, diverted, unverified, data.get("special_account_exception")]
    confidence = sum(x is not None for x in confidence_fields) / len(confidence_fields)
    confidence *= evidence_factor(period, "fund_use")
    return {
        "score": round(max(components, default=0.0), 2),
        "confidence": round(confidence, 2),
        "metrics": metrics,
        "issues": issues,
        "evidence": evidence_ref(period, "fund_use")
    }


def score_progress(period: dict, cfg: dict) -> dict:
    data = period.get("project_progress") or {}
    planned = number(data.get("planned_progress_pct"))
    actual = number(data.get("actual_progress_pct"))
    issues, metrics, components = [], {}, []
    if planned is not None and actual is not None:
        delay = max(0.0, planned - actual) / max(planned, 20.0)
        metrics.update({"planned_progress_pct": planned, "actual_progress_pct": actual, "delay_ratio": round(delay, 6)})
        components.append(ratio_score(delay, cfg["warning_delay_ratio"], cfg["critical_delay_ratio"]))
        if delay >= cfg["warning_delay_ratio"]:
            issues.append(f"实际进度 {actual:.1f}% 低于计划 {planned:.1f}%")
    status = str(data.get("status", "unknown")).strip().lower()
    status_scores = {"normal": 0, "delayed": 50, "suspended": 85, "terminated": 100}
    if status in status_scores:
        components.append(status_scores[status])
    if status in {"suspended", "terminated"}:
        issues.append(f"项目状态为 {status}")
    # unknown不是“正常”：未知状态不贡献风险分，也不增加数据置信度。
    confidence = (int(planned is not None) + int(actual is not None) + int(status in status_scores)) / 3
    confidence *= evidence_factor(period, "project_progress")
    return {
        "score": round(max(components, default=0.0), 2),
        "confidence": round(confidence, 2),
        "metrics": metrics,
        "issues": issues,
        "evidence": evidence_ref(period, "project_progress")
    }


def kpi_deviation(actual: float, target: float, direction: str) -> float:
    scale = max(abs(target), 1e-9)
    if direction == "lower_better":
        return max(0.0, actual - target) / scale
    return max(0.0, target - actual) / scale


def period_target(kpi: dict, period: dict) -> tuple[float | None, str]:
    """取得本监测期应达值，避免拿半年/建设期实绩硬比全年最终承诺。"""
    kpi_id = kpi.get("kpi_id")
    explicit = (period.get("expected_environmental_kpis") or {}).get(kpi_id)
    if number(explicit) is not None:
        return number(explicit), "period_expected_value"

    schedule = kpi.get("target_schedule") or []
    dated = [row for row in schedule if isinstance(row, dict)
             and str(row.get("as_of_date", "")) <= str(period.get("as_of_date", ""))
             and number(row.get("target_value")) is not None]
    if dated:
        selected = sorted(dated, key=lambda row: str(row.get("as_of_date", "")))[-1]
        return number(selected.get("target_value")), "target_schedule"

    base = number(kpi.get("target_value"))
    target_type = str(kpi.get("target_type", "point_threshold"))
    factor = number(period.get("kpi_target_factor"))
    if target_type in {"annual_cumulative", "cumulative_flow"}:
        if factor is not None:
            return base * factor if base is not None else None, "annual_target_scaled"
        if not str(period.get("as_of_date", "")).endswith("12-31"):
            return None, "missing_period_factor"
    phase = str(period.get("project_phase", "operating")).lower()
    if phase in {"construction", "trial", "not_operational"} and target_type != "point_threshold":
        return None, "missing_phase_baseline"
    return base, "commitment_target"


def score_environment(period: dict, commitments: dict, cfg: dict) -> dict:
    values = period.get("environmental_kpis") or {}
    details, issues, scores = [], [], []
    promised_kpis = commitments.get("environmental_kpis") or []
    observed = 0
    for kpi in promised_kpis:
        kpi_id = kpi.get("kpi_id")
        actual = number(values.get(kpi_id))
        target, target_source = period_target(kpi, period)
        if actual is None or target is None:
            details.append({"kpi_id": kpi_id, "status": "missing", "target": target,
                            "actual": actual, "target_source": target_source})
            continue
        observed += 1
        deviation = kpi_deviation(actual, target, kpi.get("direction", "higher_better"))
        warning = number(kpi.get("warning_deviation_ratio")) or cfg["warning_deviation_ratio"]
        critical = number(kpi.get("critical_deviation_ratio")) or cfg["critical_deviation_ratio"]
        score = ratio_score(deviation, warning, critical)
        scores.append(score)
        status = "normal" if deviation < warning else ("warning" if deviation < critical else "critical")
        details.append({
            "kpi_id": kpi_id, "name": kpi.get("name"), "unit": kpi.get("unit"),
            "direction": kpi.get("direction", "higher_better"), "target": target,
            "actual": actual, "target_source": target_source,
            "deviation_ratio": round(deviation, 6), "score": round(score, 2), "status": status
        })
        if status != "normal":
            issues.append(f"环境指标“{kpi.get('name', kpi_id)}”相对贷中承诺偏离 {deviation:.2%}")
    confidence = observed / len(promised_kpis) if promised_kpis else 0.0
    confidence *= evidence_factor(period, "environmental_kpis")
    # 多指标同时偏离时兼顾最差项与整体，不让大量正常指标掩盖单一严重偏离。
    axis_score = 0.7 * max(scores, default=0.0) + 0.3 * (sum(scores) / len(scores) if scores else 0.0)
    return {
        "score": round(axis_score, 2), "confidence": round(confidence, 2),
        "metrics": {"kpi_observed": observed, "kpi_promised": len(promised_kpis), "details": details},
        "issues": issues, "evidence": evidence_ref(period, "environmental_kpis")
    }


def score_events(period: dict, cfg: dict) -> tuple[dict, list[str]]:
    cards, scores, hard_red = [], [], []
    for event in period.get("events", []):
        event_type = event.get("event_type", "other")
        severity = event.get("severity", "low")
        confirmed = event.get("verification_status") in {"confirmed", "verified"}
        lifecycle = str(event.get("lifecycle_status", event.get("status", "active"))).lower()
        active = lifecycle not in {"closed", "resolved", "rectified", "overturned", "expired"}
        base = cfg["event_scores"].get(event_type, cfg["event_scores"]["other"]).get(severity, 10)
        # 未核实舆情只作为线索，风险分折半且不会触发硬否决。
        score = float(base) if confirmed else float(base) * 0.5
        scores.append(score)
        code = event.get("event_code")
        if confirmed and active and code in cfg["hard_red_events"]:
            hard_red.append(code)
        cards.append({
            "event_id": event.get("event_id"), "event_type": event_type, "event_code": code,
            "severity": severity, "verification_status": event.get("verification_status", "unverified"),
            "lifecycle_status": lifecycle,
            "date": event.get("date"), "description": event.get("description"),
            "source": event.get("source"), "score": round(score, 2),
            "notice": "未核实事件仅作复核线索" if not confirmed else "已核实事件"
        })
    confidence = 1.0 if period.get("event_search_completed") is True else (0.6 if period.get("events") else 0.0)
    return ({
        "score": round(max(scores, default=0.0), 2), "confidence": round(confidence, 2),
        "metrics": {"event_count": len(cards)}, "issues": [c["description"] for c in cards if c.get("description")],
        "event_cards": cards, "evidence": evidence_ref(period, "compliance_events")
    }, hard_red)


def preloan_context(profile: dict) -> dict:
    if not profile:
        return {"score": 0.0, "availability": "not_available", "alerts": []}
    risk = number(profile.get("text_risk_signal_score"))
    penalty = number(profile.get("risk_penalty_rate"))
    percentile = number(profile.get("third_party_environment_percentile"))
    parts, alerts = [], []
    if risk is not None:
        parts.append(clamp(risk))
        if risk >= 60: alerts.append("贷前文本风险提示较高")
    if penalty is not None:
        parts.append(clamp(penalty * 300))
        if penalty >= 0.10: alerts.append("贷前环境处罚类信息占比较高")
    if percentile is not None:
        parts.append(clamp(100 - percentile))
        if percentile <= 30: alerts.append("第三方环境表现处于较低分位")
    return {
        "score": round(sum(parts) / len(parts), 2) if parts else 0.0,
        "availability": "available" if parts else "not_available",
        "alerts": alerts,
        "notice": "贷前企业画像只作风险背景，不覆盖贷后项目事实"
    }


def midloan_context(mid: dict) -> dict:
    if not mid:
        return {"availability": "not_available", "alerts": []}
    grade = mid.get("review_suggestion")
    alerts = []
    if grade in {"C", "D"}:
        alerts.append(f"贷中审查为{grade}类，不宜在关键缺口未关闭时视作正常绿色基线")
    retrieval = mid.get("catalog_retrieval") or {}
    approved_code = mid.get("approved_catalog_code") or retrieval.get("resolved_catalog_code")
    if not approved_code:
        alerts.append("贷中尚未形成经人工确认的最终目录代码，不能把Top-1候选直接冻结为贷后基线")
    return {
        "availability": "available", "review_suggestion": grade,
        "catalog_code": approved_code,
        "retrieval_state": retrieval.get("state"),
        "evidence_status": (mid.get("evidence_review") or {}).get("evidence_status"),
        "unclosed_missing_fields": mid.get("missing_basic_fields", []), "alerts": alerts,
        "notice": "贷中输出用于冻结承诺和证据基线，不在贷后重新做目录分类"
    }


def period_score(period: dict, commitments: dict, cfg: dict) -> tuple[dict, list[str]]:
    fund = score_fund(period, cfg["fund_use"])
    progress = score_progress(period, cfg["progress"])
    environment = score_environment(period, commitments, cfg["kpi_defaults"])
    events, hard_red = score_events(period, cfg)
    axes = {"fund_use": fund, "project_progress": progress,
            "environmental_performance": environment, "compliance_events": events}
    available_weight = sum(cfg["weights"][k] for k, v in axes.items() if v["confidence"] > 0)
    weighted = (sum(cfg["weights"][k] * v["score"] for k, v in axes.items() if v["confidence"] > 0)
                / available_weight if available_weight else 0.0)
    confidence = sum(cfg["weights"][k] * v["confidence"] for k, v in axes.items())
    return ({
        "as_of_date": period.get("as_of_date"), "axis_results": axes,
        "raw_weighted_score": round(weighted, 2), "data_confidence": round(confidence, 2)
    }, hard_red)


def add_persistence(period_results: list[dict], cfg: dict) -> None:
    n = int(cfg["thresholds"]["persistence_periods"])
    threshold = float(cfg["thresholds"]["persistence_axis_score"])
    axis_names = cfg["weights"].keys()
    for i, result in enumerate(period_results):
        persistent = []
        if i + 1 >= n:
            window = period_results[i + 1 - n:i + 1]
            for axis in axis_names:
                if all(x["axis_results"][axis]["score"] >= threshold for x in window):
                    persistent.append(axis)
        result["persistent_axes"] = persistent
        result["persistence_adjustment"] = min(15, 5 * len(persistent))
        result["adjusted_score"] = round(clamp(result["raw_weighted_score"] + result["persistence_adjustment"]), 2)


def grade(score: float, confidence: float, hard_red: list[str], cfg: dict) -> tuple[str, str]:
    t = cfg["thresholds"]
    if hard_red or score >= t["red"]:
        return "RED", "红色：立即复核并按制度升级处置"
    if score >= t["orange"]:
        return "ORANGE", "橙色：限期专项核查"
    if score >= t["yellow"]:
        return "YELLOW", "黄色：补充材料并加强跟踪"
    if confidence < t["low_confidence"]:
        return "GREY", "灰色：证据不足，无法判断正常或异常"
    return "GREEN", "绿色：当前未见显著偏离，继续例行监测"


def actions_for(level: str, latest: dict, hard_red: list[str]) -> list[dict]:
    actions = []
    for axis, result in latest["axis_results"].items():
        if result["confidence"] == 0:
            actions.append({"priority": "P2", "owner": "贷后管理", "action": f"补采 {axis} 的本期数据和可追溯证据"})
        elif result["score"] >= 55:
            actions.append({"priority": "P1", "owner": "贷后管理/专业复核", "action": f"对 {axis} 发起专项核查并记录结论"})
        elif result["score"] >= 30:
            actions.append({"priority": "P2", "owner": "客户经理/贷后管理", "action": f"核验 {axis} 的偏离原因、证据口径和整改计划"})
    if hard_red:
        actions.insert(0, {"priority": "P0", "owner": "风险/合规负责人", "action": "核验硬触发事件，按本行制度决定停拨、整改、重分类或其他措施；模型不自动执行"})
    if level == "GREY":
        actions.insert(0, {"priority": "P1", "owner": "客户经理", "action": "先补件，不得把信息缺失写成项目违规"})
    actions.append({"priority": "P3", "owner": "系统", "action": "保存本次输入、证据、模型版本、人工复核和最终处置，进入闭环台账"})
    return actions


def analyze_case(case: dict, config: dict) -> dict:
    periods = sorted(case.get("monitoring_periods", []), key=lambda x: x.get("as_of_date", ""))
    if not periods:
        raise ValueError("monitoring_periods 不能为空")
    results, hard_red_by_period = [], []
    for period in periods:
        result, hard_red = period_score(period, case.get("commitments", {}), config)
        results.append(result)
        hard_red_by_period.append(hard_red)
    add_persistence(results, config)
    latest = results[-1]
    # 只允许最新期间仍有效且已核实的重大事件硬触发。历史事件保留审计轨迹，
    # 但整改关闭后不能永久锁死为红色。
    current_hard_red = hard_red_by_period[-1]
    historical_hard_red = sorted(set(code for rows in hard_red_by_period[:-1] for code in rows))
    level, label = grade(latest["adjusted_score"], latest["data_confidence"], current_hard_red, config)
    pre = preloan_context(case.get("preloan_profile") or {})
    mid = midloan_context(case.get("midloan_review") or {})
    # 企业级贷前风险只允许在边界附近上调一个档位，不得覆盖项目实测证据。
    if pre["score"] >= 70 and level == "GREEN":
        level, label = "YELLOW", "黄色：项目当前偏离不高，但企业级环境风险背景要求加强跟踪"
    issues = []
    for axis, item in latest["axis_results"].items():
        issues.extend({"axis": axis, "message": msg} for msg in item["issues"])
    # “绿色”等级只表示综合风险尚未越过黄色阈值，并不表示所有分项均正常。
    # 只要已有明确问题或待办，仍需进入人工复核队列，避免绿灯掩盖局部异常。
    review_tasks = actions_for(level, latest, current_hard_red)
    return {
        "schema_version": "green-loan-post-monitor/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": case.get("project_id"), "project_name": case.get("project_name"),
        "company_name": case.get("company_name"), "as_of_date": latest["as_of_date"],
        "model_positioning": "贷后绿色承诺持续兑现、偏离识别与人工处置闭环",
        "input_sources": case.get("resolved_source_paths", {}),
        "contract_metadata": case.get("contract_metadata", {}),
        "risk_level": level, "risk_label": label, "risk_score": latest["adjusted_score"],
        "data_confidence": latest["data_confidence"],
        "hard_red_triggers": sorted(set(current_hard_red)),
        "historical_hard_red_events": historical_hard_red,
        "latest_axis_results": latest["axis_results"], "period_results": results,
        "preloan_context": pre, "midloan_baseline": mid, "current_issues": issues,
        "review_tasks": review_tasks,
        "manual_review_required": level != "GREEN" or bool(issues) or bool(review_tasks),
        "limitations": [
            "风险分是排序与触发工具，不是违约概率，也不是漂绿认定",
            "未核实舆情只作线索；硬触发必须是已核实事件",
            "数据缺失降低置信度并触发补件，不能据此认定正常或违规",
            "阈值须用本行历史案例和专家金标准校准后才能生产使用",
            "模型不自动停贷、抽贷、重分类或对外披露，最终处置由授权人员决定"
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="单案例JSON，或案例数组JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    cfg = deep_merge(DEFAULT_CONFIG, load_json(args.config)) if args.config else DEFAULT_CONFIG
    payload = load_json(args.input)
    if isinstance(payload, list):
        result = [analyze_case(hydrate_case(x, args.input), cfg) for x in payload]
    else:
        result = analyze_case(hydrate_case(payload, args.input), cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
