from __future__ import annotations

from typing import Any


def normalize_evidence(items: list[dict[str, Any]] | None, case_id: str | None = None) -> list[dict[str, Any]]:
    result = []
    for i, item in enumerate(items or [], 1):
        result.append({
            "evidence_id": item.get("evidence_id") or item.get("id") or f"E{i:03d}", "case_id": item.get("case_id") or case_id,
            "claim_id": item.get("claim_id"), "source_document": item.get("source_document") or item.get("file_name"),
            "source_type": item.get("source_type", "E1"), "issuer": item.get("issuer") or item.get("source"),
            "timestamp": item.get("timestamp") or item.get("date"),
            "name": item.get("name") or item.get("type") or "未命名材料",
            "source": item.get("source"), "page": item.get("page"),
            "location": item.get("location") or item.get("paragraph") or item.get("sentence_id"),
            "raw_excerpt": item.get("raw_excerpt") or item.get("sentence") or item.get("value"),
            "file_hash": item.get("file_hash"),
            "verification_status": item.get("verification_status", "unverified"),
            "conflict_status": item.get("conflict_status", "none"), "confidence": item.get("confidence"),
            "reviewer_status": item.get("reviewer_status", "pending"),
            "supports": item.get("supports", []),
        })
    return result


def build_worklist(midloan: dict[str, Any]) -> dict[str, Any]:
    gaps = midloan.get("evidence_review", {}).get("missing_evidence", [])
    if not gaps:
        gaps = midloan.get("evidence_review", {}).get("missing_or_unverified", [])
    conditions = midloan.get("condition_review", {}).get("condition_results", [])
    site_checks = []
    for condition in conditions:
        if condition.get("status") in {"unknown", "conflict", "not_met"}:
            site_checks.append({
                "priority": "P1" if condition.get("status") in {"conflict", "not_met"} else "P2",
                "check": condition.get("condition_text") or "核验目录技术条件",
                "reason": f"当前状态：{condition.get('status', 'unknown')}",
                "evidence_refs": condition.get("evidence_refs", []),
            })
    return {
        "supplementation_list": [{
            "missing": x.get("required_type") if isinstance(x, dict) else str(x),
            "why_missing": x.get("description", "当前证据未提供或未核验") if isinstance(x, dict) else "当前证据未提供或未核验",
            "condition": x.get("condition_id") if isinstance(x, dict) else None,
            "basis_source": x.get("basis_source") if isinstance(x, dict) else None,
            "basis_type": x.get("basis_type", "R2 standard_derived") if isinstance(x, dict) else "R2 standard_derived",
            "critical_blocker": True,
        } for x in gaps],
        "site_inspection_priorities": site_checks,
        "postloan_tracking_list": [],
        "notice": "清单用于辅助补件与尽调准备，具体材料以适用政策、本行制度和人工判断为准。",
    }


def detect_conflicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_claim: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if item.get("claim_id"):
            by_claim.setdefault(str(item["claim_id"]), []).append(item)
    conflicts = []
    for claim_id, rows in by_claim.items():
        values = {str(x.get("raw_excerpt")) for x in rows if x.get("raw_excerpt") not in (None, "")}
        sources = {x.get("source_type") for x in rows}
        if len(values) > 1 and len(sources) > 1:
            conflicts.append({"claim_id": claim_id, "status": "CONFLICT", "evidence_ids": [x.get("evidence_id") for x in rows], "requires_human_review": True})
    return conflicts
