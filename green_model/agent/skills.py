from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .evidence_engine import build_worklist, normalize_evidence


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GreenProfileSkill:
    """封装贷前结果。模型推理仍由原pipeline负责，本Skill统一证据输出契约。"""

    @staticmethod
    def from_profile(profile: dict[str, Any]) -> dict[str, Any]:
        evidence = normalize_evidence(profile.get("evidence_items") or profile.get("sentences"), profile.get("case_id"))
        return {
            "skill": "green_profile_skill", "schema_version": "1.0",
            "company_name": profile.get("company_name"), "document_id": profile.get("document_id"),
            "green_relevance": profile.get("green_relevance") or profile.get("pred_relevance"),
            "evidence_strength": profile.get("evidence_strength") or profile.get("pred_evidence_strength"),
            "claim_type": profile.get("claim_type") or profile.get("pred_claim_type"),
            "topic": profile.get("topic"), "model_confidence": profile.get("model_confidence"),
            "usable_fact_candidate": bool(profile.get("usable_fact_candidate", profile.get("evidence_strength") in {1, 2, "1", "2"})),
            "evidence_items": evidence,
            "human_review_required": True,
            "decision_boundary": "企业文本画像是项目核查线索，不等于具体贷款项目的绿色或转型认定。",
        }


class ProjectReviewSkill:
    def __init__(self, project_root: Path):
        self.root = project_root

    def run(self, project_path: Path, catalog_path: Path, output_path: Path,
            preloan_path: Path | None = None, config_path: Path | None = None) -> dict[str, Any]:
        script = self.root / "loan_review" / "review_project_gold.py"
        command = [sys.executable, str(script), "--project", str(project_path), "--catalog", str(catalog_path),
                   "--output", str(output_path), "--mode", "tfidf"]
        if preloan_path:
            command += ["--preloan-profile", str(preloan_path)]
        if config_path:
            command += ["--config", str(config_path)]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode:
            raise RuntimeError(completed.stderr or completed.stdout)
        result = json.loads(output_path.read_text(encoding="utf-8-sig"))
        result["skill"] = "project_review_skill"
        result["field_worklist"] = build_worklist(result)
        return result


class PostloanMonitorSkill:
    def __init__(self, project_root: Path):
        self.module = _load_module(project_root / "post_loan_monitoring" / "postloan_model.py", "agent_postloan_model")

    def run(self, case: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.module.analyze_case(case, config or self.module.DEFAULT_CONFIG)
        result["skill"] = "postloan_monitor_skill"
        return result
