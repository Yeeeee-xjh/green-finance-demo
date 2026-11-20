from __future__ import annotations
import json,tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any
from green_model.agent.rule_pack import RulePack
from green_model.agent.skills import ProjectReviewSkill
from .schema import ReviewInput
class GreenTransitionReviewSkill:
    """统一编排绿色目录召回、转型规则、条件与Evidence核验。"""
    name="green_transition_review_skill"
    def __init__(self,project_root:Path,green_catalog:Path,transition_rules:Path|None=None):
        self.root=Path(project_root); self.rules=RulePack(green_catalog,transition_rules); self.engine=ProjectReviewSkill(self.root)
    def run_project_file(self,project_path:Path,output_path:Path,profile_path:Path|None=None)->dict[str,Any]:
        project=json.loads(Path(project_path).read_text(encoding="utf-8-sig")); route=self.rules.route(project); transition=self.rules.review_transition(project,route)
        mid=self.engine.run(Path(project_path),self.rules.green_catalog,Path(output_path),profile_path)
        return self._output(route,transition,mid)
    def run(self,payload:ReviewInput|dict[str,Any])->dict[str,Any]:
        data=asdict(payload) if isinstance(payload,ReviewInput) else dict(payload); obj=ReviewInput(**data); obj.validate(); project=dict(obj.project); project.update({"project_id":obj.case_id,"project_description":obj.project_description,"industry":obj.industry,"evidence_items":obj.evidence})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"project.json"; o=Path(d)/"review.json"; p.write_text(json.dumps(project,ensure_ascii=False),encoding="utf-8"); return self.run_project_file(p,o)
    def _output(self,route,transition,mid):
        cond=mid.get("condition_review",{}).get("conditions",[]); ev=mid.get("evidence_review",{}); conflicts=[x for x in ev.get("items",[]) if x.get("status")=="conflict"]
        return {"skill":self.name,"green_route":route.get("green_route"),"transition_route":route.get("transition_route"),"matched_rules":transition.get("matched_rules",[]),"conditions":cond,"evidence_status":ev.get("evidence_status"),"missing_conditions":[x for x in cond if x.get("status") in {"unknown","not_met"}],"conflicts":conflicts,"review_status":mid.get("review_label"),"human_review_required":bool(mid.get("manual_review_required") or route.get("human_confirmation_required")),"routing":route,"transition_review":transition,"midloan_review":mid}
