from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .document_adapter import project_from_material
from .orchestrator import GreenCreditAgent
from .structured_data_adapter import load_structured


class Workbench:
    def __init__(self):
        self.cfg = load_config(); self.agent = GreenCreditAgent(self.cfg["project_root"], self.cfg["case_storage"], self.cfg["green_catalog"], self.cfg["transition_rules"])

    def case_ids(self) -> list[str]:
        return sorted(p.name for p in self.cfg["case_storage"].glob("*") if p.is_dir())

    def case(self, case_id: str) -> dict[str, Any]:
        p = self.cfg["case_storage"] / case_id / "case_review.json"
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}

    def audit(self, case_id: str, event: str, details: dict[str, Any]) -> None: self.agent.cases.append_audit(case_id, event, details)

    def analyse(self, case_id: str, company: str, project: str, industry: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
        case_dir = self.agent.cases._dir(case_id); payload = project_from_material(case_id, company, project, industry, materials)
        project_path = case_dir / "project.generated.json"; project_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.audit(case_id, "case_created_or_reanalysed", {"materials": len(materials), "at": datetime.now(timezone.utc).isoformat()})
        return self.agent.start_case(case_id, project_path)

    def update_actuals(self, case_id: str, path: Path) -> dict[str, Any]:
        rows = load_structured(path); current = self.case(case_id)
        template = self.cfg["project_root"] / "post_loan_monitoring/data/postloan_case.example.json"
        post = json.loads(template.read_text(encoding="utf-8")); post.update({k: current.get("project", {}).get(k) for k in ("project_id", "project_name", "company_name")})
        period = post["monitoring_periods"][-1]; period["evidence_items"].append({"evidence_id": "ACTUAL-UPLOAD", "name": path.name, "source": "用户上传", "date": datetime.now().date().isoformat(), "verification_status": "unverified", "supports": ["environmental_kpis"]})
        for row in rows:
            name = str(row.get("metric_name", "")); actual = row.get("actual_value")
            if actual is not None: period["environmental_kpis"][name] = actual
        result = self.agent.post.run(post); self.agent.cases.save_artifact(case_id, "postloan_monitor.json", result); self.audit(case_id, "actual_data_processed", {"file": path.name, "metrics": len(rows)})
        return result

    def chat(self, case_id: str, message: str) -> str:
        from .ui_presenter import build_view, canonical_case_id
        display_id = canonical_case_id(case_id)
        if display_id in {"DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D"}:
            storage_id = "DEMO-P01" if display_id == "DEMO-A" else display_id
            view = build_view(display_id, self.case(storage_id), self.cfg["case_storage"])
            lower = message.lower()
            scope_prefix = "本轮为公开材料的指标示范核验，不评价历史发行合规，不替代银行授信审批。"
            if any(word in message for word in ("河北", "江苏", "地域", "规则", "依据", "标准来源")):
                references = "参照河北钢铁2025指引核验主要工序碳排、能效及企业整体转型方案。" if display_id == "DEMO-B" else "参照江苏建材2024目录核验具体燃料路径及其明文指标。" if display_id == "DEMO-C" else "按2025绿色目录4.2.1核验风电建设或运营活动，该条未列统一数值阈值。"
                return scope_prefix + references + "地方规则允许跨地区参考回测，不因地域不同停止演示；结果不等于所在地政策认定。矩阵分别展示政策要求、项目内容、证据定位和结果；证据示例不是固定必交清单。"
            if any(word in lower for word in ("召回", "语义", "概率", "tfidf", "tf-idf", "匹配")):
                return scope_prefix + ("召回是找可能相关的目录条目；Demo A的真实排序分不是合规概率或通过率，行业关联与条件满足分别判断。" if display_id == "DEMO-A" else "当前目录参考候选由公开材料人工定位，未补造排序分；名称相关不等于活动和技术条件均满足。")
            if any(word in message for word in ("第三方", "评估报告")):
                return scope_prefix + ("4.2.1未将第三方评估报告列为硬条件，不由模型自行增加。" if display_id in {"DEMO-A", "DEMO-D"} else "已有披露证明项目评估报告曾存在；河北2025参考规则另要求企业整体转型方案的第三方评估，项目报告存在不自动证明整体方案已评估。" if display_id == "DEMO-B" else "江苏建材具体条目决定技术指标；未确认的银行、产品或合同要求不提前设为第三方报告缺项。")
            if any(word in lower for word in ("进度", "贷后", "actual", "实际", "目标")):
                return scope_prefix + view["project_check"]["performance_basis"]
            if any(word in message for word in ("缺", "补件", "材料")):
                tasks = "；".join(x["name"] for x in view["missing"])
                return scope_prefix + f"当前待核实指标：{tasks or '无直接补充任务'}。这不是固定材料清单；一份证据可支持多个指标。银行内部标准未接入，无法判断授信或内部材料完整性。"
            return view["summary"] + " 所有结果按指标与证据分别说明；待核实不等于不满足，补充材料登记也不自动变为满足。"
        case = self.case(case_id); lower = message.lower(); review = case.get("midloan_review", {}); work = review.get("field_worklist", {})
        if any(word in message for word in ("缺", "补件", "材料")):
            items = work.get("supplementation_list", []); return "当前待补材料：" + ("；".join(str(x.get("material_type", x)) for x in items) if items else "暂无系统生成的补件；仍请人工核验现有证据。")
        if any(word in message for word in ("进度", "贷后", "actual", "实际")):
            return "可在“贷后监测”上传 CSV/Excel/JSON Actual 数据。系统将调用 postloan_monitor_skill 更新四轴风险与偏离。"
        return f"当前 Case 为 {case.get('project', {}).get('project_name', case_id)}。绿色初审建议：{review.get('review_label', '等待材料分析')}；路径：{case.get('routing', {}).get('route_reason', '待判断')}。我只解释并编排专业 Skill，最终认定需人工确认。"
