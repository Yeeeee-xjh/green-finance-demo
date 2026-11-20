"""Reviewed, source-backed content added without deleting legacy master rows.

Raw mapping-derived records remain inspectable but cannot earn coverage credit.
The JSON research manifests are curated inputs, never substitutes for originals.
"""
from __future__ import annotations

import json
from pathlib import Path

from green_model.agent.domain.models import stable_id
from green_model.agent.storage.repository import PRIMARY_KEYS

ROOT = Path(__file__).resolve().parents[1]


def _upsert(uow, table, record):
    key = PRIMARY_KEYS[table]
    if uow.get(table, record[key]):
        uow.update(table, record[key], {k: v for k, v in record.items() if k != key})
    else:
        uow.insert(table, record)


def _load_research(uow, filename, code):
    from .industry_master import _source_record
    path = Path(__file__).with_name(filename)
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = {}
    for item in payload["sources"]:
        original = Path(item["local_path"])
        if not original.is_absolute():
            original = ROOT / original
        if not original.is_file():
            raise FileNotFoundError(f"官方来源原件缺失：{original}")
        source = _source_record(
            key=f"rework:{item['key']}", path=original, name=item["title"],
            issuer=item["issuer"], url=item["url"],
            version=item.get("version") or item.get("document_no") or item["title"],
            authority="official_public_source", standard_no=item.get("standard_no"),
            document_no=item.get("document_no"), published_at=item.get("published_at"),
            effective_at=item.get("effective_at"),
            status=item.get("availability", "official_summary_only"),
            formal=item.get("formal_rule_eligible", True),
            limitation=item.get("notes"), is_mandatory=item.get("is_mandatory"),
        )
        source["expires_at"] = item.get("expires_at")
        _upsert(uow, "source_manifest", source)
        sources[item["key"]] = source
    for item in payload["records"]:
        module, name, text = item["module"], item["name"], item["text"]
        source = sources[item["source_key"]]
        locator = item["locator"]
        derivation = item.get("derivation_type", "source_derived")
        common = {"industry_code": code, "source_id": source["source_id"],
                  "source_page": locator, "scope_status": item.get("scope_status", "core")}
        identity = f"phase35-rework:{code}:{module}:{item['source_key']}:{name}"
        stage = item.get("applicable_stage") or item.get("stage")
        if module in ("process", "equipment", "route"):
            _upsert(uow, "industry_knowledge_items", {
                "knowledge_id": stable_id("knowledge", identity),
                "industry_code": code, "module": module, "title": name, "content": text,
                "source_id": source["source_id"], "source_locator": locator,
                "derivation_type": derivation, "scope_status": common["scope_status"],
            })
            continue
        if module == "standard":
            standard_id = stable_id("standard", identity)
            _upsert(uow, "standard_catalog", {
                "standard_id": standard_id, "standard_no": item.get("standard_no"),
                "standard_name": name, "standard_type": "官方公开行业标准/技术规范",
                "issuer": source["issuer"], "effective_at": source.get("effective_at"),
                "expires_at": source.get("expires_at"),
                "full_text_status": item.get("full_text_status", source["availability_status"]),
                "public_scope_note": text, "source_id": source["source_id"],
            })
            _upsert(uow, "industry_standard_links", {
                "link_id": stable_id("stdlink", identity), "standard_id": standard_id,
                "applicability": item.get("applicability") or text, **common,
            })
            continue
        tables = {
            "indicator": "indicator_definitions", "threshold": "threshold_definitions",
            "permit": "permit_requirements", "document": "document_requirements",
            "evidence": "evidence_requirements", "risk": "industry_risk_points",
            "term": "term_cards", "postloan": "postloan_indicator_definitions",
        }
        table = tables[module]
        fields = {}
        if module == "indicator":
            fields = {"indicator_name": name, "definition_text": text,
                      "formula_text": item.get("formula"), "unit": item.get("unit"),
                      "statistical_scope": item.get("scope") or text, "applicable_stage": stage,
                      "derivation_type": derivation,
                      "formal_rule_eligible": int(derivation == "policy_explicit" and source["formal_rule_eligible"])}
        elif module == "threshold":
            value = item.get("value")
            fields = {"threshold_text": text, "threshold_value": str(value) if value is not None else None,
                      "operator": item.get("operator"), "unit": item.get("unit"),
                      "threshold_kind": "explicit_numeric" if value is not None else "non_numeric",
                      "applicable_region": item.get("region") or "全国（仍须核对条款适用范围）",
                      "effective_at": item.get("effective_at") or source.get("effective_at"),
                      "expires_at": item.get("expires_at") or source.get("expires_at")}
        elif module == "permit":
            fields = {"permit_name": name, "requirement_text": text, "applicable_stage": stage,
                      "applicable_region": item.get("region") or "全国；按项目类别和所在地实施",
                      "status_note": item.get("notes")}
        elif module == "document":
            fields = {"document_name": name, "requirement_text": text,
                      "mandatory_basis": locator if derivation == "policy_explicit" else "来源衍生的核验建议，非固定必交文件",
                      "applicable_stage": stage, "derivation_type": derivation,
                      "acceptable_alternatives": item.get("alternatives")}
        elif module == "evidence":
            fields = {"evidence_object": name, "requirement_text": text,
                      "acceptable_evidence": item.get("acceptable_evidence") or text,
                      "unacceptable_substitution": item.get("unacceptable_substitution"),
                      "applicable_stage": stage, "derivation_type": derivation}
        elif module == "risk":
            fields = {"risk_category": item.get("category") or "行业核验关注点", "risk_title": name,
                      "risk_description": text, "review_focus": item.get("review_focus") or text,
                      "derivation_type": derivation,
                      "formal_rule_eligible": int(derivation == "policy_explicit" and source["formal_rule_eligible"])}
        elif module == "postloan":
            fields = {"indicator_name": name, "definition_text": text, "formula_text": item.get("formula"),
                      "unit": item.get("unit"), "frequency": item.get("frequency"),
                      "evidence_object": item.get("evidence_object") or text, "derivation_type": derivation}
        elif module == "term":
            fields = {"term": name, "definition_text": text, "usage_note": item.get("notes") or "辅助阅读释义；须按原文边界使用。"}
        _upsert(uow, table, {PRIMARY_KEYS[table]: stable_id(module, identity), **common, **fields})


def apply_content_rework(uow, original_sources):
    """Called in the same transaction as the master build (including rollback)."""
    # Correct priority identity rather than rewriting the authoritative industry tree.
    for code, expected in (("5411", "公共电汽车客运"), ("5413", "出租车客运")):
        row = uow.connection.execute("SELECT name FROM industry_taxonomy WHERE code=?", (code,)).fetchone()
        if row is None or row["name"] != expected:
            raise ValueError(f"官方行业分类校验失败：{code}应为{expected}")
    # Retain earlier non-numeric requirements as requirements, never as numeric limits.
    uow.connection.execute("""UPDATE threshold_definitions SET threshold_kind='non_numeric'
        WHERE threshold_value IS NULL OR TRIM(threshold_value)=''""")
    green_source = original_sources["green"]["source_id"]
    mappings = uow.connection.execute("""SELECT m.*, g.catalog_code FROM industry_activity_mappings m
        JOIN green_catalog_activities g ON g.green_activity_id=m.target_activity_id
        WHERE m.industry_code='4415' AND m.mapping_domain='green_catalog'""").fetchall()
    for row in mappings:
        role = "core" if row["catalog_code"] == "4.2.1" else "adjacent"
        changes = {"relationship_role": role}
        if role == "adjacent":
            changes["mapping_type"] = "conditional"
            changes["non_applicable_conditions"] = "相邻可能活动：仅在材料明确证明该独立活动时另行核验；不因企业属于风力发电行业自动适用，不计风电深度包。"
        uow.update("industry_activity_mappings", row["mapping_id"], changes)
        # Mapping-generated content remains, but has exactly the same scope as its mapping.
        for table, prefix in (("indicator_definitions", "indicator"), ("evidence_requirements", "evidence_req"),
                              ("industry_risk_points", "riskpoint"), ("threshold_definitions", "threshold")):
            key = stable_id(prefix, f"green-2025:4415:{row['catalog_code']}")
            if uow.get(table, key):
                uow.update(table, key, {"scope_status": role})
        for link in uow.connection.execute("SELECT * FROM industry_standard_links WHERE industry_code='4415' AND source_id=? AND applicability=?",
                                           (green_source, f"绿色目录 {row['catalog_code']} 明文引用")).fetchall():
            uow.update("industry_standard_links", link["link_id"], {"scope_status": role})
    _load_research(uow, "rework_wind_sources.json", "4415")
    _load_research(uow, "rework_iron_sources.json", "3110")
    # The two curated packages above have been reviewed module-by-module.  This
    # flag does not make missing content pass; it only records that the coverage
    # table itself has been checked.  4415 therefore remains partial while its
    # public numeric-threshold module is empty.
    uow.connection.execute(
        "UPDATE industry_rule_profiles SET coverage_review_status='reviewed' "
        "WHERE industry_code IN ('4415','3110')"
    )
