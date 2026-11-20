"""Transactional SQLite repository for Phase 1 domain objects."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Iterator, Mapping

from ..domain.enums import CaseStatus, DocumentParseStatus, RoleType, TaskStatus
from ..domain.models import (
    AnalysisRun,
    AuditLog,
    BTAIndicator,
    Case,
    ClaimSignal,
    ConflictLog,
    Document,
    EvidenceSnippet,
    ExtractionRun,
    HumanDecision,
    ModelPredictionRecord,
    ModelRun,
    ProjectFact,
    ReportSnapshot,
    RiskFinding,
    RulePack,
    RuleVersion,
    SourceRecord,
    Task,
    VerificationItem,
    utc_now,
)
from ..domain.state_machines import (
    DOCUMENT_TRANSITIONS,
    TASK_TRANSITIONS,
    InvalidTransition,
    require_case_transition,
    require_transition,
)
from .database import Database


class NotFound(LookupError):
    pass


class ConcurrencyConflict(RuntimeError):
    pass


MODEL_TABLES: dict[type[Any], str] = {
    AnalysisRun: "analysis_runs",
    Case: "cases",
    ClaimSignal: "claim_signals",
    Document: "documents",
    SourceRecord: "source_records",
    ExtractionRun: "extraction_runs",
    ProjectFact: "project_facts",
    EvidenceSnippet: "evidence_snippets",
    RuleVersion: "rule_versions",
    RulePack: "rule_packs",
    VerificationItem: "verification_items",
    RiskFinding: "risk_findings",
    ConflictLog: "conflict_logs",
    Task: "tasks",
    BTAIndicator: "bta_indicators",
    ModelRun: "model_runs",
    ModelPredictionRecord: "model_prediction_records",
    HumanDecision: "human_decisions",
    AuditLog: "audit_logs",
    ReportSnapshot: "report_snapshots",
}

PRIMARY_KEYS: dict[str, str] = {
    "analysis_runs": "analysis_run_id",
    "cases": "case_id",
    "claim_signals": "claim_id",
    "documents": "doc_id",
    "source_records": "source_id",
    "extraction_runs": "extraction_run_id",
    "project_facts": "fact_id",
    "evidence_snippets": "evidence_id",
    "rule_versions": "rule_version_id",
    "rule_packs": "pack_id",
    "verification_items": "verification_id",
    "risk_findings": "finding_id",
    "conflict_logs": "conflict_id",
    "tasks": "task_id",
    "bta_indicators": "indicator_id",
    "bta_observations": "observation_id",
    "model_runs": "model_run_id",
    "model_prediction_records": "prediction_id",
    "human_decisions": "decision_id",
    "audit_logs": "audit_id",
    "report_snapshots": "report_id",
    "migration_batches": "batch_id",
    "migration_records": "migration_id",
    "source_manifest": "source_id",
    "industry_taxonomy": "node_id",
    "industry_rule_profiles": "profile_id",
    "standard_catalog": "standard_id",
    "industry_standard_links": "link_id",
    "indicator_definitions": "indicator_definition_id",
    "threshold_definitions": "threshold_id",
    "unit_conversion_rules": "conversion_id",
    "permit_requirements": "permit_requirement_id",
    "document_requirements": "document_requirement_id",
    "evidence_requirements": "evidence_requirement_id",
    "industry_risk_points": "risk_point_id",
    "postloan_indicator_definitions": "postloan_indicator_id",
    "term_cards": "term_id",
    "green_catalog_activities": "green_activity_id",
    "transition_catalog_activities": "transition_activity_id",
    "industry_activity_mappings": "mapping_id",
    "regional_rule_overlays": "overlay_id",
    "rule_version_relations": "relation_id",
    "industry_build_logs": "build_log_id",
    "industry_knowledge_items": "knowledge_id",
    "phase36_rule_items": "phase36_item_id",
    "rule_application_mappings": "application_mapping_id",
    "industry_density_assessments": "density_assessment_id",
    "simulation_rule_items": "simulation_item_id",
    "mock_rule_batches": "mock_batch_id",
    "postloan_evaluations": "evaluation_id",
}

ALLOWED_TABLES = frozenset(
    {
        *PRIMARY_KEYS,
        "fact_evidence_links",
        "verification_fact_links",
        "verification_evidence_links",
        "risk_evidence_links",
        "risk_rule_links",
        "risk_fact_links",
        "task_evidence_links",
        "task_risk_links",
        "task_conflict_links",
        "task_verification_links",
        "rule_pack_entries",
        "analysis_run_documents",
        "rule_application_evidence_links",
        "verification_requirement_links",
        "mock_rule_batch_items",
    }
)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return int(value)
    return value


class UnitOfWork:
    """CRUD operations scoped to one caller-controlled transaction."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._columns_cache: dict[str, set[str]] = {}

    def _validate_table(self, table: str) -> None:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"不允许访问的数据表：{table}")

    def _columns(self, table: str) -> set[str]:
        self._validate_table(table)
        if table not in self._columns_cache:
            rows = self.connection.execute(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                raise ValueError(f"数据表不存在：{table}")
            self._columns_cache[table] = {row["name"] for row in rows}
        return self._columns_cache[table]

    def add(self, entity: Any) -> dict[str, Any]:
        table = MODEL_TABLES.get(type(entity))
        if table is None:
            raise TypeError(f"未注册的领域对象：{type(entity).__name__}")
        if not hasattr(entity, "to_record"):
            raise TypeError("领域对象必须实现to_record")
        return self.insert(table, entity.to_record())

    def insert(
        self,
        table: str,
        record: Mapping[str, Any],
        *,
        on_conflict: str = "error",
    ) -> dict[str, Any]:
        columns = self._columns(table)
        data = {key: _plain(value) for key, value in record.items() if key in columns}
        now = utc_now()
        if "created_at" in columns:
            data.setdefault("created_at", now)
        if "updated_at" in columns:
            data.setdefault("updated_at", now)
        if "row_version" in columns:
            data.setdefault("row_version", 1)
        if not data:
            raise ValueError("没有可写入字段")
        names = list(data)
        placeholders = ", ".join("?" for _ in names)
        conflict_clause = ""
        if on_conflict == "ignore":
            conflict_clause = " ON CONFLICT DO NOTHING"
        elif on_conflict != "error":
            raise ValueError("on_conflict仅支持error或ignore")
        sql = (
            f"INSERT INTO {table} ({', '.join(names)}) "
            f"VALUES ({placeholders}){conflict_clause}"
        )
        self.connection.execute(sql, tuple(data[name] for name in names))
        return data

    def get(self, table: str, object_id: str) -> dict[str, Any] | None:
        self._validate_table(table)
        key = PRIMARY_KEYS.get(table)
        if key is None:
            raise ValueError(f"{table}没有单一主键")
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE {key} = ?", (object_id,)
        ).fetchone()
        return dict(row) if row else None

    def require(self, table: str, object_id: str) -> dict[str, Any]:
        row = self.get(table, object_id)
        if row is None:
            raise NotFound(f"{table}中不存在对象：{object_id}")
        return row

    def find(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        columns = self._columns(table)
        filters = filters or {}
        unknown = set(filters) - columns
        if unknown:
            raise ValueError(f"未知筛选字段：{sorted(unknown)}")
        where = ""
        values: list[Any] = []
        if filters:
            where = " WHERE " + " AND ".join(f"{key} = ?" for key in filters)
            values.extend(_plain(value) for value in filters.values())
        order = ""
        if order_by:
            direction = "ASC"
            field = order_by
            if order_by.startswith("-"):
                direction = "DESC"
                field = order_by[1:]
            if field not in columns:
                raise ValueError(f"未知排序字段：{field}")
            order = f" ORDER BY {field} {direction}"
        suffix = ""
        if limit is not None:
            if limit < 0:
                raise ValueError("limit不能为负数")
            suffix = " LIMIT ?"
            values.append(limit)
        rows = self.connection.execute(
            f"SELECT * FROM {table}{where}{order}{suffix}", values
        ).fetchall()
        return [dict(row) for row in rows]

    def update(
        self,
        table: str,
        object_id: str,
        changes: Mapping[str, Any],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        columns = self._columns(table)
        key = PRIMARY_KEYS.get(table)
        if key is None:
            raise ValueError(f"{table}没有单一主键")
        forbidden = {key, "created_at", "row_version"}
        data = {
            name: _plain(value)
            for name, value in changes.items()
            if name in columns and name not in forbidden
        }
        if "updated_at" in columns:
            data["updated_at"] = utc_now()
        if not data:
            raise ValueError("没有可更新字段")
        assignments = [f"{name} = ?" for name in data]
        if "row_version" in columns:
            assignments.append("row_version = row_version + 1")
        values = list(data.values()) + [object_id]
        where = f"{key} = ?"
        if expected_version is not None:
            if "row_version" not in columns:
                raise ValueError(f"{table}不支持乐观锁")
            where += " AND row_version = ?"
            values.append(expected_version)
        cursor = self.connection.execute(
            f"UPDATE {table} SET {', '.join(assignments)} WHERE {where}", values
        )
        if cursor.rowcount != 1:
            if self.get(table, object_id) is None:
                raise NotFound(f"{table}中不存在对象：{object_id}")
            raise ConcurrencyConflict(f"{table}/{object_id}已被其他事务更新")
        return self.require(table, object_id)

    def delete(self, table: str, object_id: str) -> None:
        self._validate_table(table)
        key = PRIMARY_KEYS.get(table)
        if key is None:
            raise ValueError(f"{table}没有单一主键")
        cursor = self.connection.execute(
            f"DELETE FROM {table} WHERE {key} = ?", (object_id,)
        )
        if cursor.rowcount != 1:
            raise NotFound(f"{table}中不存在对象：{object_id}")


class SQLiteRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[UnitOfWork]:
        with self.database.transaction() as connection:
            yield UnitOfWork(connection)

    def add(self, entity: Any) -> dict[str, Any]:
        if not is_dataclass(entity):
            raise TypeError("add仅接受领域dataclass对象")
        with self.transaction() as uow:
            return uow.add(entity)

    def get(self, table: str, object_id: str) -> dict[str, Any] | None:
        with self.database.transaction(immediate=False) as connection:
            return UnitOfWork(connection).get(table, object_id)

    def find(
        self,
        table: str,
        *,
        filters: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self.database.transaction(immediate=False) as connection:
            return UnitOfWork(connection).find(
                table, filters=filters, order_by=order_by, limit=limit
            )

    def update(
        self,
        table: str,
        object_id: str,
        changes: Mapping[str, Any],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as uow:
            return uow.update(
                table, object_id, changes, expected_version=expected_version
            )

    def delete(self, table: str, object_id: str) -> None:
        with self.transaction() as uow:
            uow.delete(table, object_id)

    @staticmethod
    def _append_audit(
        uow: UnitOfWork,
        *,
        case_id: str | None,
        action: str,
        actor: str,
        before_state: str | None = None,
        after_state: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        uow.add(
            AuditLog(
                case_id=case_id,
                action=action,
                actor=actor,
                actor_role=RoleType.SYSTEM if actor == "system" else None,
                before_state=before_state,
                after_state=after_state,
                details_json=dict(details) if details else None,
            )
        )

    def append_audit(
        self,
        *,
        case_id: str | None,
        action: str,
        actor: str,
        before_state: str | None = None,
        after_state: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        with self.transaction() as uow:
            self._append_audit(
                uow,
                case_id=case_id,
                action=action,
                actor=actor,
                before_state=before_state,
                after_state=after_state,
                details=details,
            )

    def _record_rejected_transition(
        self,
        *,
        case_id: str | None,
        machine: str,
        object_id: str,
        current: str | None,
        target: str,
        actor: str,
        reason: str,
    ) -> None:
        self.append_audit(
            case_id=case_id,
            action=f"{machine}_transition_rejected",
            actor=actor,
            before_state=current,
            after_state=target,
            details={"object_id": object_id, "reason": reason},
        )

    def transition_case(
        self, case_id: str, target: CaseStatus | str, *, actor: str
    ) -> dict[str, Any]:
        try:
            target_status = CaseStatus(target)
        except ValueError as exc:
            row = self.get("cases", case_id)
            current = row.get("status") if row else None
            self._record_rejected_transition(
                case_id=case_id if row else None,
                machine="case",
                object_id=case_id,
                current=current,
                target=str(target),
                actor=actor,
                reason=f"未知案件状态：{target}",
            )
            raise InvalidTransition("案件", current or "null", str(target)) from exc
        try:
            with self.transaction() as uow:
                row = uow.require("cases", case_id)
                if row["status"] is None:
                    raise InvalidTransition("案件", "null", target_status.value)
                current = CaseStatus(row["status"])
                failed_from = (
                    CaseStatus(row["failed_from_status"])
                    if row.get("failed_from_status")
                    else None
                )
                require_case_transition(
                    current, target_status, failed_from_status=failed_from
                )
                changes: dict[str, Any] = {
                    "status": target_status.value,
                    "current_revision": row["current_revision"] + 1,
                }
                if target_status is CaseStatus.FAILED:
                    changes["failed_from_status"] = current.value
                elif current is CaseStatus.FAILED:
                    changes["failed_from_status"] = None
                updated = uow.update(
                    "cases",
                    case_id,
                    changes,
                    expected_version=row["row_version"],
                )
                self._append_audit(
                    uow,
                    case_id=case_id,
                    action="case_transition",
                    actor=actor,
                    before_state=current.value,
                    after_state=target_status.value,
                )
                return updated
        except InvalidTransition as exc:
            current_value = locals().get("current")
            self._record_rejected_transition(
                case_id=case_id,
                machine="case",
                object_id=case_id,
                current=current_value.value if current_value else None,
                target=target_status.value,
                actor=actor,
                reason=str(exc),
            )
            raise

    def transition_document(
        self,
        doc_id: str,
        target: DocumentParseStatus | str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        try:
            target_status = DocumentParseStatus(target)
        except ValueError as exc:
            row = self.get("documents", doc_id)
            current = row.get("parse_status") if row else None
            self._record_rejected_transition(
                case_id=row.get("case_id") if row else None,
                machine="document",
                object_id=doc_id,
                current=current,
                target=str(target),
                actor=actor,
                reason=f"未知文档状态：{target}",
            )
            raise InvalidTransition("文档", current or "null", str(target)) from exc
        try:
            with self.transaction() as uow:
                row = uow.require("documents", doc_id)
                if row["parse_status"] is None:
                    raise InvalidTransition("文档", "null", target_status.value)
                current = DocumentParseStatus(row["parse_status"])
                require_transition("文档", current, target_status, DOCUMENT_TRANSITIONS)
                updated = uow.update(
                    "documents",
                    doc_id,
                    {"parse_status": target_status.value},
                    expected_version=row["row_version"],
                )
                self._append_audit(
                    uow,
                    case_id=row["case_id"],
                    action="document_transition",
                    actor=actor,
                    before_state=current.value,
                    after_state=target_status.value,
                    details={"doc_id": doc_id},
                )
                return updated
        except InvalidTransition as exc:
            current_value = locals().get("current")
            case_value = locals().get("row", {}).get("case_id")
            self._record_rejected_transition(
                case_id=case_value,
                machine="document",
                object_id=doc_id,
                current=current_value.value if current_value else None,
                target=target_status.value,
                actor=actor,
                reason=str(exc),
            )
            raise

    def transition_task(
        self,
        task_id: str,
        target: TaskStatus | str,
        *,
        actor: str,
        closing_decision_id: str | None = None,
        closing_evidence_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            target_status = TaskStatus(target)
        except ValueError as exc:
            row = self.get("tasks", task_id)
            current = row.get("status") if row else None
            self._record_rejected_transition(
                case_id=row.get("case_id") if row else None,
                machine="task",
                object_id=task_id,
                current=current,
                target=str(target),
                actor=actor,
                reason=f"未知任务状态：{target}",
            )
            raise InvalidTransition("任务", current or "null", str(target)) from exc
        try:
            with self.transaction() as uow:
                row = uow.require("tasks", task_id)
                current = TaskStatus(row["status"])
                require_transition("任务", current, target_status, TASK_TRANSITIONS)
                if target_status is TaskStatus.CLOSED:
                    decision_id = closing_decision_id or row.get("closing_decision_id")
                    if not decision_id:
                        raise InvalidTransition(
                            "任务（关闭需人工决定）", current.value, target_status.value
                        )
                    decision = uow.require("human_decisions", decision_id)
                    allowed_roles = {
                        RoleType.REVIEWER.value,
                        RoleType.APPROVER.value,
                        RoleType.TEAM_LEAD.value,
                        RoleType.ADMINISTRATOR.value,
                    }
                    decision_is_valid = (
                        decision["case_id"] == row["case_id"]
                        and decision.get("target_type") == "task"
                        and decision.get("target_id") == task_id
                        and decision.get("decision") == "approve_close"
                        and decision.get("actor_role") in allowed_roles
                        and decision.get("based_on_revision") == row["row_version"]
                    )
                    if not decision_is_valid:
                        raise InvalidTransition(
                            "任务（关闭决定无效或已过期）",
                            current.value,
                            target_status.value,
                        )
                changes: dict[str, Any] = {"status": target_status.value}
                if closing_decision_id:
                    changes["closing_decision_id"] = closing_decision_id
                if closing_evidence_id:
                    changes["closing_evidence_id"] = closing_evidence_id
                updated = uow.update(
                    "tasks",
                    task_id,
                    changes,
                    expected_version=row["row_version"],
                )
                self._append_audit(
                    uow,
                    case_id=row["case_id"],
                    action="task_transition",
                    actor=actor,
                    before_state=current.value,
                    after_state=target_status.value,
                    details={"task_id": task_id},
                )
                return updated
        except InvalidTransition as exc:
            current_value = locals().get("current")
            case_value = locals().get("row", {}).get("case_id")
            self._record_rejected_transition(
                case_id=case_value,
                machine="task",
                object_id=task_id,
                current=current_value.value if current_value else None,
                target=target_status.value,
                actor=actor,
                reason=str(exc),
            )
            raise

    def submit_supplement_for_review(
        self,
        task_id: str,
        *,
        recompute_run_id: str,
        evidence_ids: list[str],
        actor: str,
    ) -> dict[str, Any]:
        """A supplement can only advance a working task to pending review."""
        try:
            with self.transaction() as uow:
                row = uow.require("tasks", task_id)
                current = TaskStatus(row["status"])
                require_transition(
                    "任务（补件重算）",
                    current,
                    TaskStatus.PENDING_REVIEW,
                    TASK_TRANSITIONS,
                )
                run = uow.require("model_runs", recompute_run_id)
                run_is_usable = (
                    run["case_id"] == row["case_id"]
                    and run.get("status") == "completed"
                    and run.get("is_real_model_result") == 1
                    and run.get("eligible_for_decision") == 1
                    and run.get("record_origin") != "legacy_demo"
                )
                if not run_is_usable:
                    raise InvalidTransition(
                        "任务（重算未完成或不可用于判断）",
                        current.value,
                        TaskStatus.PENDING_REVIEW.value,
                    )
                if not evidence_ids:
                    raise InvalidTransition(
                        "任务（补件证据为空）",
                        current.value,
                        TaskStatus.PENDING_REVIEW.value,
                    )
                now = utc_now()
                for evidence_id in evidence_ids:
                    evidence = uow.require("evidence_snippets", evidence_id)
                    if evidence["case_id"] != row["case_id"]:
                        raise InvalidTransition(
                            "任务（补件证据不属于本案件）",
                            current.value,
                            TaskStatus.PENDING_REVIEW.value,
                        )
                    uow.insert(
                        "task_evidence_links",
                        {
                            "task_id": task_id,
                            "evidence_id": evidence_id,
                            "link_role": "supplement",
                            "created_at": now,
                            "updated_at": now,
                            "row_version": 1,
                        },
                        on_conflict="ignore",
                    )
                updated = uow.update(
                    "tasks",
                    task_id,
                    {
                        "status": TaskStatus.PENDING_REVIEW.value,
                        "recompute_run_id": recompute_run_id,
                    },
                    expected_version=row["row_version"],
                )
                self._append_audit(
                    uow,
                    case_id=row["case_id"],
                    action="supplement_submitted_for_review",
                    actor=actor,
                    before_state=current.value,
                    after_state=TaskStatus.PENDING_REVIEW.value,
                    details={
                        "task_id": task_id,
                        "recompute_run_id": recompute_run_id,
                        "evidence_ids": evidence_ids,
                    },
                )
                return updated
        except InvalidTransition as exc:
            current_value = locals().get("current")
            case_value = locals().get("row", {}).get("case_id")
            self._record_rejected_transition(
                case_id=case_value,
                machine="task_supplement",
                object_id=task_id,
                current=current_value.value if current_value else None,
                target=TaskStatus.PENDING_REVIEW.value,
                actor=actor,
                reason=str(exc),
            )
            raise

    def query_case_bundle(self, case_id: str) -> dict[str, Any]:
        with self.database.transaction(immediate=False) as connection:
            uow = UnitOfWork(connection)
            case = uow.require("cases", case_id)
            return {
                "case": case,
                "documents": uow.find(
                    "documents", filters={"case_id": case_id}, order_by="created_at"
                ),
                "facts": uow.find(
                    "project_facts", filters={"case_id": case_id}, order_by="created_at"
                ),
                "evidence": uow.find(
                    "evidence_snippets",
                    filters={"case_id": case_id},
                    order_by="created_at",
                ),
                "tasks": uow.find(
                    "tasks", filters={"case_id": case_id}, order_by="created_at"
                ),
                "audit_logs": uow.find(
                    "audit_logs", filters={"case_id": case_id}, order_by="occurred_at"
                ),
            }
