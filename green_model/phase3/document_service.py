"""Transactional document-to-evidence processing for Phase 3."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from green_model.agent.domain.enums import DataOrigin, DocumentParseStatus, RoleType, VerificationStatus
from green_model.agent.domain.models import AuditLog, EvidenceSnippet, ExtractionRun, ProjectFact, utc_now
from green_model.agent.storage import SQLiteRepository

from .parsing import LocalDocumentParser, ParsedDocument, ParsedFragment, file_sha256


@dataclass(frozen=True)
class ParseOutcome:
    status: str
    run_id: str
    evidence_count: int
    fact_count: int
    page_count: int | None
    message: str


MONEY_PATTERNS = (
    ("investment_amount", re.compile(r"(?:项目)?总投资(?:额)?(?:为|约为|：|:)?\s*([0-9][0-9,.]*)\s*(亿元|万元|元)")),
    ("financing_amount", re.compile(r"(?:本次)?(?:贷款|融资|拟募集资金|拟使用募集资金)(?:金额|规模|总额)?(?:为|约为|：|:)?\s*([0-9][0-9,.]*)\s*(亿元|万元|元)")),
    ("contract_amount", re.compile(r"(?:合同|采购合同)(?:金额|总额)(?:为|：|:)?\s*([0-9][0-9,.]*)\s*(亿元|万元|元)")),
    ("invoice_amount", re.compile(r"发票(?:金额|价税合计)(?:为|：|:)?\s*([0-9][0-9,.]*)\s*(亿元|万元|元)")),
    ("payment_amount", re.compile(r"(?:已)?(?:支付|付款)(?:金额|总额)(?:为|：|:)?\s*([0-9][0-9,.]*)\s*(亿元|万元|元)")),
)
CAPACITY_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(万千瓦|千瓦|兆瓦|MW|kW)", re.IGNORECASE)
GENERATION_PATTERN = re.compile(r"(?:年|实际|设计)?(?:上网)?发电量(?:为|约为|：|:)?\s*([0-9][0-9,.]*)\s*(亿千瓦时|万千瓦时|千瓦时|GWh|MWh|kWh)", re.IGNORECASE)
EMISSION_PATTERN = re.compile(r"(?:二氧化碳|温室气体|碳)(?:排放量|减排量)(?:为|约为|：|:)?\s*([0-9][0-9,.]*)\s*(万吨|吨)(?:CO2e|二氧化碳当量)?", re.IGNORECASE)
ENERGY_PATTERN = re.compile(r"(?:综合)?能耗(?:为|约为|：|:)?\s*([0-9][0-9,.]*)\s*(万吨标准煤|吨标准煤|千克标准煤)")
PROGRESS_PATTERN = re.compile(r"(?:工程|建设|形象)?进度(?:已完成|为|：|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%")
PROJECT_NAME_PATTERN = re.compile(r"项目名称(?:为|：|:)?\s*([^\n；；。]{2,100})")
APPROVAL_NUMBER_PATTERN = re.compile(r"(?:核准|备案|环评批复)(?:文号|编号|号)?(?:为|：|:)?\s*([\u4e00-\u9fa5A-Za-z0-9〔〕【】\[\]—\-()]+\d+号?)")
FUNDING_PURPOSE_PATTERN = re.compile(r"(?:贷款|融资|募集资金)(?:主要)?用途(?:为|：|:)?\s*([^\n；。]{2,160})")
STAGE_TERMS = (
    ("已建成", "运营期"),
    ("投入运行", "运营期"),
    ("投产", "运营期"),
    ("建设中", "建设期"),
    ("开工", "建设期"),
    ("拟建", "建设准备期"),
    ("备案", "建设准备期"),
)
ACTIVITY_TERMS = (
    ("风力发电", "风电", "风力发电设施建设或运营"),
    ("风电", "风电", "风力发电设施建设或运营"),
    ("光伏", "光伏", "太阳能发电设施建设或运营"),
    ("生物质发电", "生物质能发电", "生物质能发电设施建设或运营"),
    ("公共电汽车客运", "公共电汽车客运", "新能源城市公交运营"),
    ("新能源公交", "公共电汽车客运", "新能源城市公交运营"),
    ("储能", "储能", "储能设施建设或运营"),
    ("炼铁", "3110 炼铁", "炼铁生产或技术改造"),
    ("钢铁", "钢铁", "钢铁生产或技术改造"),
    ("水泥", "3011 水泥制造", "水泥生产或技术改造"),
)


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _money_yuan(value: Decimal, unit: str) -> Decimal:
    multiplier = {"亿元": Decimal("100000000"), "万元": Decimal("10000"), "元": Decimal("1")}[unit]
    return value * multiplier


def _normalized(value: Decimal, unit: str, mapping: dict[str, tuple[Decimal, str]]) -> tuple[Decimal, str]:
    multiplier, target_unit = mapping[unit]
    return value * multiplier, target_unit


def _fact_candidates(fragment: ParsedFragment, evidence_id: str) -> list[tuple[ProjectFact, str]]:
    text = fragment.text
    candidates: list[tuple[ProjectFact, str]] = []
    for category, pattern in MONEY_PATTERNS:
        for match in pattern.finditer(text):
            value = _decimal(match.group(1))
            if value is None:
                continue
            candidates.append((ProjectFact(
                case_id="",
                fact_category=category,
                raw_value=match.group(0),
                normalized_value=str(_money_yuan(value, match.group(2))),
                unit="元",
                value_nature="document_fact",
                method="deterministic_regex",
                match_basis=f"原文匹配：{match.group(0)}",
            ), evidence_id))
    for match in CAPACITY_PATTERN.finditer(text):
        value = _decimal(match.group(1))
        if value is None:
            continue
        unit = match.group(2)
        normalized = value
        if unit == "万千瓦":
            normalized *= Decimal("10")
        elif unit in {"千瓦", "kW"}:
            normalized /= Decimal("1000")
        candidates.append((ProjectFact(
            case_id="",
            fact_category="installed_capacity",
            raw_value=match.group(0),
            normalized_value=str(normalized),
            unit="MW",
            value_nature="document_fact",
            method="deterministic_regex",
            match_basis=f"原文匹配：{match.group(0)}",
        ), evidence_id))
    quantitative_patterns = (
        ("annual_generation", GENERATION_PATTERN, {
            "亿千瓦时": (Decimal("100000"), "MWh"),
            "万千瓦时": (Decimal("10"), "MWh"),
            "千瓦时": (Decimal("0.001"), "MWh"),
            "GWh": (Decimal("1000"), "MWh"),
            "MWh": (Decimal("1"), "MWh"),
            "kWh": (Decimal("0.001"), "MWh"),
        }),
        ("carbon_emission", EMISSION_PATTERN, {
            "万吨": (Decimal("10000"), "tCO2e"),
            "吨": (Decimal("1"), "tCO2e"),
        }),
        ("energy_consumption", ENERGY_PATTERN, {
            "万吨标准煤": (Decimal("10000"), "tce"),
            "吨标准煤": (Decimal("1"), "tce"),
            "千克标准煤": (Decimal("0.001"), "tce"),
        }),
        ("construction_progress", PROGRESS_PATTERN, {
            "%": (Decimal("1"), "%"),
        }),
    )
    for category, pattern, conversion in quantitative_patterns:
        for match in pattern.finditer(text):
            value = _decimal(match.group(1))
            if value is None:
                continue
            source_unit = match.group(2) if match.lastindex and match.lastindex >= 2 else "%"
            normalized_value, unit = _normalized(value, source_unit, conversion)
            candidates.append((ProjectFact(
                case_id="",
                fact_category=category,
                raw_value=match.group(0),
                normalized_value=str(normalized_value),
                unit=unit,
                value_nature="document_fact",
                method="deterministic_regex",
                match_basis=f"原文匹配：{match.group(0)}",
            ), evidence_id))
    text_patterns = (
        ("project_name", PROJECT_NAME_PATTERN),
        ("approval_number", APPROVAL_NUMBER_PATTERN),
        ("funding_purpose", FUNDING_PURPOSE_PATTERN),
    )
    for category, pattern in text_patterns:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            candidates.append((ProjectFact(
                case_id="",
                fact_category=category,
                raw_value=value,
                normalized_value=value,
                value_nature="document_fact",
                method="deterministic_regex",
                match_basis=f"原文匹配：{match.group(0)}",
            ), evidence_id))
    for term, stage in STAGE_TERMS:
        if term in text:
            candidates.append((ProjectFact(
                case_id="",
                fact_category="project_stage",
                raw_value=stage,
                value_nature="document_signal",
                method="controlled_term_match",
                match_basis=f"原文出现“{term}”；阶段仍需结合日期和手续人工确认。",
            ), evidence_id))
            break
    for term, industry, activity in ACTIVITY_TERMS:
        if term in text:
            candidates.append((ProjectFact(
                case_id="",
                fact_category="industry",
                raw_value=industry,
                value_nature="document_signal",
                method="controlled_term_match",
                match_basis=f"原文出现行业活动词“{term}”。",
            ), evidence_id))
            candidates.append((ProjectFact(
                case_id="",
                fact_category="project_activity",
                raw_value=activity,
                value_nature="document_signal",
                method="controlled_term_match",
                match_basis=f"原文出现项目活动词“{term}”。",
            ), evidence_id))
            break
    return candidates


class DocumentProcessingService:
    def __init__(self, repository: SQLiteRepository, parser: LocalDocumentParser | None = None):
        self.repository = repository
        self.parser = parser or LocalDocumentParser()

    def process(self, case_id: str, doc_id: str, *, actor: str = "system") -> ParseOutcome:
        document = self.repository.get("documents", doc_id)
        if document is None or document.get("case_id") != case_id:
            raise LookupError("未找到当前案件中的材料")
        path = Path(str(document.get("original_path") or ""))
        run = ExtractionRun(
            case_id=case_id,
            doc_id=doc_id,
            parser_name="pending",
            parser_version=self.parser.version,
            input_sha256=document.get("sha256"),
            status="running",
            started_at=utc_now(),
        )
        with self.repository.transaction() as uow:
            uow.add(run)
            current = uow.require("documents", doc_id)
            uow.update("documents", doc_id, {
                "parse_status": DocumentParseStatus.PARSING.value,
                "parse_failure_reason": None,
            }, expected_version=current["row_version"])
        try:
            actual_hash = file_sha256(path)
            expected_hash = document.get("sha256")
            if expected_hash and actual_hash != expected_hash:
                raise ValueError("文件哈希与入库记录不一致，已停止解析")
            parsed = self.parser.parse(path, mime_type=document.get("mime_type"))
            return self._commit_result(case_id, document, run, parsed, actual_hash, actor)
        except Exception as exc:
            message = str(exc)[:800]
            with self.repository.transaction() as uow:
                current_run = uow.require("extraction_runs", run.extraction_run_id)
                uow.update("extraction_runs", run.extraction_run_id, {
                    "status": "failed",
                    "finished_at": utc_now(),
                    "error_message": message,
                }, expected_version=current_run["row_version"])
                current_doc = uow.require("documents", doc_id)
                uow.update("documents", doc_id, {
                    "parse_status": DocumentParseStatus.PARSE_FAILED.value,
                    "parse_failure_reason": message,
                }, expected_version=current_doc["row_version"])
                uow.add(AuditLog(
                    case_id=case_id,
                    action="document_parse_failed",
                    actor=actor,
                    actor_role=RoleType.SYSTEM,
                    file_hash=document.get("sha256"),
                    details_json={"document": document.get("file_name"), "reason": message},
                ))
            return ParseOutcome("failed", run.extraction_run_id, 0, 0, None, message)

    def _commit_result(
        self,
        case_id: str,
        document: dict[str, Any],
        run: ExtractionRun,
        parsed: ParsedDocument,
        actual_hash: str,
        actor: str,
    ) -> ParseOutcome:
        if parsed.needs_ocr:
            with self.repository.transaction() as uow:
                current_run = uow.require("extraction_runs", run.extraction_run_id)
                uow.update("extraction_runs", run.extraction_run_id, {
                    "parser_name": parsed.parser_name,
                    "parser_version": parsed.parser_version,
                    "input_sha256": actual_hash,
                    "status": "needs_ocr",
                    "finished_at": utc_now(),
                    "parsed_pages": parsed.page_count,
                    "ocr_status": "pending",
                    "error_message": parsed.ocr_reason,
                }, expected_version=current_run["row_version"])
                current_doc = uow.require("documents", document["doc_id"])
                uow.update("documents", document["doc_id"], {
                    "page_count": parsed.page_count,
                    "parse_status": DocumentParseStatus.NEEDS_OCR.value,
                    "parse_failure_reason": parsed.ocr_reason,
                    "sha256": actual_hash,
                }, expected_version=current_doc["row_version"])
                uow.add(AuditLog(
                    case_id=case_id,
                    action="document_requires_ocr",
                    actor=actor,
                    actor_role=RoleType.SYSTEM,
                    file_hash=actual_hash,
                    details_json={"document": document.get("file_name"), "pages": parsed.page_count},
                ))
            return ParseOutcome("needs_ocr", run.extraction_run_id, 0, 0, parsed.page_count, parsed.ocr_reason or "需要OCR")

        evidence_count = 0
        fact_count = 0
        seen_facts: set[tuple[str | None, str | None, str | None, str]] = set()
        with self.repository.transaction() as uow:
            for fragment in parsed.fragments:
                if not fragment.text.strip():
                    continue
                evidence = EvidenceSnippet(
                    case_id=case_id,
                    doc_id=document["doc_id"],
                    source_id=document.get("source_id"),
                    extraction_run_id=run.extraction_run_id,
                    page_number=fragment.page_number,
                    bbox=fragment.bbox,
                    locator_type=fragment.locator_type,
                    locator=fragment.locator,
                    raw_excerpt=fragment.text,
                    text_sha256=hashlib.sha256(fragment.text.encode("utf-8")).hexdigest(),
                    extraction_method=fragment.extraction_method,
                    table_cell=fragment.table_cell,
                    verification_status=VerificationStatus.PENDING_VERIFICATION,
                    record_origin=DataOrigin.SYSTEM_DERIVED,
                )
                uow.add(evidence)
                evidence_count += 1
                for fact, evidence_id in _fact_candidates(fragment, evidence.evidence_id):
                    fact.case_id = case_id
                    fact.extraction_run_id = run.extraction_run_id
                    key = (fact.fact_category, fact.normalized_value, fact.unit, str(fact.raw_value))
                    if key in seen_facts:
                        continue
                    seen_facts.add(key)
                    uow.add(fact)
                    uow.insert("fact_evidence_links", {
                        "fact_id": fact.fact_id,
                        "evidence_id": evidence_id,
                        "link_role": "source",
                    })
                    fact_count += 1
            current_run = uow.require("extraction_runs", run.extraction_run_id)
            uow.update("extraction_runs", run.extraction_run_id, {
                "parser_name": parsed.parser_name,
                "parser_version": parsed.parser_version,
                "input_sha256": actual_hash,
                "status": "completed",
                "finished_at": utc_now(),
                "parsed_pages": parsed.page_count,
                "ocr_status": "not_required",
                "output_revision": 1,
            }, expected_version=current_run["row_version"])
            current_doc = uow.require("documents", document["doc_id"])
            uow.update("documents", document["doc_id"], {
                "page_count": parsed.page_count,
                "parse_status": DocumentParseStatus.PARSED.value,
                "parse_failure_reason": None,
                "sha256": actual_hash,
            }, expected_version=current_doc["row_version"])
            uow.add(AuditLog(
                case_id=case_id,
                action="document_parsed",
                actor=actor,
                actor_role=RoleType.SYSTEM,
                file_hash=actual_hash,
                details_json={
                    "document": document.get("file_name"),
                    "parser": parsed.parser_name,
                    "pages": parsed.page_count,
                    "evidence_count": evidence_count,
                    "fact_count": fact_count,
                },
            ))
        return ParseOutcome(
            "completed",
            run.extraction_run_id,
            evidence_count,
            fact_count,
            parsed.page_count,
            f"解析完成：形成 {evidence_count} 条证据片段、{fact_count} 条项目事实。",
        )
