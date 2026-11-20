from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from green_model.skills import GreenProfileSkill, GreenTransitionReviewSkill, PostloanMonitorSkill


class GreenCreditAgent:
    """单Agent编排：只组织证据和待办，不自动审批或最终认定。"""

    def __init__(self, project_root: Path, case_root: Path, green_catalog: Path,
                 transition_rules: Path | None = None):
        self.root = Path(project_root)
        self.cases = CaseManager(case_root)
        self.review = GreenTransitionReviewSkill(self.root, green_catalog, transition_rules)
        self.rules = self.review.rules
        self.post = PostloanMonitorSkill(self.root)

    def start_case(self, case_id: str, project_path: Path, profile_path: Path | None = None) -> dict[str, Any]:
        project = json.loads(Path(project_path).read_text(encoding="utf-8-sig"))
        profile = json.loads(Path(profile_path).read_text(encoding="utf-8-sig")) if profile_path else {}
        profile_result = GreenProfileSkill.from_profile(profile)
        case_dir = self.cases._dir(case_id)
        review_path = case_dir / "midloan_review.raw.json"
        review = self.review.run_project_file(Path(project_path), review_path, profile_path)
        route, transition_review, midloan = review["routing"], review["transition_review"], review["midloan_review"]
        result = {
            "case_id": case_id, "status": "AWAITING_HUMAN_CONFIRMATION",
            "project": {k: project.get(k) for k in ("project_id", "project_name", "company_name")},
            "profile": profile_result, "routing": route, "transition_review": transition_review, "rule_pack": self.rules.status(),
            "midloan_review": midloan,
            "next_action": "由授权人员确认适用路径、目录条目、条件与证据后，方可建立贷后监测基线。",
            "automatic_approval": False,
        }
        self.cases.save_artifact(case_id, "case_review.json", result)
        return result

    def add_material(self, case_id: str, material: dict[str, Any]) -> dict[str, Any]:
        case_dir = self.cases._dir(case_id)
        review_path = case_dir / "case_review.json"
        if not review_path.exists():
            raise FileNotFoundError(f"原Case不存在：{case_id}")
        case = json.loads(review_path.read_text(encoding="utf-8-sig"))
        evidence = GreenProfileSkill.from_profile({"sentences": [material]})["evidence_items"][0]
        evidence["case_id"] = case_id
        case.setdefault("evidence", []).append(evidence)
        closed = []
        for task in case.get("pending_tasks", []):
            if task.get("claim_id") == evidence.get("claim_id") and task.get("status") == "OPEN":
                task["status"] = "CLOSED_BY_NEW_EVIDENCE"; closed.append(task.get("task_id"))
        case["status"] = "HUMAN_REVIEW" if evidence.get("conflict_status") != "none" else case.get("status")
        self.cases.save_artifact(case_id, "case_review.json", case)
        self.cases.append_audit(case_id, "material_bound_to_existing_case", {"evidence_id": evidence["evidence_id"], "closed_tasks": closed})
        return case

    def confirm_and_monitor(self, case_id: str, confirmation: dict[str, Any], postloan_case: dict[str, Any]) -> dict[str, Any]:
        if confirmation.get("confirmed_by") in (None, "") or confirmation.get("decision") in (None, ""):
            raise ValueError("必须记录人工确认人和人工决定，Agent不能自行越过确认门")
        self.cases.save_artifact(case_id, "human_confirmation.json", confirmation)
        result = self.post.run(postloan_case)
        self.cases.save_artifact(case_id, "postloan_monitor.json", result)
        return result
