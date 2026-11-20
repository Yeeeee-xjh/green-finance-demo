"""Versioned local registry for verified public rule packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from green_model.agent.domain.enums import SourceStatus
from green_model.agent.domain.models import RulePack, RuleVersion, SourceRecord, stable_id, utc_now
from green_model.agent.simplified_demo_rules import CEMENT, CEMENT_URL, GREEN, GREEN_URL, STEEL, STEEL_URL
from green_model.agent.storage import SQLiteRepository

from .parsing import file_sha256


@dataclass(frozen=True)
class RulePackSpec:
    key: str
    name: str
    industry: str
    region: str
    version: str
    issuer: str
    source_url: str
    source_candidates: tuple[Path, ...]
    rules: tuple[tuple[str, str, str, str, str, str], ...]


class RuleRegistry:
    def __init__(self, repository: SQLiteRepository, workspace_root: str | Path | None = None):
        self.repository = repository
        self.workspace_root = Path(workspace_root or Path(__file__).resolve().parents[2]).resolve()

    def specs(self) -> tuple[RulePackSpec, ...]:
        root = self.workspace_root
        return (
            RulePackSpec(
                "green-2025",
                "绿色金融支持项目目录",
                "跨行业",
                "全国",
                "2025年版",
                "中国人民银行等部门",
                GREEN_URL,
                (root / "data_policy" / "green_catlog_2025.pdf",),
                tuple(GREEN),
            ),
            RulePackSpec(
                "hebei-steel-2025",
                "河北省钢铁行业转型金融工作指引",
                "钢铁",
                "河北省（跨地区仅作参考回测）",
                "2025年版",
                "中国人民银行河北省分行等部门",
                STEEL_URL,
                (
                    root / "tmp" / "河北省钢铁行业转型金融工作指引_2025年版.pdf",
                    root / "outputs" / "材料核验依据包_v2_三层规则与Demo重评" / "01_政策原文" / "04_河北省钢铁行业转型金融工作指引_2025年版.pdf",
                ),
                tuple(STEEL),
            ),
            RulePackSpec(
                "jiangsu-building-2024",
                "江苏省转型金融支持经济活动目录（建材行业）",
                "水泥与建材",
                "江苏省（跨地区仅作参考回测）",
                "2024年版",
                "中国人民银行江苏省分行",
                CEMENT_URL,
                (root / "data_policy" / "jiangsu_building_materials_transition_2024.pdf",),
                tuple(CEMENT),
            ),
        )

    def sync(self) -> dict[str, int | list[str]]:
        counts = {"packs": 0, "rules": 0, "sources": 0}
        skipped: list[str] = []
        with self.repository.transaction() as uow:
            for spec in self.specs():
                path = next((candidate for candidate in spec.source_candidates if candidate.is_file()), None)
                if path is None:
                    skipped.append(f"{spec.name}：本地政策原件不存在")
                    continue
                source_hash = file_sha256(path)
                source_id = stable_id("src", f"official-rule:{spec.key}:{source_hash}")
                source = SourceRecord(
                    source_id=source_id,
                    source_type="official_policy_pdf",
                    title=f"{spec.name}（{spec.version}）",
                    issuer=spec.issuer,
                    source_url=spec.source_url,
                    accessed_at=utc_now(),
                    local_path=str(path),
                    sha256=source_hash,
                    status=SourceStatus.VERIFIED,
                    authority_level="official_public_document",
                )
                existing_source = uow.get("source_records", source_id)
                if not existing_source:
                    uow.add(source)
                    counts["sources"] += 1

                pack_id = stable_id("rulepack", f"{spec.key}:{source_hash}")
                pack = RulePack(
                    pack_id=pack_id,
                    pack_name=spec.name,
                    industry=spec.industry,
                    applicable_region=spec.region,
                    version_label=spec.version,
                    source_id=source_id,
                    effective_at=None,
                    expires_at=None,
                    status="active_reference",
                    content_hash=source_hash,
                )
                existing_pack = uow.get("rule_packs", pack_id)
                if not existing_pack:
                    uow.add(pack)
                    counts["packs"] += 1

                for sequence, row in enumerate(spec.rules, start=1):
                    rule_id, rule_name, requirement, basis, _url, evidence_requirement = row
                    content = {
                        "rule_id": rule_id,
                        "name": rule_name,
                        "requirement": requirement,
                        "basis": basis,
                        "evidence_requirement": evidence_requirement,
                        "pack": spec.name,
                        "version": spec.version,
                    }
                    content_hash = hashlib.sha256(
                        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    rule_version_id = stable_id("rulev", f"{spec.key}:{rule_id}:{content_hash}")
                    rule = RuleVersion(
                        rule_version_id=rule_version_id,
                        rule_id=rule_id,
                        rule_name=rule_name,
                        version_label=spec.version,
                        source_id=source_id,
                        published_at=None,
                        effective_at=None,
                        expires_at=None,
                        industry=spec.industry,
                        activity=rule_name,
                        applicable_stage="按项目活动与实施阶段适用",
                        requirement_text=requirement,
                        threshold_json={"source_basis": basis},
                        evidence_requirement=evidence_requirement,
                        is_bank_internal=False,
                        content_hash=content_hash,
                        status="active_reference",
                    )
                    existing_rule = uow.get("rule_versions", rule_version_id)
                    if not existing_rule:
                        uow.add(rule)
                        counts["rules"] += 1
                    uow.insert("rule_pack_entries", {
                        "pack_id": pack_id,
                        "rule_version_id": rule_version_id,
                        "sequence_no": sequence,
                    }, on_conflict="ignore")
        return {**counts, "skipped": skipped}
