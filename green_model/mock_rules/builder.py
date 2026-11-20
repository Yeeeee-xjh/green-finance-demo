"""Transactional, replaceable mock rule packages.

The builder never writes ``industry_density_assessments``.  Every application
row is inserted into the same master tables used by real rules and carries an
``is_mock=1`` marker wherever that table supports the marker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from green_model.agent.domain.models import stable_id, utc_now
from green_model.agent.storage.database import Database

from .catalog import INDUSTRIES, pack_items


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "phase1" / "green_finance_phase1.sqlite3"
SCHEMA_VERSION = "mock-rule-pack-v1"
MOCK_LABEL = "示例规则"
SUPPORTED_INDUSTRIES = tuple(INDUSTRIES)

TASK_BY_MODULE = {
    "process": "现场核验", "equipment": "现场核验", "route": "规则核验",
    "standard": "规则核验", "indicator": "规则核验", "threshold": "规则核验",
    "permit": "补件", "document": "补件", "evidence": "补件", "risk": "冲突核实",
    "term": "规则核验", "postloan": "贷后预警",
}

PKS = {
    "source_manifest": "source_id", "industry_knowledge_items": "knowledge_id",
    "standard_catalog": "standard_id", "industry_standard_links": "link_id",
    "indicator_definitions": "indicator_definition_id", "threshold_definitions": "threshold_id",
    "permit_requirements": "permit_requirement_id", "document_requirements": "document_requirement_id",
    "evidence_requirements": "evidence_requirement_id", "industry_risk_points": "risk_point_id",
    "postloan_indicator_definitions": "postloan_indicator_id", "term_cards": "term_id",
    "phase36_rule_items": "phase36_item_id", "rule_application_mappings": "application_mapping_id",
}

DELETE_ORDER = {
    "rule_application_mappings": 10, "phase36_rule_items": 20,
    "industry_standard_links": 30, "indicator_definitions": 30,
    "threshold_definitions": 30, "permit_requirements": 30,
    "document_requirements": 30, "evidence_requirements": 30,
    "industry_risk_points": 30, "postloan_indicator_definitions": 30,
    "term_cards": 30, "industry_knowledge_items": 30,
    "standard_catalog": 40, "source_manifest": 50,
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class MockRulePackBuilder:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE):
        self.database = Database(database_path)
        self.database.initialize()
        self._columns_cache: dict[str, tuple[str, ...]] = {}

    def _columns(self, connection, table: str) -> tuple[str, ...]:
        if table not in self._columns_cache:
            self._columns_cache[table] = tuple(
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            )
        return self._columns_cache[table]

    def _upsert(self, connection, table: str, record: dict[str, Any]) -> None:
        columns = self._columns(connection, table)
        unknown = set(record) - set(columns)
        if unknown:
            raise ValueError(f"{table}包含未知字段：{sorted(unknown)}")
        now = utc_now()
        data = dict(record)
        if "created_at" in columns:
            data.setdefault("created_at", now)
        if "updated_at" in columns:
            data["updated_at"] = now
        if "row_version" in columns:
            data.setdefault("row_version", 1)
        pk = PKS[table]
        names = list(data)
        updates = [name for name in names if name not in {pk, "created_at", "row_version"}]
        sql = (
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)}) "
            f"ON CONFLICT({pk}) DO UPDATE SET "
            + ",".join(f"{name}=excluded.{name}" for name in updates)
        )
        connection.execute(sql, tuple(data[name] for name in names))

    @staticmethod
    def _track(connection, batch_id: str, table: str, record_id: str) -> None:
        now = utc_now()
        connection.execute(
            """INSERT INTO mock_rule_batch_items
               (mock_batch_id,record_table,record_id,delete_order,created_at,updated_at,row_version)
               VALUES (?,?,?,?,?,?,1)
               ON CONFLICT(mock_batch_id,record_table,record_id) DO UPDATE SET
                 delete_order=excluded.delete_order,updated_at=excluded.updated_at""",
            (batch_id, table, record_id, DELETE_ORDER[table], now, now),
        )

    @staticmethod
    def _ids(code: str, key: str) -> dict[str, str]:
        base = f"{SCHEMA_VERSION}:{code}:{key}"
        return {
            "record": stable_id("mock_record", base),
            "phase": stable_id("mock_phase36", base),
            "mapping": stable_id("mock_mapping", base),
        }

    def _source(self, connection, code: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        source_id = stable_id("mock_source", f"{SCHEMA_VERSION}:{code}")
        payload_sha = _sha({"industry_code": code, "items": items})
        record = {
            "source_id": source_id,
            "source_name": f"{MOCK_LABEL}｜{code} {INDUSTRIES[code]['name']}功能测试包",
            "issuer": "数绿融通演示数据（非权威来源）",
            "version_label": SCHEMA_VERSION,
            "source_url": f"mock://rule-pack/{code}/{SCHEMA_VERSION}",
            "sha256": payload_sha,
            "accessed_at": utc_now(),
            "authority_level": "simulation_only",
            "is_mandatory": None,
            "formal_rule_eligible": 0,
            "availability_status": "public_channel_not_obtained",
            "limitation_note": "示例规则，仅用于功能测试；不计入规则密度，不得作为真实审批依据。",
            "is_mock": 1,
        }
        self._upsert(connection, "source_manifest", record)
        return {**record, "source_sha256": payload_sha}

    def _master_record(
        self, code: str, item: dict[str, Any], source: dict[str, Any], record_id: str,
    ) -> tuple[str, dict[str, Any], tuple[str, dict[str, Any]] | None]:
        module, name, text = str(item["module"]), str(item["name"]), str(item["text"])
        common = {"industry_code": code, "source_id": source["source_id"], "is_mock": 1}
        if module in {"process", "equipment", "route"}:
            return "industry_knowledge_items", {**common, "knowledge_id": record_id, "module": module, "title": name, "content": text, "source_locator": "示例规则/功能测试", "derivation_type": "source_derived", "scope_status": "core"}, None
        if module == "standard":
            standard_id = stable_id("mock_standard", f"{SCHEMA_VERSION}:{code}:{item['key']}")
            standard = {"standard_id": standard_id, "standard_no": f"MOCK-{code}-001", "standard_name": name, "standard_type": "示例审查口径（非标准）", "issuer": source["issuer"], "full_text_status": "public_channel_not_obtained", "public_scope_note": text, "source_id": source["source_id"]}
            link = {**common, "link_id": record_id, "standard_id": standard_id, "applicability": "仅系统演示，待真实来源替换", "source_page": "示例规则", "scope_status": "core"}
            return "industry_standard_links", link, ("standard_catalog", standard)
        if module == "indicator":
            return "indicator_definitions", {**common, "indicator_definition_id": record_id, "indicator_name": name, "definition_text": text, "formula_text": "实际值/目标值×100%", "statistical_scope": "仅演示", "unit": "%", "applicable_stage": "贷后", "derivation_type": "source_derived", "formal_rule_eligible": 0, "source_page": "示例规则", "scope_status": "core"}, None
        if module == "threshold":
            indicator_id = stable_id("mock_record", f"{SCHEMA_VERSION}:{code}:indicator")
            return "threshold_definitions", {**common, "threshold_id": record_id, "indicator_definition_id": indicator_id, "threshold_text": text, "operator": "<", "threshold_value": "85", "unit": "%", "applicable_region": "仅演示", "effective_at": "2099-01-01", "source_page": "示例规则", "scope_status": "core", "threshold_kind": "explicit_numeric", "applicable_scope": "仅系统功能测试，非真实阈值", "source_sha256": source["source_sha256"], "derivation_type": "source_derived"}, None
        if module == "permit":
            return "permit_requirements", {**common, "permit_requirement_id": record_id, "permit_name": name, "requirement_text": text, "applicable_stage": "贷前/贷中", "applicable_region": "仅演示", "status_note": "待人工核实", "source_page": "示例规则", "scope_status": "core", "derivation_type": "source_derived"}, None
        if module == "document":
            return "document_requirements", {**common, "document_requirement_id": record_id, "document_name": name, "requirement_text": text, "mandatory_basis": "示例规则，非法定要求", "applicable_stage": "贷前/贷中", "acceptable_alternatives": "由客户经理人工确认", "source_page": "示例规则", "scope_status": "core", "derivation_type": "source_derived"}, None
        if module == "evidence":
            return "evidence_requirements", {**common, "evidence_requirement_id": record_id, "evidence_object": name, "requirement_text": text, "acceptable_evidence": "可定位原文且口径可人工复核的材料", "unacceptable_substitution": "不接受无来源摘录或系统自行生成的结论", "applicable_stage": "贷前/贷中/贷后", "source_page": "示例规则", "scope_status": "core", "derivation_type": "source_derived"}, None
        if module == "risk":
            return "industry_risk_points", {**common, "risk_point_id": record_id, "risk_category": "资金与实施风险", "risk_title": name, "risk_description": text, "review_focus": "核对项目边界、支付对象、设备和验收证据", "derivation_type": "source_derived", "formal_rule_eligible": 0, "source_page": "示例规则", "scope_status": "core"}, None
        if module == "term":
            return "term_cards", {**common, "term_id": record_id, "term": name, "definition_text": text, "usage_note": "辅助阅读演示，须用真实规则包替换", "source_page": "示例规则", "scope_status": "core", "derivation_type": "source_derived"}, None
        if module == "postloan":
            return "postloan_indicator_definitions", {**common, "postloan_indicator_id": record_id, "indicator_name": name, "definition_text": text, "formula_text": "(实际值-目标值)/目标值×100%", "unit": item.get("unit") or "%", "frequency": "月度（演示）", "evidence_object": "经人工确认的运行台账", "source_page": "示例规则", "scope_status": "core", "derivation_type": "source_derived", "indicator_category": item.get("indicator_category"), "comparison_direction": item.get("comparison_direction"), "warning_deviation_ratio": "0.10", "critical_deviation_ratio": "0.20", "statistical_scope": item.get("statistical_scope"), "measurement_method": "经人工确认的同口径台账汇总", "measurement_boundary": "本贷款项目边界", "basis_version": "mock-basis-v1"}, None
        raise ValueError(f"不支持的模块：{module}")

    @staticmethod
    def _evidence_ids(code: str) -> dict[str, str]:
        return {
            alias: stable_id("mock_record", f"{SCHEMA_VERSION}:{code}:evidence_{alias}")
            for alias in ("project", "permit", "asset", "performance")
        }

    def _build_in_transaction(self, connection, code: str) -> dict[str, Any]:
        items = pack_items(code)
        # Evidence objects must exist before normalized mapping links are
        # written.  This is only a dependency order; the catalog declaration
        # remains presentation-oriented.
        write_items = [item for item in items if item["module"] == "evidence"] + [
            item for item in items if item["module"] != "evidence"
        ]
        batch_id = stable_id("mock_batch", f"{SCHEMA_VERSION}:{code}")
        replacement_key = f"industry:{code}:mock-active"
        now = utc_now()
        connection.execute(
            """INSERT INTO mock_rule_batches
               (mock_batch_id,industry_code,batch_label,schema_version,replacement_key,status,created_at,updated_at,row_version)
               VALUES (?,?,?,?,?,'active',?,?,1)
               ON CONFLICT(mock_batch_id) DO UPDATE SET batch_label=excluded.batch_label,
                 schema_version=excluded.schema_version,status='active',updated_at=excluded.updated_at,
                 row_version=mock_rule_batches.row_version+1""",
            (batch_id, code, f"{MOCK_LABEL}｜{code} {INDUSTRIES[code]['name']}", SCHEMA_VERSION, replacement_key, now, now),
        )
        source = self._source(connection, code, items)
        self._track(connection, batch_id, "source_manifest", source["source_id"])
        evidence_ids = self._evidence_ids(code)
        counts: dict[str, int] = {}
        for item in write_items:
            ids = self._ids(code, str(item["key"]))
            table, record, extra = self._master_record(code, item, source, ids["record"])
            if extra:
                self._upsert(connection, extra[0], extra[1])
                self._track(connection, batch_id, extra[0], str(extra[1][PKS[extra[0]]]))
            self._upsert(connection, table, record)
            self._track(connection, batch_id, table, ids["record"])
            fingerprint = _sha({"code": code, "module": item["module"], "name": item["name"], "text": item["text"], "mock": 1})
            phase = {
                "phase36_item_id": ids["phase"], "industry_code": code, "module": item["module"],
                "record_table": table, "record_id": ids["record"], "source_id": source["source_id"],
                "source_locator": "示例规则/功能测试", "lineage_kind": "simulation",
                "formal_density_eligible": 0, "content_fingerprint": fingerprint,
                "source_sha256": source["source_sha256"], "validation_status": "pending",
                "validation_reasons_json": _json(["模拟数据：不参与真实规则资格判定"]),
                "eligibility_policy_version": SCHEMA_VERSION, "is_mock": 1,
            }
            self._upsert(connection, "phase36_rule_items", phase)
            self._track(connection, batch_id, "phase36_rule_items", ids["phase"])
            required = [evidence_ids[key] for key in item["evidence"]]
            mapping = {
                "application_mapping_id": ids["mapping"], "phase36_item_id": ids["phase"],
                "industry_code": code,
                "verification_item_template": f"{item['name']}：{item['text']} 【仅待核实】",
                "evidence_requirement_ids_json": _json(required),
                "task_type": item.get("task") or TASK_BY_MODULE[str(item["module"])], "is_mock": 1,
            }
            self._upsert(connection, "rule_application_mappings", mapping)
            self._track(connection, batch_id, "rule_application_mappings", ids["mapping"])
            for evidence_id in required:
                connection.execute(
                    """INSERT INTO rule_application_evidence_links
                       (application_mapping_id,evidence_requirement_id,created_at,updated_at,row_version)
                       VALUES (?,?,?,?,1) ON CONFLICT(application_mapping_id,evidence_requirement_id)
                       DO UPDATE SET updated_at=excluded.updated_at""",
                    (ids["mapping"], evidence_id, now, now),
                )
            counts[str(item["module"])] = counts.get(str(item["module"]), 0) + 1
        return {"industry_code": code, "mock_batch_id": batch_id, "item_count": len(items), "module_counts": counts}

    @staticmethod
    def _assert_removable(connection, table: str, record_id: str) -> None:
        pk = PKS[table]
        row = connection.execute(f"SELECT * FROM {table} WHERE {pk}=?", (record_id,)).fetchone()
        if row is None:
            return
        if "is_mock" in row.keys() and row["is_mock"] != 1:
            raise ValueError(f"批次登记异常：拒绝删除正式记录 {table}/{record_id}")
        if table == "standard_catalog":
            source = connection.execute("SELECT is_mock FROM source_manifest WHERE source_id=?", (row["source_id"],)).fetchone()
            if source is None or source["is_mock"] != 1:
                raise ValueError(f"批次登记异常：拒绝删除正式标准 {record_id}")

    def _remove_in_transaction(self, connection, code: str) -> dict[str, Any]:
        batch = connection.execute(
            "SELECT * FROM mock_rule_batches WHERE replacement_key=?",
            (f"industry:{code}:mock-active",),
        ).fetchone()
        if batch is None:
            return {"industry_code": code, "removed": 0, "status": "not_found"}
        rows = connection.execute(
            """SELECT * FROM mock_rule_batch_items WHERE mock_batch_id=?
               ORDER BY delete_order,record_table,record_id""", (batch["mock_batch_id"],),
        ).fetchall()
        evidence_ids = [r["record_id"] for r in rows if r["record_table"] == "evidence_requirements"]
        if evidence_ids:
            marks = ",".join("?" for _ in evidence_ids)
            connection.execute(
                f"""DELETE FROM verification_requirement_links
                    WHERE evidence_requirement_id IN ({marks})
                      AND verification_id IN (SELECT verification_id FROM verification_items WHERE is_mock=1)""",
                evidence_ids,
            )
        removed = 0
        for row in rows:
            table, record_id = row["record_table"], row["record_id"]
            self._assert_removable(connection, table, record_id)
            cursor = connection.execute(f"DELETE FROM {table} WHERE {PKS[table]}=?", (record_id,))
            removed += max(cursor.rowcount, 0)
        connection.execute("DELETE FROM mock_rule_batch_items WHERE mock_batch_id=?", (batch["mock_batch_id"],))
        connection.execute(
            """UPDATE mock_rule_batches SET status='removed',updated_at=?,row_version=row_version+1
               WHERE mock_batch_id=?""", (utc_now(), batch["mock_batch_id"]),
        )
        return {"industry_code": code, "removed": removed, "status": "removed"}

    @staticmethod
    def _validate_codes(codes: Iterable[str] | None) -> tuple[str, ...]:
        result = tuple(codes or SUPPORTED_INDUSTRIES)
        unsupported = sorted(set(result) - set(SUPPORTED_INDUSTRIES))
        if unsupported:
            raise ValueError(f"不支持的模拟行业：{unsupported}")
        return result

    def build(self, industries: Iterable[str] | None = None, *, replace: bool = False) -> dict[str, Any]:
        codes = self._validate_codes(industries)
        with self.database.transaction() as connection:
            results = []
            for code in codes:
                if replace:
                    self._remove_in_transaction(connection, code)
                results.append(self._build_in_transaction(connection, code))
        return {"schema_version": SCHEMA_VERSION, "action": "replace" if replace else "build", "industries": results}

    def remove(self, industries: Iterable[str] | None = None) -> dict[str, Any]:
        codes = self._validate_codes(industries)
        with self.database.transaction() as connection:
            results = [self._remove_in_transaction(connection, code) for code in codes]
        return {"schema_version": SCHEMA_VERSION, "action": "remove", "industries": results}
