"""Build auditable Phase 3.6 industry rule packages.

The builder is deliberately fail-closed:

* official originals are registered with their local SHA-256;
* curated content is written to the Phase 3.5 master tables first;
* every density item is linked to a verification template and evidence object;
* simulations are never copied into the formal registry;
* density is calculated only by :class:`DensityAssessor` after validation.

Running the builder repeatedly is safe.  Stable identifiers and strict
upserts prevent duplicate sources, rules, mappings and evidence links.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from green_model.agent.domain.models import stable_id, utc_now
from green_model.agent.storage.database import Database
from green_model.agent.storage.repository import PRIMARY_KEYS, SQLiteRepository
from green_model.phase2_ui.app import DEFAULT_DATABASE
from green_model.phase35.industry_master import _source_record

from .catalog import ROOT, SHOWCASE_ITEMS, SOURCE_ALIASES, SOURCE_SPECS
from .density import MODULE_TABLES, DensityAssessor, content_fingerprint


REPORT_ROOT = ROOT / "data" / "industry_master"
FIRST_TIER = ("3011", "3110", "4415")
SECOND_TIER = ("4416", "4417", "5411")
FORCED_BASE = ("5413",)

TASK_BY_MODULE = {
    "process": "现场核验",
    "equipment": "现场核验",
    "route": "规则核验",
    "standard": "规则核验",
    "indicator": "规则核验",
    "threshold": "规则核验",
    "permit": "规则核验",
    "document": "补件",
    "evidence": "补件",
    "risk": "冲突核实",
    "term": "规则核验",
    "postloan": "贷后预警",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _columns(connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _strict_upsert(uow, table: str, record: dict[str, Any]) -> str:
    """Upsert one master row and reject misspelled/unknown fields."""
    columns = _columns(uow.connection, table)
    unknown = set(record) - columns
    if unknown:
        raise ValueError(f"{table}包含未知字段：{sorted(unknown)}")
    key_name = PRIMARY_KEYS[table]
    object_id = str(record[key_name])
    current = uow.get(table, object_id)
    if current is None:
        uow.insert(table, record)
        return object_id
    changes = {
        key: value
        for key, value in record.items()
        if key not in {key_name, "created_at", "updated_at", "row_version"}
        and current.get(key) != value
    }
    if changes:
        uow.update(table, object_id, changes)
    return object_id


def _row_name(module: str, row: dict[str, Any]) -> str:
    return str(
        row.get("title")
        or row.get("standard_name")
        or row.get("indicator_name")
        or row.get("threshold_text")
        or row.get("permit_name")
        or row.get("document_name")
        or row.get("evidence_object")
        or row.get("risk_title")
        or row.get("term")
        or row.get("record_id")
    )


class Phase36RulePackBuilder:
    """Create source-backed showcase packages and assess their true density."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE):
        self.database = Database(database_path)
        self.database.initialize()
        self.repository = SQLiteRepository(self.database)

    def _register_sources(self, uow) -> dict[str, dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for key, spec in SOURCE_SPECS.items():
            path = (ROOT / spec["path"]).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Phase 3.6缺少官方原件：{path}")
            candidate = _source_record(
                key=f"phase36:{key}",
                path=path,
                name=spec["name"],
                issuer=spec["issuer"],
                url=spec["url"],
                version=spec["version"],
                authority=(
                    "national_standard_official_metadata"
                    if spec.get("status") == "official_summary_only"
                    else "national_policy_official_full_text"
                ),
                standard_no=spec.get("standard_no"),
                document_no=spec.get("document_no"),
                published_at=spec.get("published_at"),
                effective_at=spec.get("effective_at"),
                status=spec.get("status", "full_text_obtained"),
                formal=True,
                limitation=spec.get("limitation"),
                is_mandatory=spec.get("mandatory"),
            )
            existing = uow.connection.execute(
                """SELECT * FROM source_manifest
                   WHERE sha256=? AND version_label=?
                   ORDER BY formal_rule_eligible DESC, source_id LIMIT 1""",
                (candidate["sha256"], candidate["version_label"]),
            ).fetchone()
            if existing:
                source_id = existing["source_id"]
                _strict_upsert(
                    uow,
                    "source_manifest",
                    {**candidate, "source_id": source_id},
                )
            else:
                source_id = candidate["source_id"]
                _strict_upsert(uow, "source_manifest", candidate)
            sources[key] = uow.require("source_manifest", source_id)

        for key, exact_name in SOURCE_ALIASES.items():
            rows = uow.connection.execute(
                """SELECT * FROM source_manifest
                   WHERE source_name=? AND formal_rule_eligible=1
                   ORDER BY CASE availability_status
                       WHEN 'full_text_obtained' THEN 0
                       WHEN 'official_summary_only' THEN 1 ELSE 2 END,
                       row_version DESC, source_id""",
                (exact_name,),
            ).fetchall()
            if not rows:
                raise ValueError(f"未找到Phase 3.6来源别名：{key} -> {exact_name}")
            sources[key] = dict(rows[0])
        return sources

    @staticmethod
    def _common(industry_code: str, source: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        return {
            "industry_code": industry_code,
            "source_id": source["source_id"],
            "source_page": item["locator"],
            "scope_status": "core",
        }

    def _write_catalog_item(
        self,
        uow,
        industry_code: str,
        item: dict[str, Any],
        source: dict[str, Any],
    ) -> tuple[str, str]:
        module = item["module"]
        name = item["name"]
        text = item["text"]
        identity = f"phase36:{industry_code}:{module}:{item['source_key']}:{name}"
        common = self._common(industry_code, source, item)
        derivation = item.get("derivation_type", "source_derived")

        if module in {"process", "equipment", "route"}:
            table = "industry_knowledge_items"
            record = {
                "knowledge_id": stable_id("knowledge", identity),
                "industry_code": industry_code,
                "module": module,
                "title": name,
                "content": text,
                "source_id": source["source_id"],
                "source_locator": item["locator"],
                "derivation_type": derivation,
                "scope_status": "core",
            }
        elif module == "standard":
            standard_id = stable_id("standard", identity)
            standard = {
                "standard_id": standard_id,
                "standard_no": item.get("standard_no"),
                "standard_name": name,
                "standard_type": "行业规范/政策技术依据",
                "issuer": source["issuer"],
                "effective_at": source.get("effective_at"),
                "expires_at": source.get("expires_at"),
                "full_text_status": item.get("full_text_status") or source["availability_status"],
                "public_scope_note": source.get("limitation_note") or text,
                "source_id": source["source_id"],
            }
            _strict_upsert(uow, "standard_catalog", standard)
            table = "industry_standard_links"
            record = {
                "link_id": stable_id("stdlink", identity),
                "industry_code": industry_code,
                "standard_id": standard_id,
                "applicability": item.get("applicability") or text,
                "source_page": item["locator"],
                "source_id": source["source_id"],
                "scope_status": "core",
            }
        elif module == "indicator":
            table = "indicator_definitions"
            record = {
                "indicator_definition_id": stable_id("indicator", identity),
                **common,
                "indicator_name": name,
                "definition_text": text,
                "formula_text": item.get("formula"),
                "statistical_scope": item.get("scope"),
                "unit": item.get("unit"),
                "applicable_stage": item.get("stage"),
                "derivation_type": derivation,
                "formal_rule_eligible": 1,
            }
        elif module == "threshold":
            table = "threshold_definitions"
            record = {
                "threshold_id": stable_id("threshold", identity),
                **common,
                "indicator_definition_id": None,
                "threshold_text": text,
                "operator": str(item.get("operator") or ""),
                "threshold_value": str(item.get("value") if item.get("value") is not None else ""),
                "unit": item.get("unit"),
                "applicable_region": item.get("region") or "全国；按来源限定范围适用",
                "applicable_scope": item.get("scope"),
                "effective_at": item.get("effective_at") or source.get("effective_at"),
                "expires_at": item.get("expires_at") or source.get("expires_at"),
                "source_sha256": source["sha256"],
                "threshold_kind": "explicit_numeric",
                "derivation_type": "policy_explicit",
            }
        elif module == "permit":
            table = "permit_requirements"
            record = {
                "permit_requirement_id": stable_id("permit", identity),
                **common,
                "permit_name": name,
                "requirement_text": text,
                "applicable_stage": item.get("stage"),
                "applicable_region": item.get("region") or "全国；同时核对属地规定",
                "status_note": item.get("notes"),
                "derivation_type": "policy_explicit",
            }
        elif module == "document":
            table = "document_requirements"
            record = {
                "document_requirement_id": stable_id("document", identity),
                **common,
                "document_name": name,
                "requirement_text": text,
                "mandatory_basis": item["locator"],
                "applicable_stage": item.get("stage"),
                "acceptable_alternatives": item.get("alternatives"),
                "derivation_type": derivation,
            }
        elif module == "evidence":
            table = "evidence_requirements"
            record = {
                "evidence_requirement_id": stable_id("evidence_req", identity),
                **common,
                "evidence_object": name,
                "requirement_text": text,
                "acceptable_evidence": item.get("acceptable") or text,
                "unacceptable_substitution": item.get("unacceptable"),
                "applicable_stage": item.get("stage"),
                "derivation_type": derivation,
            }
        elif module == "risk":
            table = "industry_risk_points"
            record = {
                "risk_point_id": stable_id("riskpoint", identity),
                **common,
                "risk_category": item.get("category") or "行业核验关注点",
                "risk_title": name,
                "risk_description": text,
                "review_focus": item.get("review_focus") or text,
                "derivation_type": derivation,
                "formal_rule_eligible": 1,
            }
        elif module == "term":
            table = "term_cards"
            record = {
                "term_id": stable_id("term", identity),
                **common,
                "term": name,
                "definition_text": text,
                "usage_note": item.get("usage") or "辅助阅读；具体适用边界以来源原文为准。",
                "derivation_type": derivation,
            }
        elif module == "postloan":
            table = "postloan_indicator_definitions"
            record = {
                "postloan_indicator_id": stable_id("postloan", identity),
                **common,
                "indicator_name": name,
                "definition_text": text,
                "formula_text": item.get("formula"),
                "unit": item.get("unit"),
                "frequency": item.get("frequency"),
                "evidence_object": item.get("evidence_object") or text,
                "derivation_type": derivation,
            }
        else:  # pragma: no cover - catalog validation catches this first
            raise ValueError(f"未知Phase 3.6模块：{module}")

        record_id = _strict_upsert(uow, table, record)
        return table, record_id

    @staticmethod
    def _prepare_existing_rows(connection, source_by_id: dict[str, dict[str, Any]]) -> None:
        """Fill guard fields only where prior reviewed rows support them."""
        target_codes = (*FIRST_TIER, *SECOND_TIER)
        placeholders = ",".join("?" for _ in target_codes)
        # Earlier migrations did not yet carry derivation type on these two
        # policy-explicit tables.  Only reviewed core rows with formal sources
        # are promoted; adjacent/unreviewed rows remain source-derived.
        connection.execute(
            f"""UPDATE permit_requirements SET derivation_type='policy_explicit'
                WHERE industry_code IN ({placeholders}) AND scope_status='core'
                  AND source_id IN (
                    SELECT source_id FROM source_manifest WHERE formal_rule_eligible=1
                  )""",
            target_codes,
        )
        threshold_rows = connection.execute(
            f"""SELECT * FROM threshold_definitions
                WHERE industry_code IN ({placeholders}) AND scope_status='core'
                  AND threshold_kind='explicit_numeric'""",
            target_codes,
        ).fetchall()
        for row in threshold_rows:
            source = source_by_id.get(row["source_id"])
            if not source or source.get("formal_rule_eligible") != 1:
                continue
            connection.execute(
                """UPDATE threshold_definitions
                   SET derivation_type='policy_explicit',
                       applicable_scope=COALESCE(NULLIF(applicable_scope,''),
                           NULLIF(applicable_region,''), threshold_text),
                       source_sha256=?
                   WHERE threshold_id=?""",
                (source["sha256"], row["threshold_id"]),
            )
        # Source-derived risk/indicator rows may be counted only after this
        # explicit reviewed-core promotion; simulations are stored elsewhere.
        for table in ("indicator_definitions", "industry_risk_points"):
            connection.execute(
                f"""UPDATE {table} SET formal_rule_eligible=1
                    WHERE industry_code IN ({placeholders}) AND scope_status='core'
                      AND source_id IN (
                        SELECT source_id FROM source_manifest WHERE formal_rule_eligible=1
                      )""",
                target_codes,
            )

    @staticmethod
    def _eligible_master_rows(connection, industry_code: str) -> list[tuple[str, str, dict[str, Any]]]:
        records: list[tuple[str, str, dict[str, Any]]] = []
        for module, (table, key) in MODULE_TABLES.items():
            where = "industry_code=? AND scope_status='core'"
            params: list[Any] = [industry_code]
            if module in {"process", "equipment", "route"}:
                where += " AND module=?"
                params.append(module)
            if module == "threshold":
                where += " AND threshold_kind='explicit_numeric'"
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE {where} ORDER BY {key}", params
            ).fetchall()
            records.extend((module, table, dict(row)) for row in rows)
        return records

    @staticmethod
    def _locator(module: str, record: dict[str, Any]) -> str:
        return str(
            record.get("source_locator")
            if module in {"process", "equipment", "route"}
            else record.get("source_page")
            or ""
        )

    @staticmethod
    def _lineage(module: str, record: dict[str, Any]) -> str:
        if module == "standard":
            return "official_public_source"
        return (
            "official_public_source"
            if record.get("derivation_type") == "policy_explicit"
            else "source_derived"
        )

    def _register_density_items(
        self,
        uow,
        industry_code: str,
        source_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registered: list[dict[str, Any]] = []
        for module, table, record in self._eligible_master_rows(uow.connection, industry_code):
            key_name = MODULE_TABLES[module][1]
            record_id = record[key_name]
            source = source_by_id.get(record["source_id"])
            if not source:
                continue
            item_id = stable_id("p36item", f"{table}:{record_id}")
            payload = {
                "phase36_item_id": item_id,
                "industry_code": industry_code,
                "module": module,
                "record_table": table,
                "record_id": record_id,
                "source_id": record["source_id"],
                "source_locator": self._locator(module, record),
                "lineage_kind": self._lineage(module, record),
                "formal_density_eligible": 0,
                "content_fingerprint": content_fingerprint(module, record),
                "source_sha256": source["sha256"],
                "validation_status": "pending",
                "validation_reasons_json": "[]",
                "eligibility_policy_version": "phase36-v1",
            }
            current = uow.get("phase36_rule_items", item_id)
            if current is None:
                uow.insert("phase36_rule_items", payload)
            else:
                # Reset only changed registrations to pending.  Unchanged rows
                # retain qualified status until the assessor rechecks them.
                registration_fields = {
                    k: v for k, v in payload.items()
                    if k not in {"phase36_item_id", "formal_density_eligible",
                                 "validation_status", "validation_reasons_json"}
                }
                changed = any(current.get(k) != v for k, v in registration_fields.items())
                if changed:
                    uow.update(
                        "phase36_rule_items",
                        item_id,
                        {
                            **registration_fields,
                            "formal_density_eligible": 0,
                            "validation_status": "pending",
                            "validation_reasons_json": "[]",
                        },
                    )
            registered.append({**record, **payload, "record": record})
        return registered

    @staticmethod
    def _upsert_mapping(
        uow,
        item: dict[str, Any],
        evidence_ids: list[str],
    ) -> None:
        mapping_id = stable_id("p36map", item["phase36_item_id"])
        record = item["record"]
        name = _row_name(item["module"], record)
        mapping = {
            "application_mapping_id": mapping_id,
            "phase36_item_id": item["phase36_item_id"],
            "industry_code": item["industry_code"],
            "verification_item_template": (
                f"核验“{name}”：按{item['source_locator']}对照项目事实，"
                "保留原文页码；证据不足时生成补件或人工复核任务。"
            ),
            "evidence_requirement_ids_json": json.dumps(
                evidence_ids, ensure_ascii=False, sort_keys=True
            ),
            "task_type": TASK_BY_MODULE[item["module"]],
        }
        _strict_upsert(uow, "rule_application_mappings", mapping)
        uow.connection.execute(
            "DELETE FROM rule_application_evidence_links WHERE application_mapping_id=?",
            (mapping_id,),
        )
        now = utc_now()
        for evidence_id in evidence_ids:
            uow.connection.execute(
                """INSERT INTO rule_application_evidence_links
                   (application_mapping_id,evidence_requirement_id,created_at,updated_at,row_version)
                   VALUES (?,?,?,?,1)""",
                (mapping_id, evidence_id, now, now),
            )

    def _map_items(self, uow, industry_code: str, items: list[dict[str, Any]]) -> None:
        evidences = [item for item in items if item["module"] == "evidence"]
        if not evidences and items:
            raise ValueError(f"{industry_code}存在正式规则项但没有证据要求")
        # Historical master data may include intentionally gray/incomplete
        # evidence rows.  They remain registered (and will be rejected by the
        # assessor), but must not make an otherwise valid rule fail merely
        # because an automatic same-source match selected them.
        usable_evidences = [
            item for item in evidences
            if item["record"].get("requirement_text")
            and item["record"].get("acceptable_evidence")
            and (
                any(char.isdigit() for char in item["source_locator"])
                or (
                    "第" in item["source_locator"]
                    and any(token in item["source_locator"] for token in ("条", "章", "部分"))
                )
            )
        ]
        by_source: dict[str, list[str]] = defaultdict(list)
        all_ids: list[str] = []
        for evidence in usable_evidences:
            evidence_id = evidence["record_id"]
            all_ids.append(evidence_id)
            by_source[evidence["source_id"]].append(evidence_id)
        for index, item in enumerate(items):
            if item["module"] == "evidence":
                selected = [item["record_id"]]
            else:
                candidates = by_source.get(item["source_id"], [])
                selected = candidates[:2]
                if not selected and all_ids:
                    selected = [all_ids[index % len(all_ids)]]
            self._upsert_mapping(uow, item, selected)

    @staticmethod
    def _source_manifest_export(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = (
            "source_id", "source_name", "issuer", "document_no", "standard_no",
            "version_label", "published_at", "effective_at", "expires_at",
            "source_url", "local_path", "sha256", "accessed_at",
            "authority_level", "availability_status", "formal_rule_eligible",
            "limitation_note",
        )
        return [{field: source.get(field) for field in fields} for source in sources]

    def build(self, *, export_reports: bool = True) -> dict[str, Any]:
        assessments: dict[str, dict[str, Any]] = {}
        with self.repository.transaction() as uow:
            sources = self._register_sources(uow)
            for industry_code, items in SHOWCASE_ITEMS.items():
                for spec in items:
                    if spec["source_key"] not in sources:
                        raise ValueError(
                            f"{industry_code}/{spec['module']}引用未注册来源：{spec['source_key']}"
                        )
                    self._write_catalog_item(
                        uow, industry_code, spec, sources[spec["source_key"]]
                    )

            source_by_id = {
                row["source_id"]: dict(row)
                for row in uow.connection.execute("SELECT * FROM source_manifest")
            }
            self._prepare_existing_rows(uow.connection, source_by_id)
            registered: dict[str, list[dict[str, Any]]] = {}
            for code in (*FIRST_TIER, *SECOND_TIER):
                registered[code] = self._register_density_items(uow, code, source_by_id)
                self._map_items(uow, code, registered[code])

            assessor = DensityAssessor(uow.connection)
            for code in FIRST_TIER:
                assessments[code] = assessor.assess(
                    code,
                    target_tier="first_tier",
                    numeric_threshold_expected=True,
                    threshold_basis_note=(
                        "公开官方来源存在可结构化数值阈值；按数值、单位、比较符、"
                        "适用范围、生效时间、页码与SHA-256完整性执行5条门槛。"
                    ),
                )
            for code in SECOND_TIER:
                assessments[code] = assessor.assess(
                    code,
                    target_tier="second_tier",
                    numeric_threshold_expected=False,
                    threshold_basis_note=(
                        "本轮不以未核验的数值门槛补齐第二梯队；已取得规则按真实模块计数，"
                        "其余显示待建设。"
                    ),
                )
            for code in FORCED_BASE:
                assessments[code] = assessor.assess(
                    code,
                    target_tier="base",
                    numeric_threshold_expected=False,
                    threshold_basis_note="仅基础行业信息；深度规则包待建设。",
                )
            source_export = self._source_manifest_export(
                sorted(source_by_id.values(), key=lambda row: row["source_id"])
            )

        result = {
            "policy_version": "phase36-v1",
            "database": str(self.database.path),
            "built_at": utc_now(),
            "assessments": assessments,
            "sources": source_export,
        }
        if export_reports:
            REPORT_ROOT.mkdir(parents=True, exist_ok=True)
            (REPORT_ROOT / "phase36_source_manifest.json").write_text(
                _json(source_export), encoding="utf-8"
            )
            (REPORT_ROOT / "phase36_density_report.json").write_text(
                _json({k: v for k, v in result.items() if k != "sources"}),
                encoding="utf-8",
            )
        return result


__all__ = ["Phase36RulePackBuilder"]
