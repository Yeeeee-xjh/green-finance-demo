"""Fail-closed qualification and density assessment for Phase 3.6.

Counts are never trusted from a research manifest.  A rule contributes only
after its underlying master row, official source, local SHA-256, scope,
application mapping and evidence linkage have all been revalidated.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from green_model.agent.domain.models import stable_id, utc_now


POLICY_VERSION = "phase36-v1"
DENSITY_GATES = {
    "process": 6,
    "equipment": 8,
    "standard": 5,
    "indicator": 8,
    "permit": 5,
    "document": 6,
    "evidence": 10,
    "risk": 8,
    "term": 8,
    "postloan": 3,
    "route": 2,
}

MODULE_TABLES = {
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

REQUIRED_FIELDS = {
    "process": ("title", "content", "source_locator"),
    "equipment": ("title", "content", "source_locator"),
    "route": ("title", "content", "source_locator"),
    "standard": ("applicability", "source_page"),
    "indicator": ("indicator_name", "definition_text", "source_page"),
    "threshold": (
        "threshold_text", "operator", "threshold_value", "unit",
        "applicable_scope", "effective_at", "source_page", "source_sha256",
    ),
    "permit": ("permit_name", "requirement_text", "applicable_stage", "source_page"),
    "document": ("document_name", "requirement_text", "applicable_stage", "source_page"),
    "evidence": ("evidence_object", "requirement_text", "acceptable_evidence", "source_page"),
    "risk": ("risk_title", "risk_description", "review_focus", "source_page"),
    "term": ("term", "definition_text", "source_page"),
    "postloan": ("indicator_name", "definition_text", "frequency", "evidence_object", "source_page"),
}

EXPLICIT_ONLY = {"standard", "indicator", "threshold", "permit", "document"}
DERIVED_ALLOWED = {"process", "equipment", "evidence", "risk", "term", "postloan", "route"}
VALID_TASKS = {"补件", "冲突核实", "规则核验", "现场核验", "贷后预警"}
VALID_THRESHOLD_OPERATORS = {"<", "<=", "=", ">=", ">", "≤", "≥"}
PLACEHOLDERS = {"", "-", "—", "待补充", "待核验", "待确认", "未获取", "公开渠道未获取"}

# These fields define business-content identity.  Source/version metadata is
# deliberately excluded: the same rule copied under a second source must not
# inflate package density.
FINGERPRINT_FIELDS = {
    "process": ("title", "content"),
    "equipment": ("title", "content"),
    "route": ("title", "content"),
    "standard": ("standard_id", "applicability"),
    "indicator": ("indicator_name", "definition_text", "formula_text", "unit"),
    "threshold": (
        "threshold_text", "operator", "threshold_value", "unit", "applicable_scope",
    ),
    "permit": ("permit_name", "requirement_text", "applicable_stage"),
    "document": ("document_name", "requirement_text", "applicable_stage"),
    "evidence": ("evidence_object", "requirement_text", "acceptable_evidence"),
    "risk": ("risk_title", "risk_description", "review_focus"),
    "term": ("term", "definition_text"),
    "postloan": ("indicator_name", "definition_text", "frequency", "evidence_object"),
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _present(value: Any) -> bool:
    return _text(value) not in PLACEHOLDERS


def _normalise(value: Any) -> str:
    return " ".join(_text(value).split()).casefold()


def content_fingerprint(module: str, record: dict[str, Any]) -> str:
    """Return the canonical content fingerprint used for density de-duplication."""
    if module not in FINGERPRINT_FIELDS:
        raise ValueError(f"不支持的密度模块：{module}")
    payload = [module]
    payload.extend(_normalise(record.get(field)) for field in FINGERPRINT_FIELDS[module])
    return hashlib.sha256("\x1f".join(payload).encode("utf-8")).hexdigest()


def _precise_locator(value: Any, *, standard: bool = False) -> bool:
    locator = _text(value)
    if not _present(locator) or locator in {"全文", "正文", "官网", "原文"}:
        return False
    if any(character.isdigit() for character in locator):
        return True
    if standard and any(token in locator for token in ("官方标准信息页", "官方元数据页")):
        return True
    if any(token in locator for token in ("附录", "总则", "适用范围", "定义")):
        return True
    chinese_number = "〇零一二三四五六七八九十百千万两"
    # Official web notices often have no stable PDF page but do have precise
    # structural locators, e.g. “通知第八、十条” or “正文第二部分（一）”.
    if re.search(
        rf"第[{chinese_number}\d、至—\-]+(?:页|条|章|节|部分|款|项|表)", locator
    ):
        return True
    if any(token in locator for token in ("正文", "网页", "通知", "公告", "附件")) and re.search(
        rf"[（(][{chinese_number}\d]+[）)]", locator
    ):
        return True
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_errors(
    effective_at: Any,
    expires_at: Any,
    *,
    subject: str,
) -> list[str]:
    """Reject records that are not currently effective or have malformed dates."""
    errors: list[str] = []
    effective = _text(effective_at)
    if effective:
        try:
            if date.fromisoformat(effective[:10]) > date.today():
                errors.append(f"{subject}尚未生效")
        except ValueError:
            errors.append(f"{subject}生效日无法校验")
    expires = _text(expires_at)
    if expires:
        try:
            if date.fromisoformat(expires[:10]) < date.today():
                errors.append(f"{subject}已过有效期")
        except ValueError:
            errors.append(f"{subject}有效期无法校验")
    return errors


def _columns(connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


class DensityAssessor:
    """Validate registered rule rows and persist an auditable density result."""

    def __init__(self, connection):
        self.connection = connection

    def _source_errors(self, source: dict[str, Any], module: str) -> list[str]:
        errors: list[str] = []
        if not source or source.get("formal_rule_eligible") != 1:
            return ["来源未确认为官方可用依据"]
        if "official" not in _text(source.get("authority_level")).casefold():
            errors.append("来源权威级别未标识为官方")
        if source.get("superseded_by_source_id") or source.get("availability_status") == "superseded":
            errors.append("来源已被替代或废止")
        if source.get("availability_status") not in {"full_text_obtained", "official_summary_only"}:
            errors.append("官方公开内容未取得")
        path = Path(_text(source.get("local_path")))
        if not path.is_file():
            errors.append("本地来源原件缺失")
        elif _sha256(path) != _text(source.get("sha256")):
            errors.append("本地原件SHA-256与来源台账不一致")
        errors.extend(
            _date_errors(
                source.get("effective_at"), source.get("expires_at"), subject="来源"
            )
        )
        # A catalogue/metadata record is a standard reference, never a source
        # for numeric or substantive technical requirements.
        if module != "standard" and source.get("availability_status") == "official_summary_only":
            errors.append("仅官方摘要/元数据不足以支撑该模块实质规则")
        return errors

    def _underlying(self, item: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        module = item["module"]
        expected_table, key = MODULE_TABLES[module]
        errors: list[str] = []
        if item["record_table"] != expected_table:
            return None, ["模块与底层表不匹配"]
        row = self.connection.execute(
            f"SELECT * FROM {expected_table} WHERE {key}=?", (item["record_id"],)
        ).fetchone()
        if row is None:
            return None, ["底层业务记录不存在"]
        record = dict(row)
        if _text(record.get("industry_code")) != item["industry_code"]:
            errors.append("底层记录行业不匹配")
        if _text(record.get("source_id")) != item["source_id"]:
            errors.append("底层记录来源不匹配")
        if "scope_status" in record and record["scope_status"] != "core":
            errors.append("仅相邻活动或未完成核心适用复核")
        if module in {"process", "equipment", "route"} and record.get("module") != module:
            errors.append("知识条目模块标签不匹配")
        missing = [name for name in REQUIRED_FIELDS[module] if not _present(record.get(name))]
        if missing:
            errors.append("底层记录缺字段：" + "、".join(missing))
        derivation = _text(record.get("derivation_type"))
        if module in EXPLICIT_ONLY and module != "standard" and derivation != "policy_explicit":
            errors.append("该模块不允许用来源派生内容充当政策明文")
        if module in DERIVED_ALLOWED and derivation not in {"policy_explicit", "source_derived"}:
            errors.append("来源派生类型缺失或不合法")
        if "formal_rule_eligible" in record and record.get("formal_rule_eligible") != 1:
            errors.append("底层业务记录未标记为正式规则")
        locator_field = "source_locator" if module in {"process", "equipment", "route"} else "source_page"
        if not _precise_locator(record.get(locator_field), standard=module == "standard"):
            errors.append("来源定位不够精确")
        if module == "standard":
            standard = self.connection.execute(
                "SELECT * FROM standard_catalog WHERE standard_id=?", (record["standard_id"],)
            ).fetchone()
            if standard is None:
                errors.append("标准目录记录不存在")
            else:
                standard = dict(standard)
                if not _present(standard.get("standard_name")):
                    errors.append("标准名称缺失")
                if standard.get("full_text_status") not in {
                    "full_text_obtained", "official_summary_only"
                }:
                    errors.append("标准全文或官方元数据未取得")
                if _text(standard.get("source_id")) != _text(record.get("source_id")):
                    errors.append("标准目录与行业适用记录的来源不一致")
                errors.extend(
                    _date_errors(
                        standard.get("effective_at"),
                        standard.get("expires_at"),
                        subject="标准",
                    )
                )
                standard_source_row = self.connection.execute(
                    "SELECT * FROM source_manifest WHERE source_id=?", (standard["source_id"],)
                ).fetchone()
                standard_source = dict(standard_source_row) if standard_source_row else {}
                errors.extend(self._source_errors(standard_source, "standard"))
        if module == "threshold":
            if record.get("threshold_kind") != "explicit_numeric":
                errors.append("非政策明文数值阈值")
            try:
                float(_text(record.get("threshold_value")))
            except ValueError:
                errors.append("阈值不是可计算纯数值")
            if _text(record.get("operator")) not in VALID_THRESHOLD_OPERATORS:
                errors.append("阈值比较符不受支持")
            errors.extend(
                _date_errors(
                    record.get("effective_at"),
                    record.get("expires_at"),
                    subject="阈值",
                )
            )
            if _text(record.get("source_sha256")) != _text(item.get("source_sha256")):
                errors.append("阈值来源哈希不一致")
        return record, errors

    def _mapping_errors(self, item: dict[str, Any]) -> list[str]:
        mapping = self.connection.execute(
            "SELECT * FROM rule_application_mappings WHERE phase36_item_id=?",
            (item["phase36_item_id"],),
        ).fetchone()
        if mapping is None:
            return ["缺少核验项与任务映射"]
        mapping = dict(mapping)
        errors: list[str] = []
        if mapping["industry_code"] != item["industry_code"]:
            errors.append("业务映射行业不匹配")
        if mapping["task_type"] not in VALID_TASKS:
            errors.append("任务类型不合法")
        if not _present(mapping.get("verification_item_template")):
            errors.append("核验项模板缺失")
        links = self.connection.execute(
            """SELECT e.*, s.formal_rule_eligible AS source_formal_rule_eligible,
                      s.availability_status AS source_availability_status,
                      s.authority_level AS source_authority_level,
                      s.local_path AS source_local_path, s.sha256 AS source_sha256,
                      s.superseded_by_source_id AS source_superseded_by,
                      s.effective_at AS source_effective_at,
                      s.expires_at AS source_expires_at
               FROM rule_application_evidence_links l
               JOIN evidence_requirements e
                 ON e.evidence_requirement_id=l.evidence_requirement_id
               JOIN source_manifest s ON s.source_id=e.source_id
               WHERE l.application_mapping_id=?""",
            (mapping["application_mapping_id"],),
        ).fetchall()
        if not links:
            errors.append("未绑定可验证的证据要求")
        else:
            linked_ids: set[str] = set()
            for link_row in links:
                link = dict(link_row)
                linked_ids.add(link["evidence_requirement_id"])
                if link["industry_code"] != item["industry_code"]:
                    errors.append("绑定了其他行业的证据要求")
                if link.get("scope_status") != "core":
                    errors.append("绑定证据未完成核心适用复核")
                missing = [
                    name for name in REQUIRED_FIELDS["evidence"] if not _present(link.get(name))
                ]
                if missing:
                    errors.append("绑定证据缺字段：" + "、".join(missing))
                evidence_source = {
                    "formal_rule_eligible": link.get("source_formal_rule_eligible"),
                    "availability_status": link.get("source_availability_status"),
                    "authority_level": link.get("source_authority_level"),
                    "local_path": link.get("source_local_path"),
                    "sha256": link.get("source_sha256"),
                    "superseded_by_source_id": link.get("source_superseded_by"),
                    "effective_at": link.get("source_effective_at"),
                    "expires_at": link.get("source_expires_at"),
                }
                errors.extend(self._source_errors(evidence_source, "evidence"))
                if not _precise_locator(link.get("source_page")):
                    errors.append("绑定证据的来源定位不精确")
            try:
                declared_raw = json.loads(mapping["evidence_requirement_ids_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                errors.append("证据要求ID清单不是有效JSON")
            else:
                if not isinstance(declared_raw, list) or not all(
                    isinstance(value, str) and value.strip() for value in declared_raw
                ):
                    errors.append("证据要求ID清单必须是非空字符串数组")
                    declared_ids: set[str] = set()
                else:
                    declared_ids = set(declared_raw)
                    if len(declared_ids) != len(declared_raw):
                        errors.append("证据要求ID清单存在重复项")
                if declared_ids != linked_ids:
                    errors.append("声明的证据ID与实际绑定不一致")
        return errors

    def qualify_all(self, industry_code: str) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT * FROM phase36_rule_items WHERE industry_code=? ORDER BY module, phase36_item_id",
            (industry_code,),
        ).fetchall()
        counts: Counter[str] = Counter()
        for raw in rows:
            item = dict(raw)
            errors: list[str] = []
            if item["lineage_kind"] == "simulation":
                errors.append("模拟规则永不计入正式密度")
            if (
                item["module"] in EXPLICIT_ONLY
                and item["lineage_kind"] != "official_public_source"
            ):
                errors.append("政策明文模块必须标记为官方公开来源")
            source_row = self.connection.execute(
                "SELECT * FROM source_manifest WHERE source_id=?", (item["source_id"],)
            ).fetchone()
            source = dict(source_row) if source_row else {}
            errors.extend(self._source_errors(source, item["module"]))
            if _text(item.get("source_sha256")) != _text(source.get("sha256")):
                errors.append("规则项来源哈希与来源台账不一致")
            record, row_errors = self._underlying(item)
            errors.extend(row_errors)
            if record is not None:
                locator_field = (
                    "source_locator"
                    if item["module"] in {"process", "equipment", "route"}
                    else "source_page"
                )
                if _text(item.get("source_locator")) != _text(record.get(locator_field)):
                    errors.append("规则项定位与底层记录不一致")
                expected_fingerprint = content_fingerprint(item["module"], record)
                if _text(item.get("content_fingerprint")) != expected_fingerprint:
                    errors.append("内容指纹缺失或与底层记录不一致")
                derivation = _text(record.get("derivation_type"))
                if (
                    item["lineage_kind"] == "official_public_source"
                    and derivation == "source_derived"
                ):
                    errors.append("来源派生内容不得标记为政策明文")
                if (
                    item["lineage_kind"] == "source_derived"
                    and derivation == "policy_explicit"
                ):
                    errors.append("政策明文的血缘标记不一致")
            errors.extend(self._mapping_errors(item))
            errors = list(dict.fromkeys(errors))
            status = "qualified" if not errors else "rejected"
            eligible = int(not errors)
            reasons_json = json.dumps(errors, ensure_ascii=False)
            if (
                item.get("validation_status") != status
                or item.get("validation_reasons_json") != reasons_json
                or item.get("formal_density_eligible") != eligible
                or item.get("eligibility_policy_version") != POLICY_VERSION
            ):
                self.connection.execute(
                    """UPDATE phase36_rule_items
                       SET validation_status=?, validation_reasons_json=?,
                           formal_density_eligible=?, eligibility_policy_version=?,
                           updated_at=?, row_version=row_version+1
                       WHERE phase36_item_id=?""",
                    (
                        status, reasons_json, eligible, POLICY_VERSION, utc_now(),
                        item["phase36_item_id"],
                    ),
                )
            if eligible:
                counts[item["module"]] += 1
        return dict(counts)

    def assess(
        self,
        industry_code: str,
        *,
        target_tier: str,
        numeric_threshold_expected: bool,
        threshold_basis_note: str,
    ) -> dict[str, Any]:
        if not _present(threshold_basis_note):
            raise ValueError("必须记录数值阈值门槛的判定依据")
        qualified = self.qualify_all(industry_code)
        raw = dict(Counter(row["module"] for row in self.connection.execute(
            "SELECT module FROM phase36_rule_items WHERE industry_code=?", (industry_code,)
        )))
        simulations = self.connection.execute(
            "SELECT COUNT(*) AS n FROM simulation_rule_items WHERE industry_code=?", (industry_code,)
        ).fetchone()["n"]
        simulations += self.connection.execute(
            """SELECT COUNT(*) AS n FROM phase36_rule_items
               WHERE industry_code=? AND lineage_kind='simulation'""", (industry_code,)
        ).fetchone()["n"]
        explicit = dict(Counter(row["module"] for row in self.connection.execute(
            """SELECT module FROM phase36_rule_items
               WHERE industry_code=? AND validation_status='qualified'
                 AND lineage_kind='official_public_source'""", (industry_code,)
        )))
        derived = dict(Counter(row["module"] for row in self.connection.execute(
            """SELECT module FROM phase36_rule_items
               WHERE industry_code=? AND validation_status='qualified'
                 AND lineage_kind='source_derived'""", (industry_code,)
        )))
        gates = dict(DENSITY_GATES)
        effective_threshold_expected = bool(numeric_threshold_expected or raw.get("threshold", 0))
        if effective_threshold_expected:
            gates["threshold"] = 5
        unmet = [
            {"module": module, "required": required, "qualified": qualified.get(module, 0)}
            for module, required in gates.items() if qualified.get(module, 0) < required
        ]
        score = round(sum(min(qualified.get(m, 0) / n, 1.0) for m, n in gates.items()) * 100 / len(gates))
        if target_tier == "base" or industry_code == "5413":
            status = "base_only"
        elif not unmet:
            status = "depth_public_sources"
        elif sum(qualified.values()):
            status = "partial_public_sources"
        else:
            status = "base_only" if target_tier == "base" else "pending"
        threshold_count = qualified.get("threshold", 0)
        if effective_threshold_expected:
            if threshold_count >= 5:
                threshold_status = "met"
            elif threshold_count == 0 and raw.get("threshold", 0) == 0:
                threshold_status = "public_channel_not_obtained"
            else:
                threshold_status = "insufficient"
        else:
            threshold_status = "not_required"
        source_count = self.connection.execute(
            """SELECT COUNT(DISTINCT source_id) AS n FROM phase36_rule_items
               WHERE industry_code=? AND validation_status='qualified'""",
            (industry_code,),
        ).fetchone()["n"]
        module_counts = {
            module: {
                "raw": raw.get(module, 0),
                "qualified": qualified.get(module, 0),
                "official_explicit": explicit.get(module, 0),
                "source_derived": derived.get(module, 0),
                "required": gates.get(module),
            }
            for module in set(MODULE_TABLES) | set(gates)
        }
        now = utc_now()
        record = {
            "density_assessment_id": stable_id("density", f"{POLICY_VERSION}:{industry_code}"),
            "industry_code": industry_code,
            "target_tier": target_tier,
            "build_status": status,
            "completion_percent": score,
            "module_counts_json": json.dumps(module_counts, ensure_ascii=False, sort_keys=True),
            "unmet_gates_json": json.dumps(unmet, ensure_ascii=False, sort_keys=True),
            "numeric_threshold_expected": int(effective_threshold_expected),
            "numeric_threshold_status": threshold_status,
            "official_source_count": source_count,
            "simulation_count": simulations,
            "assessed_at": now,
            "assessment_policy_version": POLICY_VERSION,
            "threshold_basis_note": threshold_basis_note,
            "updated_at": now,
        }
        exists = self.connection.execute(
            "SELECT 1 FROM industry_density_assessments WHERE industry_code=?", (industry_code,)
        ).fetchone()
        if exists:
            assignments = ",".join(f"{k}=?" for k in record if k not in {"density_assessment_id", "industry_code"})
            values = [record[k] for k in record if k not in {"density_assessment_id", "industry_code"}]
            self.connection.execute(
                f"UPDATE industry_density_assessments SET {assignments}, row_version=row_version+1 WHERE industry_code=?",
                (*values, industry_code),
            )
        else:
            record["created_at"] = now
            record["row_version"] = 1
            cols = list(record)
            self.connection.execute(
                f"INSERT INTO industry_density_assessments ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                tuple(record[c] for c in cols),
            )
        missing_labels = [f"{x['module']} {x['qualified']}/{x['required']}" for x in unmet]
        self.connection.execute(
            """UPDATE industry_rule_profiles
               SET build_status=?, completion_percent=?, module_counts_json=?,
                   missing_modules_json=?, updated_at=?, row_version=row_version+1
               WHERE industry_code=?""",
            (
                status,
                score,
                record["module_counts_json"],
                json.dumps(missing_labels, ensure_ascii=False),
                now,
                industry_code,
            ),
        )
        return {**record, "module_counts": module_counts, "unmet_gates": unmet}
