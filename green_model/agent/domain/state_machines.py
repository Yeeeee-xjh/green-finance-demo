"""Pure state-machine rules. Persistence and audit are handled by Repository."""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import TypeVar

from .enums import CaseStatus, DocumentParseStatus, StringEnum, TaskStatus


E = TypeVar("E", bound=StringEnum)


class InvalidTransition(ValueError):
    def __init__(self, machine: str, current: str, target: str):
        self.machine = machine
        self.current = current
        self.target = target
        super().__init__(f"{machine}非法状态流转：{current} -> {target}")


CASE_TRANSITIONS: Mapping[CaseStatus, Set[CaseStatus]] = {
    CaseStatus.DRAFT: {CaseStatus.INGESTING},
    CaseStatus.INGESTING: {CaseStatus.PARSE_REVIEW, CaseStatus.FAILED},
    CaseStatus.PARSE_REVIEW: {CaseStatus.INGESTING, CaseStatus.CLASSIFYING, CaseStatus.FAILED},
    CaseStatus.CLASSIFYING: {CaseStatus.PARSE_REVIEW, CaseStatus.VERIFYING, CaseStatus.FAILED},
    CaseStatus.VERIFYING: {CaseStatus.ACTION_REQUIRED, CaseStatus.HUMAN_REVIEW, CaseStatus.FAILED},
    CaseStatus.ACTION_REQUIRED: {CaseStatus.VERIFYING, CaseStatus.HUMAN_REVIEW, CaseStatus.FAILED},
    CaseStatus.HUMAN_REVIEW: {CaseStatus.ACTION_REQUIRED, CaseStatus.MONITORING, CaseStatus.CLOSED},
    CaseStatus.MONITORING: {CaseStatus.ACTION_REQUIRED, CaseStatus.HUMAN_REVIEW, CaseStatus.CLOSED},
    # FAILED is context-sensitive: it may only resume to failed_from_status.
    CaseStatus.FAILED: {
        CaseStatus.INGESTING,
        CaseStatus.PARSE_REVIEW,
        CaseStatus.CLASSIFYING,
        CaseStatus.VERIFYING,
        CaseStatus.ACTION_REQUIRED,
        CaseStatus.HUMAN_REVIEW,
        CaseStatus.MONITORING,
    },
    CaseStatus.CLOSED: set(),
}

DOCUMENT_TRANSITIONS: Mapping[DocumentParseStatus, Set[DocumentParseStatus]] = {
    DocumentParseStatus.UPLOADED: {DocumentParseStatus.QUEUED},
    DocumentParseStatus.QUEUED: {DocumentParseStatus.PARSING, DocumentParseStatus.PARSE_FAILED},
    DocumentParseStatus.PARSING: {
        DocumentParseStatus.PARSED,
        DocumentParseStatus.NEEDS_OCR,
        DocumentParseStatus.PARSE_FAILED,
    },
    DocumentParseStatus.NEEDS_OCR: {DocumentParseStatus.QUEUED, DocumentParseStatus.PARSING},
    DocumentParseStatus.PARSE_FAILED: {DocumentParseStatus.QUEUED},
    DocumentParseStatus.PARSED: {DocumentParseStatus.HUMAN_VERIFIED, DocumentParseStatus.QUEUED},
    DocumentParseStatus.HUMAN_VERIFIED: set(),
}

TASK_TRANSITIONS: Mapping[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {TaskStatus.PENDING_REVIEW},
    TaskStatus.PENDING_REVIEW: {TaskStatus.CLOSED, TaskStatus.RETURNED},
    TaskStatus.RETURNED: {TaskStatus.IN_PROGRESS},
    TaskStatus.CLOSED: set(),
}


def require_transition(
    machine_name: str,
    current: E,
    target: E,
    transitions: Mapping[E, Set[E]],
) -> None:
    if target not in transitions.get(current, set()):
        raise InvalidTransition(machine_name, current.value, target.value)


def require_case_transition(
    current: CaseStatus,
    target: CaseStatus,
    *,
    failed_from_status: CaseStatus | None = None,
) -> None:
    require_transition("案件", current, target, CASE_TRANSITIONS)
    if current is CaseStatus.FAILED and target is not failed_from_status:
        raise InvalidTransition("案件（失败恢复）", current.value, target.value)
