"""Explicitly non-authoritative rule-pack fixtures.

These records are product fixtures, not regulatory assertions.  They use the
same shape as source-backed rules so a real package can replace them without a
schema or application-code change.
"""

from __future__ import annotations


INDUSTRIES = {
    "4415": {
        "name": "风力发电",
        "asset": "风电机组及集电线路",
        "output": "上网电量",
        "permit": "核准/备案及环境影响评价手续",
        "term": "可利用率",
    },
    "3110": {
        "name": "炼铁",
        "asset": "高炉及原料、送风系统",
        "output": "合格生铁产量",
        "permit": "环评、排污许可及能节审查手续",
        "term": "工序能耗",
    },
    "3011": {
        "name": "水泥制造",
        "asset": "熟料生产线及余热系统",
        "output": "合格熟料产量",
        "permit": "环评、排污许可及能节审查手续",
        "term": "熟料综合能耗",
    },
}


def pack_items(industry_code: str) -> list[dict[str, object]]:
    """Return a compact, full-module fixture package for one industry."""
    p = INDUSTRIES[industry_code]
    prefix = f"【示例规则·{p['name']}】"
    common = {"mock_notice": "仅用于系统功能演示，不是政策、标准或工行内部规则。"}
    return [
        {**common, "key": "process", "module": "process", "name": f"{prefix}建设与验收流程", "text": "核对立项、设计、采购、施工、调试和验收节点与材料是否一致。", "task": "现场核验", "evidence": ["project"]},
        {**common, "key": "equipment", "module": "equipment", "name": f"{prefix}核心设备边界", "text": f"对{p['asset']}的合同、发票、到货和验收记录进行交叉核对。", "task": "现场核验", "evidence": ["asset"]},
        {**common, "key": "route", "module": "route", "name": f"{prefix}技术路线一致性", "text": "可研、环评、合同和竣工材料中的技术路线应由人工核实是否发生实质变更。", "task": "规则核验", "evidence": ["project"]},
        {**common, "key": "standard", "module": "standard", "name": f"{prefix}审查口径", "text": "用于演示标准引用、适用性判断和原文追溯；不得作为真实准入依据。", "task": "规则核验", "evidence": ["project"]},
        {**common, "key": "indicator", "module": "indicator", "name": f"{prefix}{p['output']}完成率", "text": f"当期{p['output']}与同口径目标值之比，仅演示指标口径结构。", "task": "规则核验", "evidence": ["performance"]},
        {**common, "key": "threshold", "module": "threshold", "name": f"{prefix}演示偏离触发线", "text": "演示值：完成率低于85%时生成待复核任务；数值不是监管阈值。", "task": "规则核验", "evidence": ["performance"]},
        {**common, "key": "permit", "module": "permit", "name": f"{prefix}关键手续", "text": f"核对{p['permit']}是否齐全、在有效期内且项目边界一致。", "task": "补件", "evidence": ["permit"]},
        {**common, "key": "document", "module": "document", "name": f"{prefix}核心材料清单", "text": "可研/项目申请材料、审批手续、核心合同、发票与验收材料待人工核验。", "task": "补件", "evidence": ["project", "permit", "asset"]},
        {**common, "key": "evidence_project", "module": "evidence", "name": f"{prefix}项目边界证据", "text": "完整可研或项目申请材料，页码可定位，包含建设内容、投资和进度。", "task": "补件", "evidence": ["project"]},
        {**common, "key": "evidence_permit", "module": "evidence", "name": f"{prefix}许可手续证据", "text": "审批/备案/许可原件或可核验电子件，可识别主体、项目、日期与边界。", "task": "补件", "evidence": ["permit"]},
        {**common, "key": "evidence_asset", "module": "evidence", "name": f"{prefix}设备与资金证据", "text": "合同、发票、支付流水、到货单与验收记录可串联至同一设备。", "task": "补件", "evidence": ["asset"]},
        {**common, "key": "evidence_performance", "module": "evidence", "name": f"{prefix}运行实绩证据", "text": "经确认口径的运行台账、计量记录或第三方报告，包含期间和单位。", "task": "补件", "evidence": ["performance"]},
        {**common, "key": "risk", "module": "risk", "name": f"{prefix}资金用途与项目边界偏离", "text": f"设备合同、支付对象或验收范围与{p['asset']}边界不一致时，仅生成待核实风险线索。", "task": "冲突核实", "evidence": ["project", "asset"]},
        {**common, "key": "term", "module": "term", "name": f"{prefix}{p['term']}", "text": f"{p['term']}的演示术语卡：页面必须同时显示口径、期间、单位和证据。", "task": "规则核验", "evidence": ["performance"]},
        {**common, "key": "postloan_funds", "module": "postloan", "name": f"{prefix}资金用途匹配率", "text": "按基准、目标、实际三列核对贷款支付与合同、发票和设备边界；偏离后只生成人工复核任务。", "task": "贷后预警", "evidence": ["asset"], "indicator_category": "funds_use", "comparison_direction": "higher_is_better", "unit": "%", "statistical_scope": "本贷款项目累计支付口径"},
        {**common, "key": "postloan_progress", "module": "postloan", "name": f"{prefix}建设进度完成率", "text": "同一里程碑和统计期内比较计划进度与实际进度；偏离后只生成人工复核任务。", "task": "贷后预警", "evidence": ["project", "asset"], "indicator_category": "construction_progress", "comparison_direction": "higher_is_better", "unit": "%", "statistical_scope": "本贷款项目建设里程碑口径"},
        {**common, "key": "postloan_performance", "module": "postloan", "name": f"{prefix}贷后{p['output']}完成率", "text": "按基准、目标、实际三列同口径监测运行实绩；偏离后只生成人工复核任务。", "task": "贷后预警", "evidence": ["performance"], "indicator_category": "environmental_performance", "comparison_direction": "higher_is_better", "unit": "%", "statistical_scope": "本贷款项目年度累计口径"},
        {**common, "key": "postloan_compliance", "module": "postloan", "name": f"{prefix}未闭环合规事件数", "text": "同一报告期内记录处罚、许可到期和整改未闭环事件；增加后只生成人工复核任务。", "task": "贷后预警", "evidence": ["permit", "performance"], "indicator_category": "compliance_event", "comparison_direction": "lower_is_better", "unit": "件", "statistical_scope": "本贷款项目报告期口径"},
    ]
