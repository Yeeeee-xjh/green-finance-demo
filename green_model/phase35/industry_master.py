"""Build and query case-independent industry master data.

The national industry tree is parsed from the official NBS annotation workbook.
Green and regional transition catalogues are attached as many-to-many mappings;
they are deliberately not represented as top-level industries.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from green_model.agent.domain.models import stable_id, utc_now
from green_model.agent.storage import Database, SQLiteRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "phase1" / "green_finance_phase1.sqlite3"
MASTER_ROOT = PROJECT_ROOT / "data" / "industry_master"
SOURCE_ROOT = MASTER_ROOT / "sources"
NBS_XLSX = SOURCE_ROOT / "GB_T_4754_2017_注释_第1号修改单.xlsx"
NBS_PDF = SOURCE_ROOT / "GB_T_4754_2017_第1号修改单.pdf"
GREEN_PDF = WORKSPACE_ROOT / "data_policy" / "green_catlog_2025.pdf"
HEBEI_PDF = WORKSPACE_ROOT / "tmp" / "河北省钢铁行业转型金融工作指引_2025年版.pdf"
HEBEI_OLD_PDF = WORKSPACE_ROOT / "data_policy" / "hebei_steel_transition_2024.pdf"
JIANGSU_PDF = WORKSPACE_ROOT / "data_policy" / "jiangsu_building_materials_transition_2024.pdf"
NDRC_EFFICIENCY_PDF = SOURCE_ROOT / "工业重点领域能效标杆水平和基准水平_2023年版.pdf"
NEA_COAL_GAS_HTML = SOURCE_ROOT / "国家能源局_关于规范煤制天然气产业发展有关事项的通知.html"
GREEN_ROWS = PROJECT_ROOT / "loan_review" / "data" / "catalog_rows_2025_full.json"
GREEN_ENTRIES = PROJECT_ROOT / "loan_review" / "data" / "catalog_entries_2025_full.json"

NBS_URL = "https://www.stats.gov.cn/sj/tjbz/gmjjhyfl/"
NBS_XLSX_URL = "https://www.stats.gov.cn/sj/tjbz/gmjjhyfl/202302/P020230213403084213497.xlsx"
GREEN_URL = "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/5779612/2025071418513641380.pdf"
HEBEI_URL = "https://shijiazhuang.pbc.gov.cn/shijiazhuang/fileDir/resource/cms/2025/04/2025042714100799205.pdf"
JIANGSU_URL = "https://nanjing.pbc.gov.cn/nanjing/117542/117557/5499324/5579843/2025020516540963278.pdf"
NDRC_EFFICIENCY_URL = "https://www.ndrc.gov.cn/xwdt/tzgg/202307/P020230704381677315075.pdf"
NEA_COAL_GAS_URL = "https://www.nea.gov.cn/2010-06/18/c_131097733.htm"

PUBLIC_TEXT_GAP = "公开渠道未获取全文，当前仅登记公开可见信息。"
BANK_RULE_GAP = "银行内部规则未接入，无法判断。"

PRIORITY_1 = (
    "4415", "4416", "4414", "4417", "4420", "3110", "3120", "3011",
    "3041", "3071", "2521", "2522", "3216", "3211", "7721", "7722",
    "7723", "4210", "4220", "4872", "4812", "5412", "4710",
)
PRIORITY_2 = (
    "3824", "3825", "3841", "2611", "2612", "2621", "2651", "3212",
    "7724", "4813", "4862", "5411",
)
PRIORITY_3 = (
    "3072", "3073", "3051", "3052", "3053", "3054", "2911", "2912",
    "2913", "2914", "2915", "2916", "2919", "2921", "2922", "2923",
    "2924", "2925", "2926", "2927", "2928", "2929",
)
PRIORITY_BY_CODE = {
    **{code: 1 for code in PRIORITY_1},
    **{code: 2 for code in PRIORITY_2},
    **{code: 3 for code in PRIORITY_3},
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(*cells: Any) -> str:
    parts = [str(value).strip() for value in cells if value is not None and str(value).strip()]
    if parts and parts[0] in {"—", "-"}:
        parts = parts[1:]
    return "".join(parts).strip()


@dataclass
class TaxonomyNode:
    code: str
    name: str
    level: str
    parent_code: str | None
    section_code: str
    sort_order: int
    description_lines: list[str] = field(default_factory=list)
    included_lines: list[str] = field(default_factory=list)
    excluded_lines: list[str] = field(default_factory=list)

    @property
    def description(self) -> str | None:
        return "\n".join(self.description_lines).strip() or None

    @property
    def included(self) -> str | None:
        return "\n".join(self.included_lines).strip() or None

    @property
    def excluded(self) -> str | None:
        return "\n".join(self.excluded_lines).strip() or None


def parse_nbs_taxonomy(path: Path = NBS_XLSX) -> list[TaxonomyNode]:
    """Parse the official annotation workbook without inventing missing fields."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    nodes: list[TaxonomyNode] = []
    current: TaxonomyNode | None = None
    mode = "description"
    section = division = group = None

    def finish() -> None:
        nonlocal current
        if current is not None:
            nodes.append(current)
            current = None

    def start(code: str, name: str, level: str, row_no: int) -> None:
        nonlocal current, mode, section, division, group
        finish()
        if level == "section":
            parent = None
            section, division, group = code, None, None
        elif level == "division":
            parent = section
            division, group = code, None
        elif level == "group":
            parent = division
            group = code
        else:
            parent = group
        if not section or (level != "section" and not parent):
            raise ValueError(f"行业树父级缺失：{code} / row {row_no}")
        current = TaxonomyNode(code, name, level, parent, section, len(nodes) + 1)
        mode = "description"

    for row_no, row in enumerate(sheet.iter_rows(max_col=5, values_only=True), start=1):
        col_a, col_b, col_c, col_d, col_e = row
        candidates: list[tuple[str, str]] = []
        if col_a is not None:
            value = str(col_a).strip()
            if re.fullmatch(r"[A-T]", value):
                candidates.append((value, "section"))
            elif re.fullmatch(r"\d{2}", value):
                candidates.append((value, "division"))
            elif re.fullmatch(r"\d{3}", value):
                candidates.append((value, "group"))
        if col_b is not None and re.fullmatch(r"\d{4}", str(col_b).strip()):
            candidates.append((str(col_b).strip(), "class"))
        if candidates:
            name = str(col_d or "").strip()
            if not name:
                raise ValueError(f"行业名称缺失：{candidates} / row {row_no}")
            for code, level in candidates:
                start(code, name, level, row_no)
            continue
        if current is None:
            continue
        marker = str(col_c or "").strip()
        text = _text(col_d, col_e)
        if marker == "◇" or text.startswith("包括对下列") or text.startswith("包括："):
            mode = "included"
        if marker == "◆" or text.startswith("不包括"):
            mode = "excluded"
        elif mode == "included" and "列入" in text and not text.startswith("包括"):
            mode = "excluded"
        if not text or text in {"◇", "◆", "—"}:
            continue
        target = {
            "description": current.description_lines,
            "included": current.included_lines,
            "excluded": current.excluded_lines,
        }[mode]
        target.append(text)
    finish()
    counts = Counter(node.level for node in nodes)
    expected = {"section": 20, "division": 97, "group": 473, "class": 1382}
    if counts != expected:
        raise ValueError(f"官方行业树数量不一致：{dict(counts)} != {expected}")
    codes = {node.code for node in nodes}
    orphans = [node.code for node in nodes if node.parent_code and node.parent_code not in codes]
    if orphans:
        raise ValueError(f"行业树存在孤儿节点：{orphans[:10]}")
    return nodes


def _source_record(
    *, key: str, path: Path, name: str, issuer: str, url: str,
    version: str, authority: str, standard_no: str | None = None,
    document_no: str | None = None, published_at: str | None = None,
    effective_at: str | None = None, status: str = "full_text_obtained",
    formal: bool = True, limitation: str | None = None,
    is_mandatory: bool | None = None,
) -> dict[str, Any]:
    digest = file_sha256(path)
    return {
        "source_id": stable_id("srcm", f"phase35:{key}:{digest}"),
        "source_name": name,
        "issuer": issuer,
        "document_no": document_no,
        "standard_no": standard_no,
        "version_label": version,
        "published_at": published_at,
        "effective_at": effective_at,
        "expires_at": None,
        "source_url": url,
        "local_path": str(path.resolve()),
        "sha256": digest,
        "accessed_at": utc_now(),
        "authority_level": authority,
        "is_mandatory": None if is_mandatory is None else int(is_mandatory),
        "formal_rule_eligible": int(formal),
        "availability_status": status,
        "limitation_note": limitation,
        "superseded_by_source_id": None,
    }


def _extract_standard_references(text: str) -> set[tuple[str | None, str]]:
    results: set[tuple[str | None, str]] = set()
    number = r"(?:GB(?:/T)?|HJ|JC/T|JGJ|TSG|ISO|T/CECS|BDS)[ -]?[A-Za-z0-9.\-/]+"
    for match in re.finditer(rf"({number})\s*《([^》]{{2,80}})》", text):
        results.add((re.sub(r"\s+", " ", match.group(1)).strip(), match.group(2).strip()))
    for match in re.finditer(rf"《([^》]{{2,80}})》\s*[（(]\s*({number})\s*[）)]", text):
        results.add((re.sub(r"\s+", " ", match.group(2)).strip(), match.group(1).strip()))
    return results


class IndustryMasterBuilder:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE):
        self.database = Database(database_path)
        self.database.initialize()
        self.repository = SQLiteRepository(self.database)

    def _sources(self) -> dict[str, dict[str, Any]]:
        required = (
            NBS_XLSX, NBS_PDF, GREEN_PDF, HEBEI_PDF, HEBEI_OLD_PDF,
            JIANGSU_PDF, NDRC_EFFICIENCY_PDF, NEA_COAL_GAS_HTML,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("缺少必需官方原件：" + "; ".join(missing))
        sources = {
            "nbs": _source_record(
                key="nbs-annotation", path=NBS_XLSX,
                name="2017年国民经济行业分类注释（按第1号修改单修订）",
                issuer="国家统计局", url=NBS_XLSX_URL,
                version="GB/T 4754—2017（按第1号修改单修订）",
                standard_no="GB/T 4754—2017", authority="national_standard_official_annotation",
                published_at="2017-06-30", effective_at="2017-10-01",
                is_mandatory=False,
            ),
            "nbs_pdf": _source_record(
                key="nbs-standard-pdf", path=NBS_PDF,
                name="国民经济行业分类（GB/T 4754—2017，按第1号修改单修订）",
                issuer="国家统计局/国家市场监督管理总局、国家标准化管理委员会",
                url=NBS_URL,
                version="GB/T 4754—2017（按第1号修改单修订）",
                standard_no="GB/T 4754—2017", authority="national_standard_official_full_text",
                published_at="2017-06-30", effective_at="2017-10-01",
                is_mandatory=False,
            ),
            "green": _source_record(
                key="green-2025", path=GREEN_PDF, name="绿色金融支持项目目录（2025年版）",
                issuer="中国人民银行等部门", url=GREEN_URL, version="2025年版",
                authority="national_policy_official_full_text", published_at="2025-07-14",
            ),
            "hebei": _source_record(
                key="hebei-steel-2025", path=HEBEI_PDF, name="河北省钢铁行业转型金融工作指引（2025年版）",
                issuer="中国人民银行河北省分行等部门", url=HEBEI_URL, version="2025年版",
                authority="regional_policy_official_full_text", published_at="2025-04-27",
            ),
            "hebei_old": _source_record(
                key="hebei-steel-2023-2024", path=HEBEI_OLD_PDF,
                name="河北省钢铁行业转型金融工作指引（2023—2024年版）",
                issuer="河北省有关部门", url="", version="2023—2024年版",
                authority="regional_policy_historical_full_text",
                status="superseded", formal=False,
                limitation="已废止，仅用于版本关系核对；不作为现行规则。",
            ),
            "jiangsu": _source_record(
                key="jiangsu-materials-2024", path=JIANGSU_PDF,
                name="江苏省转型金融支持经济活动目录（建材行业）2024年版",
                issuer="中国人民银行江苏省分行", url=JIANGSU_URL, version="2024年版",
                authority="regional_policy_official_full_text", published_at="2025-02-05",
            ),
            "ndrc_efficiency": _source_record(
                key="ndrc-efficiency-2023", path=NDRC_EFFICIENCY_PDF,
                name="工业重点领域能效标杆水平和基准水平（2023年版）",
                issuer="国家发展改革委等部门", url=NDRC_EFFICIENCY_URL,
                version="2023年版", document_no="发改产业〔2023〕723号",
                authority="national_policy_official_full_text",
                published_at="2023-07-04", effective_at="2023-06-06",
            ),
            "nea_coal_gas": _source_record(
                key="nea-coal-gas-2010", path=NEA_COAL_GAS_HTML,
                name="关于规范煤制天然气产业发展有关事项的通知",
                issuer="国家发展改革委（国家能源局官网公开）", url=NEA_COAL_GAS_URL,
                version="2010年公开版", document_no="发改能源〔2010〕1205号",
                authority="national_policy_official_webpage",
                published_at="2010-06-18", formal=False,
                limitation="历史公开政策，仅用于行业知识与核验要点；现行适用性须人工复核。",
            ),
        }
        sources["hebei_old"]["superseded_by_source_id"] = sources["hebei"]["source_id"]
        return sources

    def build(self, *, export: bool = True) -> dict[str, Any]:
        nodes = parse_nbs_taxonomy()
        sources = self._sources()
        node_by_code = {node.code: node for node in nodes}
        counts: Counter[str] = Counter()
        with self.repository.transaction() as uow:
            for source in sources.values():
                uow.insert("source_manifest", source, on_conflict="ignore")
            uow.insert("rule_version_relations", {
                "relation_id": stable_id("version", "hebei-steel-2023-2024:replaced-by:2025"),
                "old_source_id": sources["hebei_old"]["source_id"],
                "new_source_id": sources["hebei"]["source_id"],
                "relation_type": "replaces",
                "relation_note": "2023—2024年版已废止；现行公开规则登记为2025年版。",
            }, on_conflict="ignore")
            counts["rule_version_relations"] += 1
            nbs = sources["nbs"]
            for node in nodes:
                node_id = stable_id("industry", f"gbt4754-2017-am1:{node.code}")
                uow.insert("industry_taxonomy", {
                    "node_id": node_id,
                    "code": node.code,
                    "name": node.name,
                    "level": node.level,
                    "parent_node_id": stable_id("industry", f"gbt4754-2017-am1:{node.parent_code}") if node.parent_code else None,
                    "parent_code": node.parent_code,
                    "section_code": node.section_code,
                    "official_description": node.description,
                    "included_activities": node.included,
                    "excluded_activities": node.excluded,
                    "source_id": nbs["source_id"],
                    "source_version": nbs["version_label"],
                    "source_url": nbs["source_url"],
                    "accessed_at": nbs["accessed_at"],
                    "source_sha256": nbs["sha256"],
                    "sort_order": node.sort_order,
                }, on_conflict="ignore")
                counts[f"taxonomy_{node.level}"] += 1
                if node.level != "class":
                    continue
                priority = PRIORITY_BY_CODE.get(node.code)
                build_status = "partial_public_sources" if priority in (1, 2) else "pending" if priority == 3 else "base_only"
                missing = ["典型流程", "核心设备", "行业专属审批许可", "银行内部规则"]
                uow.insert("industry_rule_profiles", {
                    "profile_id": stable_id("profile", f"gbt4754-2017-am1:{node.code}"),
                    "industry_code": node.code,
                    "taxonomy_node_id": node_id,
                    "priority_level": priority,
                    "build_status": build_status,
                    "completion_percent": 10 if priority else 5,
                    "industry_definition": node.description,
                    "boundary_text": "\n".join(filter(None, [node.included, node.excluded])) or None,
                    "missing_modules_json": _json(missing),
                    "bank_rule_status": BANK_RULE_GAP,
                    "source_id": nbs["source_id"],
                }, on_conflict="ignore")
                if priority:
                    uow.insert("term_cards", {
                        "term_id": stable_id("term", f"gbt4754:{node.code}:{node.name}"),
                        "industry_code": node.code,
                        "term": node.name,
                        "definition_text": node.description or f"GB/T 4754—2017行业小类 {node.code}。",
                        "usage_note": "用于行业定标与项目活动边界对照，不直接代替授信准入判断。",
                        "source_page": None,
                        "source_id": nbs["source_id"],
                    }, on_conflict="ignore")
            self._insert_green_catalog(uow, sources["green"], node_by_code, counts)
            self._insert_hebei_overlay(uow, sources["hebei"], counts)
            self._insert_jiangsu_overlay(uow, sources["jiangsu"], counts)
            self._insert_ndrc_efficiency(uow, sources["ndrc_efficiency"], counts)
            self._insert_nea_coal_gas(uow, sources["nea_coal_gas"], counts)
            from .content_rework import apply_content_rework
            apply_content_rework(uow, sources)
            self._refresh_profiles(uow, counts)
            uow.insert("industry_build_logs", {
                "build_log_id": stable_id("build", f"phase35:{nbs['sha256']}:{sources['green']['sha256']}"),
                "industry_code": None,
                "build_stage": "phase3.5",
                "build_status": "completed",
                "message": "全量行业树与公开来源规则映射已完成；未获取内容保持空值或明确缺口。",
                "source_id": nbs["source_id"],
            }, on_conflict="ignore")
        exported = self.export_master_data(nodes, sources) if export else {}
        with self.database.transaction(immediate=False) as connection:
            actual_counts = {
                "taxonomy_section": connection.execute("SELECT COUNT(*) FROM industry_taxonomy WHERE level='section'").fetchone()[0],
                "taxonomy_division": connection.execute("SELECT COUNT(*) FROM industry_taxonomy WHERE level='division'").fetchone()[0],
                "taxonomy_group": connection.execute("SELECT COUNT(*) FROM industry_taxonomy WHERE level='group'").fetchone()[0],
                "taxonomy_class": connection.execute("SELECT COUNT(*) FROM industry_taxonomy WHERE level='class'").fetchone()[0],
                "green_activities": connection.execute("SELECT COUNT(*) FROM green_catalog_activities").fetchone()[0],
                "green_mappings": connection.execute("SELECT COUNT(*) FROM industry_activity_mappings WHERE mapping_domain='green_catalog'").fetchone()[0],
                "transition_mappings": connection.execute("SELECT COUNT(*) FROM industry_activity_mappings WHERE mapping_domain='transition_catalog'").fetchone()[0],
                "priority_1_profiles": connection.execute("SELECT COUNT(*) FROM industry_rule_profiles WHERE priority_level=1").fetchone()[0],
                "priority_2_profiles": connection.execute("SELECT COUNT(*) FROM industry_rule_profiles WHERE priority_level=2").fetchone()[0],
                "priority_3_profiles": connection.execute("SELECT COUNT(*) FROM industry_rule_profiles WHERE priority_level=3").fetchone()[0],
                "source_manifest": connection.execute("SELECT COUNT(*) FROM source_manifest").fetchone()[0],
                "rule_version_relations": connection.execute("SELECT COUNT(*) FROM rule_version_relations").fetchone()[0],
            }
        return {"counts": actual_counts, "build_events": dict(counts), "sources": actual_counts["source_manifest"], **exported}

    def _insert_green_catalog(self, uow, source: dict[str, Any], nodes: dict[str, TaxonomyNode], counts: Counter[str]) -> None:
        entries = json.loads(GREEN_ENTRIES.read_text(encoding="utf-8"))
        rows = json.loads(GREEN_ROWS.read_text(encoding="utf-8"))
        for entry in entries:
            code = str(entry.get("catalog_code") or "").strip()
            activity_id = stable_id("green", f"green-2025:{code}")
            uow.insert("green_catalog_activities", {
                "green_activity_id": activity_id,
                "catalog_code": code,
                "activity_name": entry.get("project_name") or entry.get("level3") or code,
                "level1_name": entry.get("level1"),
                "level2_name": entry.get("level2"),
                "ghg_reduction_contribution": int(bool(entry.get("ghg_reduction_contribution"))),
                "source_page": ",".join(str(v) for v in entry.get("source_pages") or []),
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            counts["green_activities"] += 1
        standards_seen: set[tuple[str, str | None, str]] = set()
        for row in rows:
            catalog_code = str(row.get("catalog_code") or "").strip()
            activity_id = stable_id("green", f"green-2025:{catalog_code}")
            conditions = str(row.get("conditions") or "").strip() or None
            remarks = str(row.get("remarks") or "").strip() or None
            pages = ",".join(str(v) for v in row.get("source_pages") or []) or None
            for raw_code in row.get("industry_codes") or []:
                industry_code = str(raw_code).strip()
                if industry_code not in nodes or len(industry_code) != 4:
                    continue
                mapping_id = stable_id("mapping", f"green-2025:{industry_code}:{catalog_code}")
                uow.insert("industry_activity_mappings", {
                    "mapping_id": mapping_id,
                    "industry_code": industry_code,
                    "project_activity_name": row.get("project_name") or row.get("level3") or catalog_code,
                    "mapping_domain": "green_catalog",
                    "target_activity_id": activity_id,
                    "mapping_type": "conditional" if conditions else "direct",
                    "applicable_conditions": conditions,
                    "non_applicable_conditions": remarks,
                    "evidence_requirement": f"应能证明目录明文条件：{conditions}" if conditions else None,
                    "applicable_region": "全国",
                    "source_page": pages,
                    "source_file_hash": source["sha256"],
                    "source_id": source["source_id"],
                }, on_conflict="ignore")
                counts["green_mappings"] += 1
                if industry_code in PRIORITY_BY_CODE:
                    indicator_id = stable_id("indicator", f"green-2025:{industry_code}:{catalog_code}")
                    uow.insert("indicator_definitions", {
                        "indicator_definition_id": indicator_id,
                        "industry_code": industry_code,
                        "indicator_name": f"{catalog_code} {row.get('project_name') or '目录活动'}条件符合性",
                        "definition_text": conditions or "核对项目活动与目录活动范围。",
                        "formula_text": None,
                        "statistical_scope": "按目录活动、项目范围和明文条件逐项对照",
                        "unit": None,
                        "applicable_stage": "贷前/贷中核验",
                        "derivation_type": "policy_explicit",
                        "formal_rule_eligible": 1,
                        "source_page": pages,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")
                    uow.insert("evidence_requirements", {
                        "evidence_requirement_id": stable_id("evidence_req", f"green-2025:{industry_code}:{catalog_code}"),
                        "industry_code": industry_code,
                        "evidence_object": f"{catalog_code} {row.get('project_name') or '目录活动'}明文条件",
                        "requirement_text": conditions or "项目事实应与目录活动范围一致。",
                        "acceptable_evidence": None,
                        "unacceptable_substitution": "仅有企业绿色形象或不能定位到项目的披露，不足以代替项目证据。",
                        "applicable_stage": "贷前/贷中核验",
                        "source_page": pages,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")
                    uow.insert("industry_risk_points", {
                        "risk_point_id": stable_id("riskpoint", f"green-2025:{industry_code}:{catalog_code}"),
                        "industry_code": industry_code,
                        "risk_category": "目录条件对应风险",
                        "risk_title": f"{catalog_code}活动边界或条件无法由项目证据支持",
                        "risk_description": conditions or "项目活动范围与目录活动不应只凭名称对应。",
                        "review_focus": "回到目录原文与项目证据，核对活动边界、技术条件、统计口径和原文位置。",
                        "derivation_type": "source_derived",
                        "formal_rule_eligible": 0,
                        "source_page": pages,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")
                    if conditions and re.search(r"\d|%|不低于|不高于|以上|以下|限值|标杆|先进值|[<>]", conditions):
                        uow.insert("threshold_definitions", {
                            "threshold_id": stable_id("threshold", f"green-2025:{industry_code}:{catalog_code}"),
                            "indicator_definition_id": indicator_id,
                            "industry_code": industry_code,
                            "threshold_text": conditions,
                            "operator": "按政策原文复核",
                            "threshold_value": None,
                            "unit": None,
                            "applicable_region": "全国",
                            "source_page": pages,
                            "source_id": source["source_id"],
                        }, on_conflict="ignore")
                for standard_no, standard_name in _extract_standard_references("\n".join(filter(None, [conditions, remarks]))):
                    key = (industry_code, standard_no, standard_name)
                    if key in standards_seen:
                        continue
                    standards_seen.add(key)
                    standard_id = stable_id("standard", f"green-2025-ref:{standard_no}:{standard_name}")
                    uow.insert("standard_catalog", {
                        "standard_id": standard_id,
                        "standard_no": standard_no,
                        "standard_name": standard_name,
                        "standard_type": "绿色目录引用标准",
                        "issuer": None,
                        "full_text_status": "reference_only",
                        "public_scope_note": PUBLIC_TEXT_GAP,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")
                    uow.insert("industry_standard_links", {
                        "link_id": stable_id("stdlink", f"{industry_code}:{standard_id}:{catalog_code}"),
                        "industry_code": industry_code,
                        "standard_id": standard_id,
                        "applicability": f"绿色目录 {catalog_code} 明文引用",
                        "source_page": pages,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")

    def _insert_hebei_overlay(self, uow, source: dict[str, Any], counts: Counter[str]) -> None:
        codes = ("3110", "3120", "4210")
        activity_id = stable_id("transition", "hebei-steel-2025:overall-plan")
        requirement = (
            "钢铁企业应具有整体转型方案，明确短中长期目标、技术路径、"
            "投融资计划和治理实施方案，并按指引进行评估与持续披露。"
        )
        uow.insert("transition_catalog_activities", {
            "transition_activity_id": activity_id,
            "activity_code": "HB-STEEL-2025-OVERALL",
            "activity_name": "钢铁企业整体转型方案与投融资计划",
            "industry_scope": "钢铁企业及废钢铁加工企业",
            "applicable_region": "河北省",
            "requirement_text": requirement,
            "source_page": "1-5",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        for code in codes:
            uow.insert("industry_activity_mappings", {
                "mapping_id": stable_id("mapping", f"hebei-steel-2025:{code}:overall"),
                "industry_code": code,
                "project_activity_name": "钢铁行业转型经济活动",
                "mapping_domain": "transition_catalog",
                "target_activity_id": activity_id,
                "mapping_type": "conditional",
                "applicable_conditions": requirement,
                "non_applicable_conditions": "非河北项目仅可作规则能力参考，不具有属地认定效力。",
                "evidence_requirement": "按指引提供转型方案、评估与披露所需证据。",
                "applicable_region": "河北省",
                "source_page": "1-5",
                "source_file_hash": source["sha256"],
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("regional_rule_overlays", {
                "overlay_id": stable_id("overlay", f"hebei-steel-2025:{code}"),
                "industry_code": code,
                "region": "河北省",
                "overlay_name": "河北省钢铁行业转型金融工作指引（2025年版）",
                "requirement_text": requirement,
                "source_page": "1-5",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            for name, definition, page in (
                ("短期碳排放强度目标", "短期目标以定量的碳排放强度表示。", "2"),
                ("中长期碳排放总量目标", "中、长期目标兼顾碳排放总量。", "2"),
                ("主要工序碳排放预期值", "投资计划涉及的主要工序碳排放指标预期值。", "2"),
                ("主要工序能耗水平", "投资计划涉及的主要工序能耗预期水平。", "2-3"),
            ):
                indicator_id = stable_id("indicator", f"hebei-steel-2025:{code}:{name}")
                uow.insert("indicator_definitions", {
                    "indicator_definition_id": indicator_id,
                    "industry_code": code, "indicator_name": name,
                    "definition_text": definition, "applicable_stage": "转型方案与贷中核验",
                    "derivation_type": "policy_explicit", "formal_rule_eligible": 1,
                    "source_page": page, "source_id": source["source_id"],
                }, on_conflict="ignore")
                if "预期值" in name or "能耗" in name:
                    threshold = "主要工序碳排放预期值低于河北省指定基准值。" if "碳排放" in name else "主要工序能耗达到国家规定的标杆、先进或国际先进水平。"
                    uow.insert("threshold_definitions", {
                        "threshold_id": stable_id("threshold", f"hebei-steel-2025:{code}:{name}"),
                        "indicator_definition_id": indicator_id, "industry_code": code,
                        "threshold_text": threshold, "operator": "按指引明文对标",
                        "applicable_region": "河北省", "source_page": page,
                        "source_id": source["source_id"],
                    }, on_conflict="ignore")
            for doc_name, text, page in (
                ("企业整体转型方案", "指引要求钢铁企业制定符合要求的转型方案。", "2-4"),
                ("转型方案评估报告", "第三方评估机构按指引对转型方案进行评估。", "4"),
                ("年度转型信息披露", "贷款存续期内按年度披露方案落实、融资使用和关键绩效指标等。", "4"),
            ):
                uow.insert("document_requirements", {
                    "document_requirement_id": stable_id("docreq", f"hebei-steel-2025:{code}:{doc_name}"),
                    "industry_code": code, "document_name": doc_name, "requirement_text": text,
                    "mandatory_basis": "河北省钢铁行业转型金融工作指引明文要求",
                    "applicable_stage": "贷前/贷中/贷后按指引适用", "source_page": page,
                    "source_id": source["source_id"],
                }, on_conflict="ignore")
            uow.insert("postloan_indicator_definitions", {
                "postloan_indicator_id": stable_id("postloan", f"hebei-steel-2025:{code}:annual"),
                "industry_code": code, "indicator_name": "转型关键绩效指标完成情况",
                "definition_text": "按年度跟踪转型方案落实、融资使用、关键绩效、重大环境违法与第三方跟踪意见。",
                "frequency": "每年", "evidence_object": "年度披露、温室气体排放核查和第三方跟踪意见",
                "source_page": "4", "source_id": source["source_id"],
            }, on_conflict="ignore")
            counts["transition_mappings"] += 1

    def _insert_jiangsu_overlay(self, uow, source: dict[str, Any], counts: Counter[str]) -> None:
        activities = (
            ("3011", "JS-BM-1.1.1", "高贝利特低热/中热硅酸盐水泥及制备", "熟料矿物中硅酸二钙由20%提升至40%以上；产品与生产线满足目录所列标准。", "1"),
            ("3011", "JS-BM-1.3.2", "一般燃料替代（RDF）", "水泥窑烧成系统燃料替代率达到25%—50%。", "3"),
            ("3011", "JS-BM-1.4.1", "水泥窑全氧燃烧技术", "出预热器烟气中CO2浓度≥80%（干基浓度）。", "3"),
            ("3041", "JS-BM-3.1.3", "玻璃熔窑全氧燃烧成套技术装备", "依据GB 21340降低熔化单耗30%，NOx排放浓度降低到200mg/Nm3以下。", "10"),
            ("3041", "JS-BM-3.2.1", "玻璃熔窑电助熔", "电助熔比例达到20%时节能5%—8%，并满足GB 21340先进值。", "10"),
            ("3071", "JS-BM-5.3.4", "建筑陶瓷产品薄型化", "通过产品薄型化减少原材料使用，产品厚度降低10%。", "16"),
            ("3071", "JS-BM-5.4.1", "陶瓷辊道窑清洁能源技术", "结合清洁能源和薄型化工艺，目录明确全行业减碳30%以上、降低外购电5%以上。", "16"),
        )
        for industry_code, activity_code, name, requirement, page in activities:
            activity_id = stable_id("transition", f"jiangsu-materials-2024:{activity_code}")
            uow.insert("transition_catalog_activities", {
                "transition_activity_id": activity_id, "activity_code": activity_code,
                "activity_name": name, "industry_scope": industry_code,
                "applicable_region": "江苏省", "requirement_text": requirement,
                "source_page": page, "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("industry_activity_mappings", {
                "mapping_id": stable_id("mapping", f"jiangsu-materials-2024:{industry_code}:{activity_code}"),
                "industry_code": industry_code, "project_activity_name": name,
                "mapping_domain": "transition_catalog", "target_activity_id": activity_id,
                "mapping_type": "conditional", "applicable_conditions": requirement,
                "non_applicable_conditions": "非江苏项目仅可作规则能力参考，不具有属地认定效力。",
                "evidence_requirement": f"应能证明技术路线及明文指标：{requirement}",
                "applicable_region": "江苏省", "source_page": page,
                "source_file_hash": source["sha256"], "source_id": source["source_id"],
            }, on_conflict="ignore")
            indicator_id = stable_id("indicator", f"jiangsu-materials-2024:{industry_code}:{activity_code}")
            uow.insert("indicator_definitions", {
                "indicator_definition_id": indicator_id, "industry_code": industry_code,
                "indicator_name": name, "definition_text": requirement,
                "applicable_stage": "贷中技术路线核验", "derivation_type": "policy_explicit",
                "formal_rule_eligible": 1, "source_page": page, "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("threshold_definitions", {
                "threshold_id": stable_id("threshold", f"jiangsu-materials-2024:{industry_code}:{activity_code}"),
                "indicator_definition_id": indicator_id, "industry_code": industry_code,
                "threshold_text": requirement, "operator": "按目录原文复核",
                "applicable_region": "江苏省", "source_page": page,
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("regional_rule_overlays", {
                "overlay_id": stable_id("overlay", f"jiangsu-materials-2024:{industry_code}"),
                "industry_code": industry_code, "region": "江苏省",
                "overlay_name": "江苏省转型金融支持经济活动目录（建材行业）2024年版",
                "requirement_text": "对照具体技术路线的技术/说明和标准/指标核验。",
                "source_page": page, "source_id": source["source_id"],
            }, on_conflict="ignore")
            counts["transition_mappings"] += 1

    def _insert_ndrc_efficiency(self, uow, source: dict[str, Any], counts: Counter[str]) -> None:
        """Register explicit 2023 national benchmark/base levels for copper and aluminium.

        The PDF itself states that statistical scope and calculation method follow
        the referenced national standards.  We therefore keep the values and the
        standard references separate and never invent a formula.
        """
        rows = (
            ("3211", "铜冶炼工艺（铜精矿—阴极铜）单位产品综合能耗", "千克标准煤/吨", "260", "380", "GB 21248"),
            ("3211", "粗铜工艺（铜精矿—粗铜）单位产品综合能耗", "千克标准煤/吨", "140", "260", "GB 21248"),
            ("3211", "阳极铜工艺（铜精矿—阳极铜）单位产品综合能耗", "千克标准煤/吨", "180", "290", "GB 21248"),
            ("3211", "电解工序（阳极铜—阴极铜）单位产品综合能耗", "千克标准煤/吨", "85", "110", "GB 21248"),
            ("3216", "电解铝铝液交流电耗", "千瓦时/吨", "13000", "13350", "GB 21346"),
        )
        standard_names = {
            "GB 21248": "铜冶炼企业单位产品能源消耗限额",
            "GB 21346": "电解铝和氧化铝单位产品能源消耗限额",
        }
        for code, name, unit, benchmark, baseline, standard_no in rows:
            indicator_id = stable_id("indicator", f"ndrc-efficiency-2023:{code}:{name}")
            uow.insert("indicator_definitions", {
                "indicator_definition_id": indicator_id,
                "industry_code": code,
                "indicator_name": name,
                "definition_text": "用于对照工业重点领域能效标杆水平和基准水平。",
                "formula_text": None,
                "statistical_scope": f"统计范围和计算方法按{standard_no}复核",
                "unit": unit,
                "applicable_stage": "贷中技术与能效核验",
                "derivation_type": "policy_explicit",
                "formal_rule_eligible": 1,
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("threshold_definitions", {
                "threshold_id": stable_id("threshold", f"ndrc-efficiency-2023:{code}:{name}"),
                "indicator_definition_id": indicator_id,
                "industry_code": code,
                "threshold_text": f"标杆水平 {benchmark} {unit}；基准水平 {baseline} {unit}。",
                "operator": "按具体工艺分别对标",
                "threshold_value": f"benchmark={benchmark};baseline={baseline}",
                "unit": unit,
                "applicable_region": "全国",
                "effective_at": source["effective_at"],
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            standard_id = stable_id("standard", f"ndrc-efficiency-2023:{standard_no}")
            uow.insert("standard_catalog", {
                "standard_id": standard_id,
                "standard_no": standard_no,
                "standard_name": standard_names[standard_no],
                "standard_type": "能耗限额国家标准（政策附件引用）",
                "issuer": "国家市场监督管理总局、国家标准化管理委员会",
                "full_text_status": "reference_only",
                "public_scope_note": PUBLIC_TEXT_GAP,
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("industry_standard_links", {
                "link_id": stable_id("stdlink", f"ndrc-efficiency-2023:{code}:{standard_no}"),
                "industry_code": code,
                "standard_id": standard_id,
                "applicability": "能效指标统计范围和计算方法的参考标准",
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("evidence_requirements", {
                "evidence_requirement_id": stable_id("evidence_req", f"ndrc-efficiency-2023:{code}:{name}"),
                "industry_code": code,
                "evidence_object": name,
                "requirement_text": f"按{standard_no}的统计范围和计算方法核对能耗值。",
                "acceptable_evidence": "项目或生产线的产量、能源消耗、统计范围与计算底稿",
                "unacceptable_substitution": "企业整体能耗或不同工艺口径数据不能直接替代本指标。",
                "applicable_stage": "贷中核验与贷后跟踪",
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
        for code, standard_no in (("3211", "GB 21248"), ("3216", "GB 21346")):
            uow.insert("industry_risk_points", {
                "risk_point_id": stable_id("riskpoint", f"ndrc-efficiency-2023:{code}:scope"),
                "industry_code": code,
                "risk_category": "能效口径风险",
                "risk_title": "工艺边界或统计口径不一致导致对标失真",
                "risk_description": f"政策附件要求统计范围和计算方法参考{standard_no}，不同工艺数据不可混用。",
                "review_focus": "核对工艺路线、产量分母、能源范围、统计期和计算底稿。",
                "derivation_type": "source_derived",
                "formal_rule_eligible": 0,
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
            uow.insert("postloan_indicator_definitions", {
                "postloan_indicator_id": stable_id("postloan", f"ndrc-efficiency-2023:{code}:energy"),
                "industry_code": code,
                "indicator_name": "单位产品能效表现",
                "definition_text": f"按{standard_no}口径持续记录对应工艺的单位产品能耗。",
                "unit": "按具体工艺指标",
                "frequency": "按融资约定或监管要求",
                "evidence_object": "产量、能源消耗、统计范围与计算底稿",
                "source_page": "6",
                "source_id": source["source_id"],
            }, on_conflict="ignore")
        counts["national_efficiency_indicators"] += len(rows)

    def _insert_nea_coal_gas(self, uow, source: dict[str, Any], counts: Counter[str]) -> None:
        code = "2522"
        indicator_id = stable_id("indicator", "nea-coal-gas-2010:2522:supporting-conditions")
        uow.insert("indicator_definitions", {
            "indicator_definition_id": indicator_id,
            "industry_code": code,
            "indicator_name": "煤制天然气项目外部配套条件",
            "definition_text": "综合核对资源承载、能源消耗、环境容量、天然气管网和区域市场容量等配套条件。",
            "formula_text": None,
            "statistical_scope": "煤制天然气项目及其煤源、水资源、外输通道和市场配套",
            "unit": None,
            "applicable_stage": "贷前与贷中核验",
            "derivation_type": "policy_explicit",
            "formal_rule_eligible": 0,
            "source_page": "网页正文第1—3条",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        uow.insert("permit_requirements", {
            "permit_requirement_id": stable_id("permit", "nea-coal-gas-2010:2522:ndrc-approval"),
            "industry_code": code,
            "permit_name": "项目核准权限复核",
            "requirement_text": "2010年通知载明，煤制天然气及配套项目由国家发展改革委统一核准。",
            "applicable_stage": "项目核准/贷前审查",
            "applicable_region": "全国",
            "status_note": "历史公开政策；现行核准权限和程序须按最新制度人工复核。",
            "source_page": "网页正文第3条",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        uow.insert("evidence_requirements", {
            "evidence_requirement_id": stable_id("evidence_req", "nea-coal-gas-2010:2522:supporting-conditions"),
            "industry_code": code,
            "evidence_object": "煤源、水资源、环境容量、管网和市场配套事实",
            "requirement_text": "项目证据应能够支持通知列出的关键外部配套条件。",
            "acceptable_evidence": None,
            "unacceptable_substitution": "仅有项目名称或企业说明，不能证明外部配套条件已经落实。",
            "applicable_stage": "贷前与贷中核验",
            "source_page": "网页正文第1—2条",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        uow.insert("industry_risk_points", {
            "risk_point_id": stable_id("riskpoint", "nea-coal-gas-2010:2522:external-support"),
            "industry_code": code,
            "risk_category": "外部配套风险",
            "risk_title": "资源、管网或市场配套条件未落实",
            "risk_description": "煤制天然气是资源、资金、技术密集型产业，外部配套条件较多。",
            "review_focus": "逐项核对煤源、水资源、环境容量、外输通道和市场承接条件。",
            "derivation_type": "source_derived",
            "formal_rule_eligible": 0,
            "source_page": "网页正文第1—2条",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        uow.insert("term_cards", {
            "term_id": stable_id("term", "nea-coal-gas-2010:2522:coal-sng"),
            "industry_code": code,
            "term": "煤制天然气",
            "definition_text": "以煤为原料，采用气化、净化和甲烷化技术制取的合成天然气。",
            "usage_note": "历史公开政策定义；当前项目适用制度仍须复核最新版本。",
            "source_page": "网页正文第1条",
            "source_id": source["source_id"],
        }, on_conflict="ignore")
        counts["coal_gas_policy_items"] += 5

    def _refresh_profiles(self, uow, counts: Counter[str]) -> None:
        from .completeness import assess_profile
        for profile in uow.find("industry_rule_profiles"):
            code = profile["industry_code"]
            priority = PRIORITY_BY_CODE.get(code)
            assessment = assess_profile(uow.connection, code)
            # Phase 3.6 is the authoritative density assessment once it exists.
            # A later Phase 3.5 idempotent rebuild may still refresh descriptive
            # industry content, but it must never downgrade or replace that
            # source-qualified density status with the older coverage result.
            density_exists = uow.connection.execute(
                "SELECT 1 FROM industry_density_assessments WHERE industry_code=?",
                (code,),
            ).fetchone() is not None
            project_types = uow.connection.execute(
                "SELECT GROUP_CONCAT(project_activity_name, '；') AS value FROM (SELECT DISTINCT project_activity_name FROM industry_activity_mappings WHERE industry_code = ? AND relationship_role='core' ORDER BY project_activity_name LIMIT 12)",
                (code,),
            ).fetchone()["value"]
            knowledge = {module: "\n".join(row["content"] for row in uow.connection.execute(
                "SELECT content FROM industry_knowledge_items WHERE industry_code=? AND module=? AND scope_status='core' ORDER BY title", (code, module)
            )) or None for module in ("process", "equipment", "route")}
            changes = {
                "priority_level": priority,
                "common_project_types": project_types,
                "typical_processes": knowledge["process"],
                "core_equipment": knowledge["equipment"],
                "technical_routes": knowledge["route"],
                "midloan_review_focus": "按行业定义和活动边界定标，再逐项核对适用目录条件、项目事实、证据原文和属地规则。",
            }
            if not density_exists:
                changes.update({
                    "build_status": assessment["build_status"],
                    "completion_percent": assessment["completion_percent"],
                    "module_counts_json": _json(assessment["modules"]),
                    "missing_modules_json": _json(assessment["missing_modules"]),
                })
            uow.update("industry_rule_profiles", profile["profile_id"], changes)
            counts[f"priority_{priority}_profiles"] += 1

    def export_master_data(self, nodes: list[TaxonomyNode], sources: dict[str, dict[str, Any]]) -> dict[str, str]:
        MASTER_ROOT.mkdir(parents=True, exist_ok=True)
        taxonomy_path = MASTER_ROOT / "industry_taxonomy_gbt4754_2017_am1.json"
        source_path = MASTER_ROOT / "source_manifest_phase35.json"
        completion_path = MASTER_ROOT / "industry_rule_profile_completion.json"
        taxonomy_payload = [
            {
                "code": node.code, "name": node.name, "level": node.level,
                "parent_code": node.parent_code, "section_code": node.section_code,
                "official_description": node.description,
                "included_activities": node.included,
                "excluded_activities": node.excluded,
            }
            for node in nodes
        ]
        taxonomy_path.write_text(_json(taxonomy_payload), encoding="utf-8")
        source_path.write_text(_json(self.repository.find("source_manifest")), encoding="utf-8")
        completion_path.write_text(_json(self.repository.find("industry_rule_profiles", order_by="industry_code")), encoding="utf-8")
        return {
            "taxonomy_export": str(taxonomy_path),
            "source_export": str(source_path),
            "completion_export": str(completion_path),
        }


class IndustryMasterQueries:
    """Read model for the industry tree and profile page."""

    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def browse(self, *, section: str = "", division: str = "", group: str = "", class_code: str = "", query: str = "") -> dict[str, Any]:
        with self.repository.database.transaction(immediate=False) as connection:
            if class_code:
                selected = connection.execute("SELECT parent_code, section_code FROM industry_taxonomy WHERE code=? AND level='class'", (class_code,)).fetchone()
                if selected:
                    group = group or selected["parent_code"]
                    section = section or selected["section_code"]
            if group:
                selected = connection.execute("SELECT parent_code, section_code FROM industry_taxonomy WHERE code=? AND level='group'", (group,)).fetchone()
                if selected:
                    division = division or selected["parent_code"]
                    section = section or selected["section_code"]
            if division:
                selected = connection.execute("SELECT parent_code FROM industry_taxonomy WHERE code=? AND level='division'", (division,)).fetchone()
                if selected:
                    section = section or selected["parent_code"]
            counts = {
                level: connection.execute("SELECT COUNT(*) AS n FROM industry_taxonomy WHERE level = ?", (level,)).fetchone()["n"]
                for level in ("section", "division", "group", "class")
            }
            sections = [dict(row) for row in connection.execute("SELECT * FROM industry_taxonomy WHERE level='section' ORDER BY sort_order")]
            search_rows: list[dict[str, Any]] = []
            if query:
                like = f"%{query}%"
                search_rows = [dict(row) for row in connection.execute(
                    """SELECT t.*,
                              COALESCE(d.build_status, p.build_status) AS build_status,
                              COALESCE(d.completion_percent, p.completion_percent) AS completion_percent,
                              p.priority_level,
                              CASE WHEN d.density_assessment_id IS NULL
                                   THEN 'phase35_coverage' ELSE 'phase36_density' END AS assessment_source
                       FROM industry_taxonomy t
                       LEFT JOIN industry_rule_profiles p ON p.industry_code=t.code
                       LEFT JOIN industry_density_assessments d ON d.industry_code=t.code
                       WHERE t.code LIKE ? OR t.name LIKE ?
                       ORDER BY t.sort_order LIMIT 100""",
                    (like, like),
                )]
            divisions = self._children(connection, section) if section else []
            groups = self._children(connection, division) if division else []
            classes = self._children(connection, group) if group else []
            profile = self._profile(connection, class_code) if class_code else None
            return {
                "counts": counts, "sections": sections, "divisions": divisions,
                "groups": groups, "classes": classes, "profile": profile,
                "selection": {"section": section, "division": division, "group": group, "class_code": class_code},
                "query": query, "search_rows": search_rows,
            }

    @staticmethod
    def _children(connection, parent_code: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(
            """SELECT t.*,
                      COALESCE(d.build_status, p.build_status) AS build_status,
                      COALESCE(d.completion_percent, p.completion_percent) AS completion_percent,
                      p.priority_level,
                      CASE WHEN d.density_assessment_id IS NULL
                           THEN 'phase35_coverage' ELSE 'phase36_density' END AS assessment_source
               FROM industry_taxonomy t
               LEFT JOIN industry_rule_profiles p ON p.industry_code=t.code
               LEFT JOIN industry_density_assessments d ON d.industry_code=t.code
               WHERE t.parent_code=? ORDER BY t.sort_order""",
            (parent_code,),
        )]

    @staticmethod
    def _profile(connection, code: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT t.*, p.* FROM industry_taxonomy t LEFT JOIN industry_rule_profiles p ON p.industry_code=t.code WHERE t.code=? AND t.level='class'",
            (code,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        density_row = connection.execute(
            "SELECT * FROM industry_density_assessments WHERE industry_code=?",
            (code,),
        ).fetchone()
        density = dict(density_row) if density_row else None
        relations = {
            "knowledge": "SELECT * FROM industry_knowledge_items WHERE industry_code=? ORDER BY module, title",
            "standards": "SELECT l.*, s.standard_no, s.standard_name, s.full_text_status, s.public_scope_note FROM industry_standard_links l JOIN standard_catalog s ON s.standard_id=l.standard_id WHERE l.industry_code=? ORDER BY s.standard_no, s.standard_name",
            "indicators": "SELECT * FROM indicator_definitions WHERE industry_code=? ORDER BY indicator_name",
            "thresholds": "SELECT * FROM threshold_definitions WHERE industry_code=? ORDER BY threshold_id",
            "permits": "SELECT * FROM permit_requirements WHERE industry_code=? ORDER BY permit_name",
            "documents": "SELECT * FROM document_requirements WHERE industry_code=? ORDER BY document_name",
            "evidence": "SELECT * FROM evidence_requirements WHERE industry_code=? ORDER BY evidence_object",
            "risks": "SELECT * FROM industry_risk_points WHERE industry_code=? ORDER BY risk_category, risk_title",
            "postloan": "SELECT * FROM postloan_indicator_definitions WHERE industry_code=? ORDER BY indicator_name",
            "terms": "SELECT * FROM term_cards WHERE industry_code=? ORDER BY term",
            "mappings": "SELECT m.*, s.source_name, s.issuer, s.version_label FROM industry_activity_mappings m JOIN source_manifest s ON s.source_id=m.source_id WHERE m.industry_code=? ORDER BY m.mapping_domain, m.project_activity_name",
            "overlays": "SELECT o.*, s.source_name, s.source_url, s.version_label FROM regional_rule_overlays o JOIN source_manifest s ON s.source_id=o.source_id WHERE o.industry_code=? ORDER BY o.region",
        }
        for key, sql in relations.items():
            result[key] = [dict(item) for item in connection.execute(sql, (code,))]
        source_ids = {item.get("source_id") for key in relations for item in result[key] if item.get("source_id")}
        source_ids.add(result.get("source_id"))
        source_ids = {source_id for source_id in source_ids if source_id}
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            params = tuple(sorted(source_ids))
            result["sources"] = [dict(item) for item in connection.execute(
                f"""
                SELECT s.*, replacement.source_name AS replaced_by_name,
                       relation.relation_type, relation.relation_note
                FROM source_manifest s
                LEFT JOIN source_manifest replacement ON replacement.source_id=s.superseded_by_source_id
                LEFT JOIN rule_version_relations relation ON relation.old_source_id=s.source_id
                WHERE s.source_id IN ({placeholders})
                   OR s.superseded_by_source_id IN ({placeholders})
                ORDER BY CASE s.availability_status WHEN 'superseded' THEN 1 ELSE 0 END,
                         s.source_name
                """,
                params + params,
            )]
        else:
            result["sources"] = []
        if density:
            from .completeness import MODULE_LABELS

            try:
                density_counts = json.loads(density.get("module_counts_json") or "{}")
                unmet_gates = json.loads(density.get("unmet_gates_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                density_counts, unmet_gates = {}, []
            unmet_by_module = {
                str(item.get("module")): item
                for item in unmet_gates
                if isinstance(item, dict) and item.get("module")
            }
            modules: dict[str, dict[str, Any]] = {}
            for module, label in MODULE_LABELS.items():
                item = density_counts.get(module) or {}
                raw_count = int(item.get("raw") or 0)
                qualified_count = int(item.get("qualified") or 0)
                required = item.get("required")
                gap = unmet_by_module.get(module)
                if gap:
                    reason = (
                        f"密度门槛 {qualified_count}/{int(gap.get('required') or 0)}；"
                        f"尚缺 {max(int(gap.get('required') or 0) - qualified_count, 0)} 条合格内容"
                    )
                elif required is None:
                    reason = "本行业未设置统一数值门槛；已登记内容仍按来源资格单独核验"
                else:
                    reason = f"已达到密度门槛 {qualified_count}/{int(required)}"
                modules[module] = {
                    "label": label,
                    "raw_count": raw_count,
                    "qualified_count": qualified_count,
                    "required_count": required,
                    "official_explicit_count": int(item.get("official_explicit") or 0),
                    "source_derived_count": int(item.get("source_derived") or 0),
                    "status": "qualified" if required is not None and qualified_count >= int(required) else "gap",
                    "reason": reason,
                }
            result.update({
                "build_status": density.get("build_status"),
                "completion_percent": density.get("completion_percent"),
                "modules": modules,
                "missing_modules": [
                    f"{MODULE_LABELS.get(str(item.get('module')), str(item.get('module')))}："
                    f"合格 {int(item.get('qualified') or 0)} / 门槛 {int(item.get('required') or 0)}"
                    for item in unmet_gates if isinstance(item, dict)
                ],
                "assessment_source": "phase36_density",
                "density_assessment": {
                    **density,
                    "module_counts": density_counts,
                    "unmet_gates": unmet_gates,
                },
            })
        else:
            try:
                result["missing_modules"] = json.loads(result.get("missing_modules_json") or "[]")
                result["modules"] = json.loads(result.get("module_counts_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                result["missing_modules"] = []
                result["modules"] = {}
            result["assessment_source"] = "phase35_coverage"
        return result
