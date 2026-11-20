from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RulePack:
    def __init__(self, green_catalog: Path, transition_rules: Path | None = None):
        self.green_catalog = Path(green_catalog)
        self.transition_rules = Path(transition_rules) if transition_rules else None

    def status(self) -> dict[str, Any]:
        green = json.loads(self.green_catalog.read_text(encoding="utf-8-sig"))
        return {
            "green": {"available": True, "source": str(self.green_catalog), "entries": len(green)},
            "transition": {
                "available": bool(self.transition_rules and self.transition_rules.exists()),
                "source": str(self.transition_rules) if self.transition_rules else None,
                "degradation": None if self.transition_rules and self.transition_rules.exists()
                else "转型规则尚未结构化：只生成转型候选和补证要求，不作符合性认定",
            },
        }

    def route(self, project: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(project.get(k, "")) for k in ("project_name", "project_description", "fund_use"))
        industry = str(project.get("industry", "")) + str(project.get("industry_name", ""))
        steel = any(term in text + industry for term in ("钢铁", "炼钢", "炼铁", "高炉", "转炉"))
        cement = any(term in text + industry for term in ("水泥", "熟料", "建材"))
        substantial = any(term in text for term in ("技改", "节能", "降碳", "资源循环", "工艺升级", "能效提升", "减排目标", "余热", "替代燃料"))
        transition = (steel or cement) and substantial
        return {
            "green_route": True,
            "transition_route": transition,
            "transition_industry": "steel" if steel else "cement_building_materials" if cement else None,
            "route_reason": "检测到高碳行业或转型技术线索，绿色与转型双路并行" if transition else "先进入绿色项目目录审查",
            "human_confirmation_required": True,
        }

    def review_transition(self, project: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        if not route.get("transition_route"):
            return {"status": "NOT_APPLICABLE", "candidate": False, "matched_rules": [],
                    "notice": "当前仅支持钢铁及建材/水泥两个示范行业，不强行分类。"}
        if not self.transition_rules or not self.transition_rules.exists():
            return {"status": "RULE_PACK_UNAVAILABLE", "candidate": True, "matched_rules": [],
                    "result": "转型融资候选 / 待进一步核验"}
        payload = json.loads(self.transition_rules.read_text(encoding="utf-8-sig"))
        industry = route.get("transition_industry")
        rules = [x for x in payload.get("rules", []) if x.get("industry") == industry]
        text = " ".join(str(project.get(k, "")) for k in ("project_name", "project_description", "fund_use"))
        matched = [r for r in rules if any(k in text for k in r.get("keywords", []))]
        return {"status": "CANDIDATE_REVIEW" if matched else "INSUFFICIENT_MATCH",
                "candidate": bool(matched), "matched_rules": matched,
                "result": "转型融资候选 / 待进一步核验" if matched else "暂未形成可靠转型候选，转人工判断",
                "notice": "规则匹配不是转型认定；条件、证据、实际绩效均需持续核验。"}
