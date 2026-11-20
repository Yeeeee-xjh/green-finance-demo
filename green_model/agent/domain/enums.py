"""Stable persisted enums.

Enum values are deliberately English machine codes.  Chinese labels belong to
the presentation layer so data remains stable when wording changes.
"""

from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class CaseStatus(StringEnum):
    DRAFT = "draft"
    INGESTING = "ingesting"
    PARSE_REVIEW = "parse_review"
    CLASSIFYING = "classifying"
    VERIFYING = "verifying"
    ACTION_REQUIRED = "action_required"
    HUMAN_REVIEW = "human_review"
    MONITORING = "monitoring"
    CLOSED = "closed"
    FAILED = "failed"


class DocumentParseStatus(StringEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PARSING = "parsing"
    PARSED = "parsed"
    NEEDS_OCR = "needs_ocr"
    PARSE_FAILED = "parse_failed"
    HUMAN_VERIFIED = "human_verified"


class VerificationStatus(StringEnum):
    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    PENDING_VERIFICATION = "pending_verification"
    EVIDENCE_CONFLICT = "evidence_conflict"
    NOT_APPLICABLE = "not_applicable"
    CANNOT_DETERMINE = "cannot_determine"
    ATTRIBUTE_ONLY = "attribute_only"


class TaskStatus(StringEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    CLOSED = "closed"
    RETURNED = "returned"


class RiskLevel(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class RoleType(StringEnum):
    RELATIONSHIP_MANAGER = "relationship_manager"
    INDUSTRY_SPECIALIST = "industry_specialist"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    TEAM_LEAD = "team_lead"
    ADMINISTRATOR = "administrator"
    SYSTEM = "system"
    MIGRATION = "migration"


class SourceStatus(StringEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"
    SUPERSEDED = "superseded"
    INVALID = "invalid"
    PUBLIC_CHANNEL_NOT_OBTAINED = "public_channel_not_obtained"


class DataOrigin(StringEnum):
    USER_UPLOAD = "user_upload"
    PUBLIC_SOURCE = "public_source"
    SYSTEM_DERIVED = "system_derived"
    LEGACY_JSON = "legacy_json"
    LEGACY_DEMO = "legacy_demo"


class RiskDimension(StringEnum):
    """Stable machine codes for the five green-credit review dimensions."""

    CLAIM_CREDIBILITY = "claim_credibility"
    PROJECT_BOUNDARY_AND_USE = "project_boundary_and_use"
    TECHNICAL_AND_COMPLIANCE = "technical_and_compliance"
    IMPLEMENTATION_AND_FUNDS = "implementation_and_funds"
    PERFORMANCE_AND_CONTINUING_COMPLIANCE = "performance_and_continuing_compliance"


class CoverageStatus(StringEnum):
    ASSESSED = "assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    RULE_NOT_AVAILABLE = "rule_not_available"
    BANK_RULES_NOT_CONNECTED = "bank_rules_not_connected"
    MODEL_NOT_RUN = "model_not_run"
    MODEL_ABSTAINED = "model_abstained"
    NOT_APPLICABLE = "not_applicable"


RISK_DIMENSION_LABELS = {
    RiskDimension.CLAIM_CREDIBILITY: "绿色主张可信性",
    RiskDimension.PROJECT_BOUNDARY_AND_USE: "项目边界与融资用途",
    RiskDimension.TECHNICAL_AND_COMPLIANCE: "行业技术与合规落实",
    RiskDimension.IMPLEMENTATION_AND_FUNDS: "项目实施与资金执行",
    RiskDimension.PERFORMANCE_AND_CONTINUING_COMPLIANCE: "绩效兑现与持续合规",
}


COVERAGE_STATUS_LABELS = {
    CoverageStatus.ASSESSED: "已评估",
    CoverageStatus.INSUFFICIENT_EVIDENCE: "证据不足",
    CoverageStatus.RULE_NOT_AVAILABLE: "公开渠道未获取规则",
    CoverageStatus.BANK_RULES_NOT_CONNECTED: "银行内部规则未接入",
    CoverageStatus.MODEL_NOT_RUN: "模型未运行",
    CoverageStatus.MODEL_ABSTAINED: "模型已运行但弃权",
    CoverageStatus.NOT_APPLICABLE: "不适用",
}


CASE_STATUS_LABELS = {
    CaseStatus.DRAFT: "草稿",
    CaseStatus.INGESTING: "材料入库中",
    CaseStatus.PARSE_REVIEW: "解析待复核",
    CaseStatus.CLASSIFYING: "行业定标中",
    CaseStatus.VERIFYING: "风险核验中",
    CaseStatus.ACTION_REQUIRED: "待处理事项",
    CaseStatus.HUMAN_REVIEW: "待人工确认",
    CaseStatus.MONITORING: "监测中",
    CaseStatus.CLOSED: "已关闭",
    CaseStatus.FAILED: "处理失败",
}

DOCUMENT_STATUS_LABELS = {
    DocumentParseStatus.UPLOADED: "已上传",
    DocumentParseStatus.QUEUED: "排队中",
    DocumentParseStatus.PARSING: "解析中",
    DocumentParseStatus.PARSED: "已解析",
    DocumentParseStatus.NEEDS_OCR: "需要OCR",
    DocumentParseStatus.PARSE_FAILED: "解析失败",
    DocumentParseStatus.HUMAN_VERIFIED: "人工校验完成",
}

TASK_STATUS_LABELS = {
    TaskStatus.PENDING: "待处理",
    TaskStatus.IN_PROGRESS: "处理中",
    TaskStatus.PENDING_REVIEW: "待审核",
    TaskStatus.CLOSED: "已关闭",
    TaskStatus.RETURNED: "已退回",
}

VERIFICATION_STATUS_LABELS = {
    VerificationStatus.SATISFIED: "已证明",
    VerificationStatus.NOT_SATISFIED: "不满足",
    VerificationStatus.PENDING_VERIFICATION: "待补证",
    VerificationStatus.EVIDENCE_CONFLICT: "证据冲突",
    VerificationStatus.NOT_APPLICABLE: "不适用",
    VerificationStatus.CANNOT_DETERMINE: "无法判断",
    VerificationStatus.ATTRIBUTE_ONLY: "属性说明",
}

RISK_LEVEL_LABELS = {
    RiskLevel.LOW: "低",
    RiskLevel.MEDIUM: "中",
    RiskLevel.HIGH: "高",
    RiskLevel.CRITICAL: "严重",
    RiskLevel.UNKNOWN: "未知",
}

SOURCE_STATUS_LABELS = {
    SourceStatus.CANDIDATE: "候选来源",
    SourceStatus.VERIFIED: "已核验",
    SourceStatus.UNAVAILABLE: "不可获取",
    SourceStatus.SUPERSEDED: "已被替代",
    SourceStatus.INVALID: "无效",
    SourceStatus.PUBLIC_CHANNEL_NOT_OBTAINED: "公开渠道未获取",
}
