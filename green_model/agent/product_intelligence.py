"""Product-level case intelligence for the competition workbench.

This module never invents a bank approval rule.  It organises existing Case
facts into an industry-first workflow and explains every computed attention
index as a review priority, not a probability of default or greenwashing.
"""
from __future__ import annotations

from copy import deepcopy


SOURCE_IDS = {
    "S01": "国家统计局《国民经济行业分类》GB/T 4754—2017及2019修改单",
    "S02": "中国人民银行《绿色金融支持项目目录（2025年版）》",
    "S03": "《银行业保险业绿色金融指引》",
    "S04": "《固定资产贷款管理办法》（2024年）",
    "S05": "《企业投资项目核准和备案管理条例》",
    "S06": "生态环境部《企业环境信息依法披露管理办法》及格式准则",
    "S07": "中国工商银行2025年度可持续发展报告（公开披露）",
    "S08": "工行公开的分阶段科创企业服务与评价实践",
    "S09": "工行公开的智能信贷与环境风险管理实践",
    "S10": "河北钢铁行业转型金融工作指引（公开参考规则）",
    "S11": "江苏省转型金融支持经济活动目录（建材行业公开参考规则）",
}


CASE_PROFILES = {
    "DEMO-A": {
        "industry": "风力发电",
        "industry_code": "D44 / 项目活动4.2.1",
        "industry_basis": "S01、S02",
        "enterprise_stage": "成熟期（公开上市公司）",
        "enterprise_stage_state": "已识别",
        "project_stage": "建设准备期",
        "project_stage_basis": "募投可研、环评文件及批复",
        "green_relation": "绿色目录活动候选",
        "case_state": "待人工复核",
        "glossary": ["风力发电设施建设和运营", "核准", "环评批复", "升压站", "送出线路", "设计发电量"],
        "risks": [
            ("绿色主张可信性", 22, "低", "项目活动与目录条目能够对应，当前不以企业形象替代项目事实。", "S02"),
            ("项目边界与融资用途", 68, "较高", "核准编号年份、总投资口径和配套工程范围存在跨文件差异。", "S04、S05"),
            ("行业技术与合规落实", 58, "中", "环评批复已有，但一项批复不能替代全部依法适用手续。", "S02、S03"),
            ("项目实施与资金执行", 38, "待核", "现有公开定增用途不能替代银行贷款用途与支付核验。", "S04"),
            ("绩效兑现与持续合规", 32, "待核", "当前为设计发电量，尚未进入实际绩效监测。", "S03、S06"),
        ],
        "signals": [
            ("跨文件一致性", "核准编号年份与投资口径存在差异", "核对变更批复、投资范围和配套工程边界", "较高", "G04", "S04、S05"),
            ("贷款用途边界", "公开募投资料说明定增用途，不等同贷款支付证据", "银行规则接入后核对合同、支付对象与项目清单", "待核", "BANK", "S04"),
        ],
    },
    "DEMO-B": {
        "industry": "钢铁冶炼及余气发电改造",
        "industry_code": "C31 / 公共转型规则参考",
        "industry_basis": "S01、S10",
        "enterprise_stage": "成熟期（大型钢铁企业）",
        "enterprise_stage_state": "已识别",
        "project_stage": "改造实施与回测期",
        "project_stage_basis": "公司债披露、项目报告及公开信息",
        "green_relation": "高碳行业低碳改造参考回测",
        "case_state": "多项待核实",
        "glossary": ["高炉煤气", "余气余热发电", "基准值", "目标值", "GB/T 1028", "GB/T 39091"],
        "risks": [
            ("绿色主张可信性", 48, "中", "融资名称与第三方报告存在，但不能替代项目实质核验。", "S03、S10"),
            ("项目边界与融资用途", 55, "中", "需把融资投向、具体机组和改造范围绑定到同一项目。", "S04、S10"),
            ("行业技术与合规落实", 72, "较高", "关键标准符合性和技术边界尚缺可定位证据。", "S10"),
            ("项目实施与资金执行", 70, "较高", "官网称投产，报告仍列在建，实施状态存在冲突。", "S04"),
            ("绩效兑现与持续合规", 64, "较高", "目标与实际口径尚不可比，需要统一边界和年度。", "S03、S10"),
        ],
        "signals": [
            ("技术标准证据", "GB/T 1028、GB/T 39091符合性尚未由原件支持", "补充原始检测/核查证据并定位页码", "较高", "R-TECH", "S10"),
            ("实施状态冲突", "官网投产与报告在建表述不一致", "核对机组、时间、阶段与统计口径", "较高", "R-STATUS", "S04"),
            ("绩效口径", "Target与Actual的范围、年度和单位尚未对齐", "统一基准期、系统边界、单位和计算公式", "较高", "R-BTA", "S03"),
        ],
    },
    "DEMO-C": {
        "industry": "水泥及建材",
        "industry_code": "C30 / 公共转型规则参考",
        "industry_basis": "S01、S11",
        "enterprise_stage": "成熟期（集团披露主体）",
        "enterprise_stage_state": "已识别",
        "project_stage": "无法判断（当前仅集团级披露）",
        "project_stage_basis": "缺少单一项目档案",
        "green_relation": "建材行业项目核验演示",
        "case_state": "项目级证据不足",
        "glossary": ["熟料替代", "替代燃料", "单位熟料综合能耗", "低碳水泥", "项目边界", "集团披露"],
        "risks": [
            ("绿色主张可信性", 62, "较高", "集团层面披露不能直接证明本次单一融资项目。", "S03、S06"),
            ("项目边界与融资用途", 76, "高", "缺少可唯一识别的项目、生产线、地点和融资用途。", "S04"),
            ("行业技术与合规落实", 66, "较高", "建材技术路径可参考，但当前缺少项目级参数。", "S11"),
            ("项目实施与资金执行", 58, "中", "无法从集团披露判断单一项目阶段和资金执行。", "S04"),
            ("绩效兑现与持续合规", 64, "较高", "企业总体绩效不能替代项目基准、目标与实绩。", "S03、S06"),
        ],
        "signals": [
            ("项目穿透", "当前材料主体为集团，缺少单项目身份", "补充项目名称、地点、生产线和建设内容", "高", "P-ID", "S04"),
            ("技术参数", "替代燃料、能效与产品指标未绑定单项目", "按项目和统计边界补充参数与证据", "较高", "P-TECH", "S11"),
        ],
    },
    "DEMO-D": {
        "industry": "风力发电",
        "industry_code": "D44 / 贷后监测案例",
        "industry_basis": "S01、S02",
        "enterprise_stage": "成熟期（公开发行主体）",
        "enterprise_stage_state": "已识别",
        "project_stage": "运营期",
        "project_stage_basis": "公开发行与运营披露",
        "green_relation": "绿色项目贷后绩效监测",
        "case_state": "贷后偏离复核中",
        "glossary": ["Baseline", "Target", "Actual", "持续偏离", "环境绩效", "发行期测算"],
        "risks": [
            ("绿色主张可信性", 28, "低", "项目类型与绿色活动仍可对应，偏离不等于属性失效。", "S02"),
            ("项目边界与融资用途", 26, "低", "当前异常来自运营绩效，并非已证明资金挪用。", "S04"),
            ("行业技术与合规落实", 30, "待核", "需结合运营期许可和合规事件持续监测。", "S03、S06"),
            ("项目实施与资金执行", 42, "中", "项目已运营，但需继续核对建设进度和资金闭环。", "S04"),
            ("绩效兑现与持续合规", 82, "高", "实际发电量较发行期测算偏低约17.35%，达到人工复核阈值。", "S03"),
        ],
        "signals": [
            ("绩效持续偏离", "Actual较发行期测算偏低约17.35%", "核对风资源、限电、设备可用率和统计口径", "高", "BTA-01", "S03"),
        ],
    },
}


GLOSSARY = {
    "风力发电设施建设和运营": ("目录活动名称，用来判断项目具体建设或运营内容是否落入对应活动边界。", "核对项目、容量、设备与建设内容，不把企业主营业务当作项目结论。", "S02"),
    "核准": ("政府对依法需要核准的投资项目作出的行政管理决定。", "核对编号、年份、建设主体、地点、规模和变更关系。", "S05"),
    "环评批复": ("生态环境主管部门对项目环境影响评价文件的审查意见。", "它能证明特定环境事项已审查，但不自动替代其他许可和银行授信条件。", "S03、S06"),
    "升压站": ("把风机输出电压升高后接入电网的配套设施。", "确认是否属于本次融资和审批范围，避免只核主机、不核配套工程。", "S04、S05"),
    "送出线路": ("将项目电力送至电网接入点的输电线路。", "核对建设主体、路径、批复和资金用途是否与项目一致。", "S04、S05"),
    "设计发电量": ("可研或设计阶段的预计值，不是投运后的实际环境绩效。", "贷后要用同口径Actual数据比较，不能把设计值当作已实现。", "S03"),
    "高炉煤气": ("炼铁过程中产生的可燃副产气体，可回收用于发电或供热。", "核对来源工序、回收范围、机组配置和替代能源量。", "S10"),
    "余气余热发电": ("回收工业过程中的可燃余气或余热用于发电的节能改造。", "需证明对应具体设备、工序和项目边界，而非只看项目名称。", "S02、S10"),
    "基准值": ("改造前或约定基准期的能耗、排放或产量数据。", "Baseline必须写清年度、边界、单位和数据来源。", "S03、S10"),
    "目标值": ("融资或转型方案约定在特定时间达到的量化结果。", "Target与Actual必须同口径，目标不能直接当作实绩。", "S03、S10"),
    "GB/T 1028": ("与工业余热术语、分类和相关技术表达有关的国家推荐性标准引用。", "系统只提示核对标准适用范围和符合性证据，不凭标准编号自动判定满足。", "S10"),
    "GB/T 39091": ("工业余热资源利用评价相关国家推荐性标准引用。", "核对评价对象、计算边界、输入数据和报告原件。", "S10"),
    "熟料替代": ("以其他胶凝材料减少水泥中高碳熟料的比例。", "核对产品类型、替代比例、质量标准与计算边界。", "S11"),
    "替代燃料": ("用符合要求的非传统燃料替代部分化石燃料。", "核对来源、热值、替代率、环保控制和实际消耗。", "S11"),
    "单位熟料综合能耗": ("生产单位熟料所消耗的综合能源，是建材行业常用能效指标。", "核对分母产量、能源折算、统计期和生产线范围。", "S11"),
    "低碳水泥": ("通过原料、燃料、熟料系数或工艺等降低全生命周期排放的水泥产品。", "不能只凭产品名称，需核对适用标准、产品参数和核查边界。", "S11"),
    "项目边界": ("本次融资实际覆盖的项目、设施、地点、阶段和资金用途范围。", "边界不清时，集团或企业事实不能直接替代项目事实。", "S04"),
    "集团披露": ("以企业集团为主体发布的总体经营或ESG信息。", "可作线索，但必须穿透到融资项目、生产线和证据页码。", "S03、S06"),
    "Baseline": ("贷中形成的已核验基准状态。", "保存基准年度、边界、单位和来源，作为贷后比较起点。", "S03、S04"),
    "Target": ("融资承诺或公开测算中的目标值。", "区分合同承诺、项目计划和发行期测算，不能混称。", "S03、S04"),
    "Actual": ("贷后报送或核验得到的实际值。", "必须与Target同口径，并保留原始数据和核验状态。", "S03、S06"),
    "持续偏离": ("实际值在连续期间偏离基准或目标的现象。", "偏离触发复核，不直接等于违规、处罚或违约。", "S03"),
    "环境绩效": ("项目在能耗、排放、资源利用等方面形成的实际结果。", "设计值、目标值和企业总量不能替代项目实绩。", "S03、S06"),
    "发行期测算": ("债券或融资披露时对项目未来产出作出的估计。", "它可作参考Target，但不是合同承诺，报告中必须注明口径。", "S03"),
}


STAGE_FOCUS = {
    "初创期": [
        "技术路线、中试或示范验证是否支持项目可行性",
        "核心团队、知识产权与外部技术依赖是否说清",
        "审批许可路径和关键里程碑是否可执行",
        "融资用途是否与研发、设备和示范项目逐项绑定",
    ],
    "成长期": [
        "订单、产能爬坡与回款能否支撑项目实施节奏",
        "新增产线、设备采购与现金流缺口是否对应",
        "单位能耗、产量和环境绩效口径是否稳定可比",
        "快速扩张是否带来许可、施工与供应链风险",
    ],
    "成熟期": [
        "本次项目是否与企业存量产线和常规经营清晰分离",
        "资本开支、资金用途与支付对象是否形成闭环",
        "历史实绩、申报目标与贷后Actual是否同口径",
        "集团披露是否能够穿透到项目、生产线和设施",
    ],
    "待人工确认": [
        "先依据成立时间、经营规模、产业化状态和公开材料确认阶段",
        "阶段未确认前不自动套用差异化核验重点",
    ],
}


def _default_profile(case_id: str, view: dict) -> dict:
    overview = view.get("overview", {})
    return {
        "industry": overview.get("industry") or "待识别行业",
        "industry_code": "待依据GB/T 4754确认",
        "industry_basis": "S01",
        "enterprise_stage": "待人工确认",
        "enterprise_stage_state": "证据不足",
        "project_stage": "待人工确认",
        "project_stage_basis": "需依据项目材料识别",
        "green_relation": "待根据项目活动和融资用途判断",
        "case_state": overview.get("status") or "待分析",
        "glossary": ["项目边界", "Baseline", "Target", "Actual"],
        "risks": [
            ("绿色主张可信性", 35, "待核", "当前材料不足，不能把未计算理解为零风险。", "S03"),
            ("项目边界与融资用途", 45, "待核", "需确认单一项目、融资对象和资金用途。", "S04"),
            ("行业技术与合规落实", 40, "待核", "需按识别后的行业规则和项目阶段逐项核对。", "S01、S03"),
            ("项目实施与资金执行", 35, "待核", "需接入进度和支付证据。", "S04"),
            ("绩效兑现与持续合规", 35, "待核", "需建立可比的Baseline、Target和Actual。", "S03"),
        ],
        "signals": [("项目识别", "行业、发展阶段和项目边界尚未确认", "由客户经理确认后调用行业规则包", "待核", "CASE", "S01、S04")],
    }


def build_product_view(case_id: str, view: dict) -> dict:
    profile = deepcopy(CASE_PROFILES.get(case_id) or _default_profile(case_id, view))
    dimensions = [
        {"name": name, "score": score, "level": level, "summary": summary, "source_ids": sources}
        for name, score, level, summary, sources in profile.pop("risks")
    ]
    signals = [
        {"title": title, "finding": finding, "action": action, "level": level, "rule_id": rule_id, "source_ids": sources}
        for title, finding, action, level, rule_id, sources in profile.pop("signals")
    ]
    missing = view.get("missing", [])
    bta = view.get("bta", [])
    steps = [
        ("01", "材料解析", "已完成" if view.get("profile") else "待处理", "提取项目事实、来源文件与页码"),
        ("02", "行业与阶段识别", "待确认" if profile["enterprise_stage_state"] == "证据不足" else "已完成", f'{profile["industry"]} / {profile["enterprise_stage"]} / {profile["project_stage"]}'),
        ("03", "风险扫描", "已完成", f"形成{len(signals)}项重点风险线索"),
        ("04", "行业辅助核验", "已完成" if (view.get("rule_assessments") or view.get("conditions")) else "待处理", "逐项绑定规则、事实、证据与状态"),
        ("05", "人工确认门", "待处理" if (missing or signals) else "已完成", f"{len(view.get('human_checks', []))}项建议人工重点核验"),
        ("06", "贷后续办", "监测中" if bta else "未启动", "继承贷中基准，持续接收Actual数据"),
    ]
    glossary = []
    for term in profile.pop("glossary"):
        plain, check, source = GLOSSARY.get(term, ("当前知识库暂无定义。", "转人工确认。", "—"))
        glossary.append({"term": term, "plain": plain, "case_check": check, "source_ids": source})
    status_counts = {"满足": 0, "待核实": 0, "冲突": 0, "不适用": 0, "无法判断": 0}
    rows = view.get("rule_assessments") or view.get("green_rules") or view.get("conditions") or []
    for item in rows:
        state = str(item.get("status", "")).lower()
        if state in {"met", "verified", "proven"}: status_counts["满足"] += 1
        elif state in {"evidence_conflict", "conflict"}: status_counts["冲突"] += 1
        elif state in {"not_applicable", "n/a", "na"}: status_counts["不适用"] += 1
        elif state in {"cannot_determine", "unknown", "not_available"}: status_counts["无法判断"] += 1
        else: status_counts["待核实"] += 1
    stage_key = next((key for key in ("初创期", "成长期", "成熟期") if key in profile["enterprise_stage"]), "待人工确认")
    profile.update({
        "risk_dimensions": dimensions,
        "risk_signals": signals,
        "agent_steps": [{"no": n, "name": name, "status": status, "detail": detail} for n, name, status, detail in steps],
        "glossary": glossary,
        "status_counts": status_counts,
        "attention_score": max(d["score"] for d in dimensions),
        "attention_label": "高" if max(d["score"] for d in dimensions) >= 75 else "较高" if max(d["score"] for d in dimensions) >= 60 else "中" if max(d["score"] for d in dimensions) >= 40 else "低",
        "score_note": "关注指数由当前证据状态映射，仅用于安排复核顺序；不是违约概率、合规概率或漂绿概率。",
        "bank_rule_state": "无法判断（工行内部规则未接入）",
        "bank_rule_note": "公开监管与行业规则可辅助核验；具体准入、额度、尽调、审批和贷后要求以经办行有效制度为准。",
        "stage_focus": STAGE_FOCUS[stage_key],
        "stage_focus_note": "成长阶段重点是本项目的辅助审查设计，参考工行公开的分阶段服务理念；不是工行内部评级或统一授信阈值。",
    })
    return profile
