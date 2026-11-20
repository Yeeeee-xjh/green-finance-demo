from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
from green_model.agent.skills import PostloanMonitorSkill as _Engine
from green_model.agent.structured_data_adapter import baseline_target_actual
from .schema import PostloanInput
class PostloanMonitorSkill:
    name="postloan_monitor_skill"; weights={"fund_use":.30,"project_progress":.25,"environmental_performance":.25,"compliance_events":.20}
    def __init__(self,project_root:Path): self.engine=_Engine(Path(project_root))
    def run(self,payload:PostloanInput|dict[str,Any],config=None)->dict[str,Any]:
        if isinstance(payload,dict) and "monitoring_periods" in payload: return self.engine.run(payload,config)
        data=asdict(payload) if isinstance(payload,PostloanInput) else dict(payload); obj=PostloanInput(**data); obj.validate(); bta=[baseline_target_actual(x) for x in obj.metrics]
        deviation=min((x["deviation"] for x in bta if x["deviation"] is not None),default=None); review=any(x["manual_attention"] for x in bta) or bool(obj.events)
        return {"skill":self.name,"weights":self.weights,"four_axis_status":{"fund_use":"待核验","project_progress":"需复核" if review else "正常","environmental_performance":"偏离" if deviation is not None and deviation<-.15 else "正常","compliance_events":"有事件" if obj.events else "无已报事件"},"baseline_target_actual":bta,"deviation":deviation,"confidence":min((x.get("confidence") or 0 for x in bta),default=0),"review_required":review,"tracking_items":[x["metric_name"] for x in bta if x["manual_attention"]]}
