"""Read models for Phase 2 pages.

This module intentionally uses only ``SQLiteRepository``.  Legacy JSON is not
part of any formal dashboard or case-queue calculation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from green_model.agent.storage import SQLiteRepository


OPEN_TASK_STATUSES = {"pending", "in_progress", "pending_review", "returned"}
CLOSED_STATES = {"closed", "resolved", "dismissed"}
LEGACY_DEMO = "legacy_demo"

RISK_DIMENSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "claim_credibility",
        "绿色主张可信性",
        ("claim", "greenwashing", "主张", "披露", "漂绿"),
    ),
    (
        "project_boundary_and_use",
        "项目边界与融资用途",
        ("project_boundary", "green_substance", "fund", "use_of_proceeds", "项目边界", "资金用途"),
    ),
    (
        "technical_and_compliance",
        "行业技术与合规落实",
        ("industry_compliance", "industry_policy", "compliance", "permit", "技术", "合规", "许可"),
    ),
    (
        "implementation_and_funds",
        "项目实施与资金执行",
        ("execution_funds", "implementation", "construction", "payment", "实施", "建设", "支付"),
    ),
    (
        "performance_and_continuing_compliance",
        "绩效兑现与持续合规",
        ("performance_compliance", "postloan", "performance", "bta", "actual", "贷后", "实绩", "偏离"),
    ),
)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _risk_bucket(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    for code, _, aliases in RISK_DIMENSIONS:
        if text == code or any(alias.lower() in text for alias in aliases):
            return code
    return None


@dataclass(frozen=True)
class DashboardSnapshot:
    metrics: dict[str, int]
    recent_cases: list[dict[str, Any]]
    risk_distribution: list[dict[str, Any]]
    task_distribution: list[dict[str, Any]]
    legacy_demo_cases: list[dict[str, Any]]
    unmapped_risk_count: int


class Phase2Queries:
    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def case(self, case_id: str) -> dict[str, Any] | None:
        return self.repository.get("cases", case_id)

    def dashboard(self) -> DashboardSnapshot:
        cases = self.repository.find("cases", order_by="-updated_at")
        tasks = self.repository.find("tasks")
        conflicts = self.repository.find("conflict_logs")
        risks = self.repository.find("risk_findings")
        indicators = self.repository.find("bta_indicators")

        formal_cases = [case for case in cases if case.get("record_origin") != LEGACY_DEMO]
        formal_case_ids = {case["case_id"] for case in formal_cases}
        legacy_cases = [case for case in cases if case.get("record_origin") == LEGACY_DEMO]
        formal_tasks = [task for task in tasks if task.get("case_id") in formal_case_ids]
        formal_conflicts = [
            item
            for item in conflicts
            if item.get("case_id") in formal_case_ids
            and item.get("record_origin") != LEGACY_DEMO
        ]
        formal_risks = [
            item
            for item in risks
            if item.get("case_id") in formal_case_ids
            and item.get("record_origin") != LEGACY_DEMO
            and item.get("is_current", 1) == 1
        ]
        formal_indicators = [
            item
            for item in indicators
            if item.get("case_id") in formal_case_ids
            and item.get("record_origin") != LEGACY_DEMO
        ]

        open_tasks = [task for task in formal_tasks if task.get("status") in OPEN_TASK_STATUSES]
        open_conflicts = [
            item
            for item in formal_conflicts
            if str(item.get("status") or "").lower() not in CLOSED_STATES
        ]
        supplement_tasks = [
            task
            for task in open_tasks
            if str(task.get("task_type") or "").lower() in {
                "supplement", "supplement_request", "supplement_review", "补件"
            }
        ]
        now = datetime.now(timezone.utc)
        overdue_tasks = []
        for task in open_tasks:
            due = _parse_time(task.get("due_at"))
            if due is not None:
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if due < now:
                    overdue_tasks.append(task)

        risk_counter: Counter[str] = Counter()
        unmapped = 0
        for risk in formal_risks:
            bucket = _risk_bucket(risk.get("risk_dimension"))
            if bucket:
                risk_counter[bucket] += 1
            else:
                unmapped += 1

        postloan_risk_count = risk_counter["performance_and_continuing_compliance"]
        postloan_indicator_count = sum(
            1
            for item in formal_indicators
            if str(item.get("status") or "").lower()
            in {"warning", "alert", "manual_attention", "overdue"}
        )

        risk_distribution = [
            {"code": code, "label": label, "count": risk_counter[code]}
            for code, label, _ in RISK_DIMENSIONS
        ]
        task_counts = Counter(task.get("status") for task in formal_tasks)
        task_distribution = [
            {"code": code, "label": label, "count": task_counts[code]}
            for code, label in (
                ("pending", "待处理"),
                ("in_progress", "处理中"),
                ("pending_review", "待审核"),
                ("returned", "已退回"),
                ("closed", "已关闭"),
            )
        ]
        return DashboardSnapshot(
            metrics={
                "case_count": len(formal_cases),
                "open_task_count": len(open_tasks),
                "conflict_count": len(open_conflicts),
                "supplement_count": len(supplement_tasks),
                "postloan_warning_count": postloan_risk_count + postloan_indicator_count,
                "overdue_task_count": len(overdue_tasks),
            },
            recent_cases=formal_cases[:8],
            risk_distribution=risk_distribution,
            task_distribution=task_distribution,
            legacy_demo_cases=legacy_cases,
            unmapped_risk_count=unmapped,
        )

    def case_queue(
        self,
        *,
        status: str | None = None,
        industry: str | None = None,
        assignee: str | None = None,
        sort: str = "updated_desc",
    ) -> dict[str, Any]:
        stored_cases = self.repository.find("cases")
        all_cases = [
            case
            for case in stored_cases
            if case.get("record_origin") != LEGACY_DEMO
        ]
        showcase_cases = [
            case
            for case in stored_cases
            if case.get("record_origin") == LEGACY_DEMO
            and "fullchain_showcase" in str(case.get("legacy_note") or "")
        ]
        cases = list(all_cases)
        tasks = self.repository.find("tasks")
        formal_case_ids = {case["case_id"] for case in all_cases}
        open_counts = Counter(
            task.get("case_id")
            for task in tasks
            if task.get("case_id") in formal_case_ids
            and task.get("status") in OPEN_TASK_STATUSES
        )
        if status:
            cases = [case for case in cases if case.get("status") == status]
        if industry:
            cases = [case for case in cases if case.get("primary_industry") == industry]
        if assignee:
            cases = [case for case in cases if case.get("assignee") == assignee]
        reverse = sort != "updated_asc"
        cases.sort(key=lambda case: case.get("updated_at") or "", reverse=reverse)
        for case in cases:
            case["open_task_count"] = open_counts[case["case_id"]]
        showcase_case_ids = {case["case_id"] for case in showcase_cases}
        showcase_open_counts = Counter(
            task.get("case_id")
            for task in tasks
            if task.get("case_id") in showcase_case_ids
            and task.get("status") in OPEN_TASK_STATUSES
        )
        document_counts = Counter(
            row.get("case_id")
            for row in self.repository.find("documents")
            if row.get("case_id") in showcase_case_ids
        )
        verification_counts = Counter(
            row.get("case_id")
            for row in self.repository.find("verification_items")
            if row.get("case_id") in showcase_case_ids
            and row.get("is_current", 1) == 1
        )
        indicator_categories: dict[str, set[str]] = {}
        for row in self.repository.find("bta_indicators"):
            case_id = row.get("case_id")
            if case_id in showcase_case_ids:
                indicator_categories.setdefault(case_id, set()).add(
                    str(row.get("indicator_category") or row.get("indicator_id"))
                )
        for case in showcase_cases:
            case_id = case["case_id"]
            case["open_task_count"] = showcase_open_counts[case_id]
            case["document_count"] = document_counts[case_id]
            case["verification_count"] = verification_counts[case_id]
            case["indicator_count"] = len(indicator_categories.get(case_id, set()))
        showcase_cases.sort(key=lambda case: case.get("updated_at") or "", reverse=True)
        return {
            "cases": cases,
            "showcase_cases": showcase_cases,
            "filters": {
                "statuses": sorted({x["status"] for x in all_cases if x.get("status")}),
                "industries": sorted(
                    {x["primary_industry"] for x in all_cases if x.get("primary_industry")}
                ),
                "assignees": sorted({x["assignee"] for x in all_cases if x.get("assignee")}),
            },
            "selected": {
                "status": status or "",
                "industry": industry or "",
                "assignee": assignee or "",
                "sort": sort,
            },
        }
