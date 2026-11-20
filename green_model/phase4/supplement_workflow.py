"""End-to-end supplement workflow orchestration.

This module deliberately coordinates existing Phase 1/3/4 services instead of
duplicating parsers or risk rules.  Uploading a supplement never closes a task:
the document is hashed and parsed, the case is reassessed, and the task advances
to ``pending_review``.  Only an authorised human decision can close it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from green_model.agent.domain.enums import (
    DataOrigin,
    DocumentParseStatus,
    RoleType,
    SourceStatus,
    TaskStatus,
)
from green_model.agent.domain.models import (
    AuditLog,
    Document,
    ReportSnapshot,
    SourceRecord,
    Task,
    new_id,
    utc_now,
)
from green_model.agent.storage import SQLiteRepository
from green_model.phase2_ui.intelligence import CaseIntelligence
from green_model.phase2_ui.reporting import json_bytes, pdf_bytes, report_payload
from green_model.phase3 import DocumentProcessingService

from .case_intelligence import AssessmentResult, CaseIntelligenceService


_SAFE_FILENAME = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


@dataclass(frozen=True)
class SupplementUpload:
    file_name: str
    content: bytes
    mime_type: str = "application/octet-stream"
    file_type: str = "补充材料"
    related_item: str | None = None


@dataclass(frozen=True)
class SupplementWorkflowResult:
    case_id: str
    task_id: str
    document_id: str
    file_sha256: str
    extraction_run_id: str
    analysis_run_id: str
    evidence_ids: tuple[str, ...]
    fact_count: int
    task_status: str
    reused_document: bool


@dataclass(frozen=True)
class HumanReviewResult:
    case_id: str
    task_id: str
    decision_id: str
    task_status: str
    report_id: str
    snapshot_revision: int
    pdf_path: str
    pdf_sha256: str


class SupplementWorkflowError(RuntimeError):
    """A user-actionable workflow failure with persisted audit context."""


class SupplementWorkflowService:
    """Coordinate upload, parsing, reassessment, review and report versioning."""

    def __init__(
        self,
        repository: SQLiteRepository,
        *,
        upload_root: str | Path,
        report_root: str | Path,
        document_service: DocumentProcessingService | None = None,
        intelligence_service: CaseIntelligenceService | None = None,
        read_model: CaseIntelligence | None = None,
        json_renderer: Callable[[dict[str, Any]], bytes] = json_bytes,
        pdf_renderer: Callable[[dict[str, Any]], bytes] = pdf_bytes,
    ) -> None:
        self.repository = repository
        self.upload_root = Path(upload_root)
        self.report_root = Path(report_root)
        self.document_service = document_service or DocumentProcessingService(repository)
        self.intelligence_service = intelligence_service or CaseIntelligenceService(repository)
        self.read_model = read_model or CaseIntelligence(repository)
        self.json_renderer = json_renderer
        self.pdf_renderer = pdf_renderer

    def upload_parse_and_reassess(
        self,
        case_id: str,
        upload: SupplementUpload,
        *,
        task_id: str | None = None,
        actor: str,
    ) -> SupplementWorkflowResult:
        """Run the supplement flow through ``pending_review``, never ``closed``."""

        case = self.repository.get("cases", case_id)
        if case is None:
            raise LookupError(f"案件不存在：{case_id}")
        if not upload.content:
            raise ValueError("补件内容不能为空")
        if len(upload.content) > 25 * 1024 * 1024:
            raise ValueError("单个补件不得超过25MB")

        digest = hashlib.sha256(upload.content).hexdigest()
        document, reused = self._register_document(
            case_id, upload, digest=digest, actor=actor
        )
        task = self._prepare_task(
            case_id,
            task_id=task_id,
            document_id=str(document["doc_id"]),
            upload=upload,
            actor=actor,
        )

        outcome = self.document_service.process(case_id, str(document["doc_id"]), actor=actor)
        if outcome.status != "completed":
            self._audit_failure(
                case_id,
                actor=actor,
                action="supplement_workflow_parse_incomplete",
                details={
                    "task_id": task["task_id"],
                    "document_id": document["doc_id"],
                    "extraction_run_id": outcome.run_id,
                    "parse_status": outcome.status,
                    "reason": outcome.message,
                },
            )
            raise SupplementWorkflowError(
                f"补件解析未完成（{outcome.status}）：{outcome.message}"
            )

        evidence_rows = self.repository.find(
            "evidence_snippets",
            filters={"case_id": case_id, "extraction_run_id": outcome.run_id},
            order_by="created_at",
        )
        evidence_ids = [str(row["evidence_id"]) for row in evidence_rows]
        if not evidence_ids:
            self._audit_failure(
                case_id,
                actor=actor,
                action="supplement_workflow_no_evidence",
                details={
                    "task_id": task["task_id"],
                    "document_id": document["doc_id"],
                    "extraction_run_id": outcome.run_id,
                },
            )
            raise SupplementWorkflowError("补件已解析但未提取到可定位证据，任务保持处理中。")

        assessment = self.intelligence_service.submit_supplement_for_reassessment(
            str(task["task_id"]),
            evidence_ids=evidence_ids,
            actor=actor,
        )
        updated_task = self.repository.get("tasks", str(task["task_id"]))
        if updated_task is None or updated_task.get("status") != TaskStatus.PENDING_REVIEW.value:
            raise SupplementWorkflowError("补件重算完成，但任务未进入待审核状态。")

        with self.repository.transaction() as uow:
            uow.add(AuditLog(
                case_id=case_id,
                action="supplement_closed_loop_pending_review",
                actor=actor,
                actor_role=RoleType.RELATIONSHIP_MANAGER,
                model_run_id=assessment.model_run_id,
                file_hash=digest,
                correlation_id=str(task["task_id"]),
                details_json={
                    "task_id": task["task_id"],
                    "document_id": document["doc_id"],
                    "extraction_run_id": outcome.run_id,
                    "analysis_run_id": assessment.analysis_run_id,
                    "evidence_ids": evidence_ids,
                    "fact_count": outcome.fact_count,
                    "old_results_retained": True,
                    "automatic_close": False,
                    "conclusion_changed": False,
                },
            ))

        return SupplementWorkflowResult(
            case_id=case_id,
            task_id=str(task["task_id"]),
            document_id=str(document["doc_id"]),
            file_sha256=digest,
            extraction_run_id=outcome.run_id,
            analysis_run_id=assessment.analysis_run_id,
            evidence_ids=tuple(evidence_ids),
            fact_count=outcome.fact_count,
            task_status=str(updated_task["status"]),
            reused_document=reused,
        )

    def review_task(
        self,
        case_id: str,
        task_id: str,
        *,
        approve: bool,
        reason: str,
        actor: str,
        actor_role: RoleType,
    ) -> HumanReviewResult:
        """Approve-close or reject-return a pending-review task, then freeze a report."""

        task = self.repository.get("tasks", task_id)
        if task is None or task.get("case_id") != case_id:
            raise LookupError("审核任务不存在或不属于当前案件。")
        if task.get("status") != TaskStatus.PENDING_REVIEW.value:
            raise ValueError("只有“待审核”任务可以进行人工确认。")
        if not reason.strip():
            raise ValueError("人工确认必须记录理由。")

        decision_code = "approve_close" if approve else "reject_return"
        decision = self.intelligence_service.record_human_confirmation(
            case_id=case_id,
            target_type="task",
            target_id=task_id,
            decision=decision_code,
            reason=reason.strip(),
            actor=actor,
            actor_role=actor_role,
        )
        evidence_links = self.repository.find(
            "task_evidence_links", filters={"task_id": task_id}, order_by="created_at"
        )
        closing_evidence_id = (
            str(evidence_links[-1]["evidence_id"]) if evidence_links else None
        )
        if approve:
            updated = self.repository.transition_task(
                task_id,
                TaskStatus.CLOSED,
                actor=actor,
                closing_decision_id=str(decision["decision_id"]),
                closing_evidence_id=closing_evidence_id,
            )
            report_status = "final_approved"
        else:
            updated = self.repository.transition_task(
                task_id, TaskStatus.RETURNED, actor=actor
            )
            report_status = "returned_for_supplement"

        report = self._freeze_report(
            case_id,
            task_id=task_id,
            decision_id=str(decision["decision_id"]),
            status=report_status,
            actor=actor,
        )
        return HumanReviewResult(
            case_id=case_id,
            task_id=task_id,
            decision_id=str(decision["decision_id"]),
            task_status=str(updated["status"]),
            report_id=str(report["report_id"]),
            snapshot_revision=int(report["snapshot_revision"]),
            pdf_path=str(report["pdf_path"]),
            pdf_sha256=str(report["pdf_hash"]),
        )

    def _register_document(
        self,
        case_id: str,
        upload: SupplementUpload,
        *,
        digest: str,
        actor: str,
    ) -> tuple[dict[str, Any], bool]:
        existing = next((
            row for row in self.repository.find(
                "documents", filters={"case_id": case_id}, order_by="-created_at"
            )
            if row.get("source_kind") == "supplement" and row.get("sha256") == digest
        ), None)
        if existing is not None:
            return existing, True

        safe_name = _SAFE_FILENAME.sub("_", Path(upload.file_name).name).strip("._")[:180]
        safe_name = safe_name or "supplement.bin"
        case_dir = self.upload_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        target = case_dir / f"{digest[:16]}_{safe_name}"
        temporary = case_dir / f".{digest[:16]}_{new_id('upload')}.partial"
        temporary.write_bytes(upload.content)
        os.replace(temporary, target)

        source = SourceRecord(
            source_type="user_supplement",
            title=upload.file_name,
            local_path=str(target),
            sha256=digest,
            status=SourceStatus.CANDIDATE,
            authority_level="user_provided_unverified",
        )
        document = Document(
            case_id=case_id,
            file_name=upload.file_name,
            file_type=upload.file_type,
            mime_type=upload.mime_type,
            source_kind="supplement",
            source_id=source.source_id,
            original_path=str(target),
            sha256=digest,
            parse_status=DocumentParseStatus.UPLOADED,
            record_origin=DataOrigin.USER_UPLOAD,
        )
        try:
            with self.repository.transaction() as uow:
                uow.add(source)
                uow.add(document)
                uow.add(AuditLog(
                    case_id=case_id,
                    action="supplement_registered",
                    actor=actor,
                    actor_role=RoleType.RELATIONSHIP_MANAGER,
                    file_hash=digest,
                    details_json={
                        "document_id": document.doc_id,
                        "source_id": source.source_id,
                        "related_item": upload.related_item,
                        "conclusion_changed": False,
                    },
                ))
        except Exception:
            if target.exists():
                target.unlink()
            raise
        return self.repository.get("documents", document.doc_id) or document.to_record(), False

    def _prepare_task(
        self,
        case_id: str,
        *,
        task_id: str | None,
        document_id: str,
        upload: SupplementUpload,
        actor: str,
    ) -> dict[str, Any]:
        if task_id:
            task = self.repository.get("tasks", task_id)
            if task is None or task.get("case_id") != case_id:
                raise LookupError("补件关联任务不存在或不属于当前案件。")
        else:
            created = Task(
                case_id=case_id,
                task_type="supplement_review",
                trigger_reason=(
                    f"新增补件：{upload.file_name}；"
                    f"关联事项：{upload.related_item or '未指定'}"
                ),
                related_entity_type="document",
                related_entity_id=document_id,
                status=TaskStatus.PENDING,
                closure_condition="重新核验完成并由授权人员审核后方可关闭",
            )
            task = self.repository.add(created)
            task_id = str(created.task_id)
        status = TaskStatus(str(task["status"]))
        if status in {TaskStatus.PENDING, TaskStatus.RETURNED}:
            return self.repository.transition_task(task_id, TaskStatus.IN_PROGRESS, actor=actor)
        if status is TaskStatus.IN_PROGRESS:
            return task
        raise ValueError(
            f"当前任务状态为{status.value}，不能提交新补件。"
        )

    def _freeze_report(
        self,
        case_id: str,
        *,
        task_id: str,
        decision_id: str,
        status: str,
        actor: str,
    ) -> dict[str, Any]:
        view = self.read_model.build(case_id)
        if view is None:
            raise LookupError(f"案件不存在：{case_id}")
        previous = self.repository.find(
            "report_snapshots", filters={"case_id": case_id}, order_by="-snapshot_revision"
        )
        revision = max([int(row.get("snapshot_revision") or 0) for row in previous] + [0]) + 1
        payload = report_payload(view)
        payload["review_closure"] = {
            "task_id": task_id,
            "decision_id": decision_id,
            "status": status,
        }
        json_data = self.json_renderer(view)
        pdf_data = self.pdf_renderer(view)
        json_hash = hashlib.sha256(json_data).hexdigest()
        pdf_hash = hashlib.sha256(pdf_data).hexdigest()
        snapshot_data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        snapshot_hash = hashlib.sha256(snapshot_data).hexdigest()

        report_dir = self.report_root / case_id / f"v{revision:03d}"
        report_dir.mkdir(parents=True, exist_ok=False)
        json_path = report_dir / "case_report.json"
        pdf_path = report_dir / "case_report.pdf"
        json_path.write_bytes(json_data)
        pdf_path.write_bytes(pdf_data)

        rules = sorted({
            str(row.get("rule_version_id"))
            for row in self.repository.find(
                "verification_items", filters={"case_id": case_id, "is_current": 1}
            )
            if row.get("rule_version_id")
        })
        models = sorted({
            f"{row.get('model_name') or '未命名'}@{row.get('model_version') or '未标注'}"
            for row in self.repository.find("model_runs", filters={"case_id": case_id})
        })
        source_material = [
            (row.get("source_id"), row.get("sha256"), row.get("status"))
            for row in self.repository.find("source_records")
        ]
        source_manifest_hash = hashlib.sha256(
            json.dumps(source_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        report = ReportSnapshot(
            case_id=case_id,
            snapshot_revision=revision,
            generated_at=utc_now(),
            rule_versions_json=rules,
            model_versions_json=models,
            source_manifest_hash=source_manifest_hash,
            snapshot_json=payload,
            snapshot_hash=snapshot_hash,
            pdf_path=str(pdf_path),
            pdf_hash=pdf_hash,
            json_path=str(json_path),
            json_hash=json_hash,
            status=status,
        )
        try:
            with self.repository.transaction() as uow:
                uow.add(report)
                uow.add(AuditLog(
                    case_id=case_id,
                    action="report_snapshot_frozen_after_human_review",
                    actor=actor,
                    details_json={
                        "report_id": report.report_id,
                        "snapshot_revision": revision,
                        "task_id": task_id,
                        "decision_id": decision_id,
                        "status": status,
                        "pdf_sha256": pdf_hash,
                        "json_sha256": json_hash,
                        "previous_versions_retained": len(previous),
                    },
                ))
        except Exception:
            for path in (json_path, pdf_path):
                if path.exists():
                    path.unlink()
            if report_dir.exists():
                report_dir.rmdir()
            raise
        return self.repository.get("report_snapshots", report.report_id) or report.to_record()

    def _audit_failure(
        self,
        case_id: str,
        *,
        actor: str,
        action: str,
        details: dict[str, Any],
    ) -> None:
        self.repository.add(AuditLog(
            case_id=case_id,
            action=action,
            actor=actor,
            details_json=details,
        ))


class SupplementWorkflowHooks:
    """Route-ready facade kept independent from Phase 2 HTML templates."""

    def __init__(self, service: SupplementWorkflowService) -> None:
        self.service = service

    def post_supplement(
        self,
        case_id: str,
        *,
        file_name: str,
        content: bytes,
        mime_type: str,
        file_type: str = "补充材料",
        related_item: str | None = None,
        task_id: str | None = None,
        actor: str,
    ) -> SupplementWorkflowResult:
        return self.service.upload_parse_and_reassess(
            case_id,
            SupplementUpload(
                file_name=file_name,
                content=content,
                mime_type=mime_type,
                file_type=file_type,
                related_item=related_item,
            ),
            task_id=task_id,
            actor=actor,
        )

    def post_task_review(
        self,
        case_id: str,
        task_id: str,
        *,
        decision: str,
        reason: str,
        actor: str,
        actor_role: RoleType,
    ) -> HumanReviewResult:
        if decision not in {"approve", "reject"}:
            raise ValueError("审核决定仅支持approve或reject。")
        return self.service.review_task(
            case_id,
            task_id,
            approve=decision == "approve",
            reason=reason,
            actor=actor,
            actor_role=actor_role,
        )
