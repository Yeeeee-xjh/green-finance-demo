from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any


STATUS_LABELS = {
    "AWAITING_HUMAN_CONFIRMATION": "待人工确认",
    "HUMAN_REVIEW": "人工复核中",
    "CANDIDATE_REVIEW": "待补关键证据",
    "NOT_APPLICABLE": "不适用",
    "verified": "已核验",
    "missing": "缺失",
    "unknown": "待核验",
    "met": "已满足",
    "not_met": "未满足",
    "proven": "已证明",
    "pending_evidence": "待补证",
    "not_applicable": "不适用",
    "cannot_determine": "无法判定",
    "evidence_conflict": "证据冲突",
    "activity_match": "活动相符",
    "candidate_only": "备选候选",
}

POLICY_NAMES = {
    "steel": "《河北省钢铁行业转型金融工作指引（2025年版）》（参考规则回测）",
    "cement_building_materials": "《江苏省转型金融支持经济活动目录（建材行业）（2024年版）》",
}

DEMO_LABELS = {
    "DEMO-A": "Demo A｜真实公开绿色项目",
    "DEMO-B": "Demo B｜钢铁余气发电·河北参考回测",
    "DEMO-C": "Demo C｜水泥集团组合·江苏参考回测",
    "DEMO-D": "Demo D｜真实公开贷后绩效偏离案例",
}


def provenance(case_id: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "demos" / "demo_provenance.json"
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8-sig")).get(case_id, {})
    if case_id == "DEMO-B" and result:
        result["rule_sources"] = "绿色路线：2025目录1.3.4（第25页）。转型路线：参照河北钢铁2025指引进行跨地区示范回测，不作四川政策认定，不评价2022发行合规；旧版规则不参与当前回测。"
    if case_id == "DEMO-C" and result:
        result["rule_sources"] = "绿色目录具体活动候选；江苏建材2024目录化石燃料替代等路径作为跨地区参考规则。集团公开指标不替代单一生产线、项目或当地融资认定。"
    return result


def canonical_case_id(case_id: str) -> str:
    return "DEMO-A" if case_id == "DEMO-P01" else case_id


def reassessment(case_id: str) -> dict[str, Any]:
    case_id = canonical_case_id(case_id)
    if case_id not in {"DEMO-A", "DEMO-B"}:
        return {}
    path = Path(__file__).resolve().parent / "demos" / "demo_ab_policy_reassessment.json"
    if not path.exists():
        raise FileNotFoundError("Demo逐规则重评文件缺失，不能回退到旧初审结论。")
    result = json.loads(path.read_text(encoding="utf-8-sig")).get(case_id)
    if not result or not result.get("rules"):
        raise ValueError(f"{case_id}逐规则重评未加载，不能判断通过或完整性。")
    return result


def official_candidates(candidates: list[dict[str, Any]]) -> None:
    path = Path(__file__).resolve().parents[1] / "loan_review" / "data" / "catalog_entries_2025_full.json"
    by_code = {row["catalog_code"]: row for row in json.loads(path.read_text(encoding="utf-8-sig"))}
    for candidate in candidates:
        candidate.pop("required_evidence", None)
        source = by_code.get(candidate.get("catalog_code"))
        if source:
            for key in ("project_name", "level3", "conditions", "industry_codes", "industry_name", "source_pages", "remarks"):
                if key in source:
                    candidate[key] = copy.deepcopy(source[key])


def _first_evidence(item: dict[str, Any]) -> dict[str, Any]:
    rows = item.get("matched_evidence") or []
    return rows[0] if rows else {}


def _pct(value: Any) -> str:
    try:
        number = float(value)
        if number <= 1:
            number *= 100
        return f"{number:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _project_fact(case: dict[str, Any]) -> list[dict[str, Any]]:
    project = case.get("project", {})
    name = project.get("project_name")
    if not name:
        return []
    return [{
        "fact": name,
        "green_relevance": "未计算",
        "strength": "项目级线索",
        "claim_type": "项目名称/申报事实",
        "included": "是",
        "excerpt": name,
        "source": "Case 项目基本信息",
        "page": "—",
        "confidence": "—",
        "reason": "项目名称可用于目录候选召回，但不能替代材料证据。",
    }]


def profile_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    profile = case.get("profile", {})
    rows = []
    for item in profile.get("evidence_items", []):
        confidence = item.get("confidence", profile.get("model_confidence"))
        strength = item.get("evidence_strength") or profile.get("evidence_strength") or (2 if item.get("verification_status") == "verified" else None)
        included = bool(item.get("usable_fact_candidate", profile.get("usable_fact_candidate")))
        rows.append({
            "fact": item.get("raw_excerpt") or item.get("name") or "未命名披露事实",
            "green_relevance": _pct(item.get("green_relevance") or profile.get("green_relevance") or confidence),
            "strength": {0: "弱", 1: "中", 2: "强", "0": "弱", "1": "中", "2": "强"}.get(strength, strength or "待核验"),
            "claim_type": item.get("claim_type") or profile.get("claim_type") or ("事实披露" if item.get("verification_status") == "verified" else "未分类"),
            "included": "是" if included else "否",
            "excerpt": item.get("raw_excerpt") or "—",
            "source": item.get("source_document") or item.get("source") or "—",
            "page": item.get("page") or item.get("location") or "—",
            "confidence": _pct(confidence),
            "reason": "证据强度足以形成核验线索。" if included else "仅作文本线索，证据强度不足以进入实质核验。",
        })
    return rows or _project_fact(case)


def missing_materials(case: dict[str, Any], *, optional: bool = False) -> list[dict[str, Any]]:
    rule_rows = case.get("rule_assessments") or []
    if rule_rows:
        rows = []
        for item in rule_rows:
            if (item.get("task_scope") == "alternative_only") != optional:
                continue
            if item.get("status") not in {"pending_evidence", "evidence_conflict"}:
                continue
            next_evidence = item.get("next_evidence")
            if not next_evidence:
                continue
            layer = item.get("layer", "模型")
            category = "备选路线可选补证" if optional else "现行目录回测待补证" if "回测" in layer else "政策明文待补证" if "政策" in layer else "银行规则未接入" if "银行" in layer else "模型证据质量"
            if case.get("_simplified_rules"):
                category = "地方参考指标待核实" if item.get("route") == "transition" else "绿色路线指标待核实"
            rows.append({
                "name": item.get("claim") or item.get("rule_id"),
                "why": f"{item.get('reason', '')} 下一步：{next_evidence}".strip(),
                "rule": item.get("rule_id", "—"),
                "type": category,
                "blocker": item.get("status") == "evidence_conflict",
                "status": item.get("status"),
            })
        return rows
    if optional:
        return []
    mid = case.get("midloan_review", {})
    industry = case.get("routing", {}).get("transition_industry")
    policy = POLICY_NAMES.get(industry, "《绿色金融支持项目目录（2025年版）》及适用技术条件")
    rows = []
    for i, item in enumerate(mid.get("evidence_review", {}).get("items", []), 1):
        if item.get("status") == "verified":
            continue
        name = item.get("required_type") or item.get("canonical_type") or f"材料{i}"
        basis_type = "R1" if any(k in name for k in ("技术", "标准", "能耗", "碳排", "基准")) else "R2"
        rows.append({
            "name": name,
            "why": item.get("description") or "用于完成目录条件与项目事实之间的证据闭环。",
            "rule": policy,
            "type": basis_type,
            "blocker": True,
        })
    return rows


def human_checks(case: dict[str, Any], is_demo_d: bool = False) -> list[dict[str, str]]:
    key = case.get("_reassessment_key")
    if key == "DEMO-A":
        return [
            {"check": "核对两个项目核准编号及变更关系", "why": "2025/45与2026/6不能由模型自行解释。"},
            {"check": "核对5.5亿元与4.96亿元投资口径", "why": "确认是阶段、范围还是项目变更差异。"},
            {"check": "确认本次银行融资范围与配套工程许可", "why": "定增用途不替代银行贷款用途，且现环评不含部分配套工程。"},
            {"check": "按经办行清单核验外部风险与授信材料", "why": "外部数据和工行内部规则尚未接入。"},
        ]
    if key == "DEMO-B":
        return [
            {"check": "核验GB/T 1028、GB/T 39091符合性", "why": "这是目录1.3.4明文附加条件，现有设计参数不能自动替代。"},
            {"check": "拆清一期、二期与债券募投范围", "why": "投产/在建表述及Target/Actual边界目前不可直接比较。"},
            {"check": "调取第三方评估原件与核算底稿", "why": "现材料已证明报告存在，但原件未入库。"},
            {"check": "确认四川及具体融资产品的转型规则", "why": "河北规则不适用于四川，工行规则也尚未接入。"},
        ]
    industry = case.get("routing", {}).get("transition_industry")
    if is_demo_d:
        return [
            {"check": "核对上网电量、结算凭证与减排测算底稿", "why": "确认2024年度实际值与第三方折算口径一致。"},
            {"check": "核查设备可用率、风资源和停机记录", "why": "判断实际减排低于发行期测算的原因。"},
            {"check": "复核发行期测算与年度实际值可比性", "why": "24.61万吨是公开测算基准，不应误称为合同承诺目标。"},
        ]
    common = [
        {"check": "实际设备是否安装并投运", "why": "文本和合同不能替代现场实施事实。"},
        {"check": "设备型号是否与申报材料一致", "why": "避免申报技术参数与实际配置不一致。"},
        {"check": "计量数据是否可追溯", "why": "确保能耗、减排和产量数据具备原始凭证。"},
    ]
    if industry == "steel":
        common.insert(2, {"check": "老旧高耗能设备是否退出", "why": "防止新增节能设备与原有高耗能产能并行造成碳锁定。"})
    elif industry == "cement_building_materials":
        common.insert(2, {"check": "替代燃料种类、比例与喂料系统", "why": "确认申报的替代燃料路径已真实落地且口径一致。"})
    return common


def case_overview(case_id: str, case: dict[str, Any], case_dir: Path) -> dict[str, str]:
    project = case.get("project", {})
    routing = case.get("routing", {})
    industry_code = routing.get("transition_industry")
    industry = {"steel": "钢铁", "cement_building_materials": "水泥/建材"}.get(industry_code, project.get("industry") or "清洁能源")
    assessment = case.get("_reassessment") or {}
    if assessment:
        route = "GREEN活动映射｜非定增认定" if case_id == "DEMO-A" else "GREEN现行目录回测｜历史转型融资披露"
        status = assessment.get("main_status", "待人工复核")
    elif case_id == "DEMO-D":
        route, status = "GREEN ROUTE｜真实贷后绩效复核", "实际减排低于发行期测算"
    elif routing.get("transition_route"):
        route, status = "GREEN + TRANSITION ROUTE", "待补关键证据"
    else:
        route = "GREEN ROUTE"
        status = "建议通过绿色属性初审" if case.get("midloan_review", {}).get("review_suggestion") == "A" else STATUS_LABELS.get(case.get("status"), "待核验")
    timestamps = [p.stat().st_mtime for p in case_dir.glob("*") if p.is_file()] if case_dir.exists() else []
    updated = datetime.fromtimestamp(max(timestamps)).strftime("%Y-%m-%d %H:%M") if timestamps else "—"
    return {
        "company": project.get("company_name") or "—",
        "project": project.get("project_name") or "—",
        "industry": industry,
        "route": route,
        "status": status,
        "updated": updated,
    }


def business_summary(case_id: str, case: dict[str, Any], missing: list[dict[str, Any]]) -> str:
    assessment = case.get("_reassessment") or {}
    if assessment:
        return assessment.get("summary", "逐条规则重评完成，等待人工复核。")
    overview = case.get("routing", {})
    industry = overview.get("transition_industry")
    if case_id == "DEMO-D":
        return "22吉电G1风电项目组合的绿色属性与资金用途已有公开材料支持；2024年按募集资金占比折算的实际年减排CO2为20.34万吨，低于发行期第三方测算的24.61万吨约17.35%。类别匹配仍成立，但绩效偏离触发人工复核。"
    if case_id == "DEMO-B":
        return "22攀钢02的100MW余热余能利用发电工程为真实公开募投项目：募集说明书披露1亿元债券资金投入本项目，项目回收高炉、转炉和焦炉煤气并采用高效发电机组。2022年度受托管理报告转引已运营一期部分的节煤、减排实绩；该实绩标记为PUBLIC_DERIVED，不能与全项目设计目标直接比较。"
    if industry == "steel":
        return "系统召回余热利用、节能降碳改造等绿色目录候选；钢铁转型规则须先确认地区、版本和融资产品的适用性，不能自动套用河北规则或生成固定材料清单。目录条件、证据和银行内部清单仍需分别核验。"
    if industry == "cement_building_materials":
        return f"系统识别该项目属于水泥/建材行业低碳转型活动，并匹配江苏建材转型金融目录中的替代燃料路径。当前有{len(missing)}项材料待补或待核验，重点补充替代燃料比例、基准期能耗和GB/GB-T标准符合性材料。"
    label = case.get("midloan_review", {}).get("review_label", "等待核验")
    return f"系统依据项目材料完成绿色目录召回、技术条件和证据链核验。当前建议为“{label}”；项目不强行进入转型路线，最终信贷判断仍由授权人员确认。"


def demo_d_case(case_storage: Path) -> dict[str, Any]:
    path = case_storage / "DEMO-D" / "bta_result.json"
    metrics = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else []
    return {
        "case_id": "DEMO-D",
        "status": "HUMAN_REVIEW",
        "project": {"project_id": "22吉电G1", "project_name": "22吉电G1风力发电项目组合｜真实贷后绩效偏离复核", "company_name": "吉林电力股份有限公司", "industry": "风力发电"},
        "profile": {"skill": "green_profile_skill", "evidence_items": []},
        "routing": {"green_route": True, "transition_route": False, "route_reason": "项目类别匹配成立，进入实际环境绩效复核"},
        "midloan_review": {
            "review_suggestion": "D", "review_label": "绿色项目成立，但实际环境绩效低于发行期测算",
            "catalog_retrieval": {"state": "reliable_candidate", "top_candidates": [{"catalog_code": "4.2.1", "project_name": "风力发电设施建设和运营", "industry_state": "match", "conditions": "风力发电设施建设和运营活动。", "source_pages": [84], "retrieval_notice": "目录依据真实；此处不展示虚构匹配分"}]},
            "condition_review": {"conditions": [{"condition_id": "D1", "condition_text": "募集资金投向风力发电项目且项目已建成运营", "status": "met", "assessment_source": "年度受托管理报告及第三方绿色跟踪评估"}]},
            "evidence_review": {"required_count": 2, "verified_count": 2, "verified_completeness": 1.0, "items": [{"required_type": "发行期环境效益测算", "description":"形成公开测算基准，不等同承诺目标", "status": "verified", "matched_evidence": [{"source": "22吉电G1首次存续期跟踪评估", "type": "第三方跟踪评估", "verification_status": "verified", "page": "PDF第2页", "confidence": 1.0}]},{"required_type":"年度实际环境绩效","description":"核验实际发电量及折算减排量","status":"verified","matched_evidence":[{"source":"22吉电G1绿色债券跟踪评估（2024年度）","type":"第三方跟踪评估","verification_status":"verified","page":"PDF第11—12页","confidence":1.0}]}]},
        },
        "bta_metrics": metrics,
    }


def _legacy_build_view(case_id: str, case: dict[str, Any], case_storage: Path) -> dict[str, Any]:
    case_id = canonical_case_id(case_id)
    if case_id == "DEMO-D" and not case:
        case = demo_d_case(case_storage)
    assessment = reassessment(case_id)
    if assessment:
        case = copy.deepcopy(case)
        case["storage_case_id"] = case.get("case_id", case_id)
        case["case_id"] = case_id
        case["status"] = "HUMAN_REVIEW"
        case["_reassessment_key"] = case_id
        case["_reassessment"] = assessment
        case["rule_assessments"] = assessment.get("rules", [])
        mid_for_display = case.setdefault("midloan_review", {})
        mid_for_display["review_suggestion"] = "HUMAN_REVIEW"
        mid_for_display["review_label"] = assessment.get("main_status", "待人工复核")
        mid_for_display["manual_review_required"] = True
        mid_for_display["review_reasons"] = [assessment.get("summary", ""), "本结论依据逐项规则；不判断银行材料齐全或自动初审通过。"]
        mid_for_display["condition_review"] = {
            "display_mode": "rule_by_rule",
            "notice": "条件按规则逐条展示；不再以比例或百分比表达完整性。",
            "conditions": [],
        }
        mid_for_display["evidence_review"] = {
            "display_mode": "rule_by_rule",
            "evidence_status": "rule_level_only",
            "notice": "旧材料计数与完整度结果不参与本轮结论；以当前规则矩阵为准。",
            "rule_assessments": case["rule_assessments"],
        }
        mid_for_display["field_worklist"] = {
            "notice": "补证任务由当前规则矩阵生成，不是政策规定的文件份数。",
        }
        mid_for_display.pop("approved_catalog_code", None)
        mid_for_display["catalog_activity_code"] = "4.2.1" if case_id == "DEMO-A" else "1.3.4"
        mid_for_display["fund_use_binding_review"] = {
            "status": "rule_level_only",
            "notice": "计划分配、实际支付和本次银行贷款用途分别判断，不能相互替代。",
            "rules": [x for x in case["rule_assessments"] if "FUND" in x.get("rule_id", "")],
        }
        mid_for_display["preloan_consistency_review"] = {
            "status": "human_review",
            "conflicts": [x for x in case["rule_assessments"] if x.get("status") == "evidence_conflict"],
            "notice": "跨文件差异由授权人员解释，不由模型自动消除。",
        }
        mid_for_display["data_availability"] = {
            "proven_rule_ids": [x["rule_id"] for x in case["rule_assessments"] if x["status"] == "proven"],
            "pending_or_conflict_rule_ids": [x["rule_id"] for x in case["rule_assessments"] if x["status"] in {"pending_evidence", "evidence_conflict"}],
            "cannot_determine_rule_ids": [x["rule_id"] for x in case["rule_assessments"] if x["status"] == "cannot_determine"],
            "notice": "状态按规则陈述，不折算为材料完整度。备选路线另列，不进入主路径任务计数。",
        }
        mid_for_display["methodological_limitations"] = [
            "目录活动相符不等于全部技术条件满足，更不等于银行授信通过。",
            "政策明文条件与模型建议的证明方式分列，证明方式不得冒充政策必交文件清单。",
            "银行产品、行业和分行内部规则未接入时，银行材料完整性无法判定。",
            "设计值与实际值必须同范围、同期间、同核算口径才可比较。",
            "备选目录条件只在主张该路线时适用，不强加到当前主路径。",
        ]
        case.setdefault("routing", {})["route_reason"] = assessment.get("headline", "按逐项规则待人工复核")
        if case_id == "DEMO-B":
            case["routing"]["transition_status"] = "cannot_determine"
            case["transition_review"] = {
                "matched_rules": [],
                "status": "cannot_determine",
                "notice": "河北规则对四川攀钢不适用；河北2023—2024版已废止。四川适用钢铁转型规则尚未接入/确认。",
            }
    mid = case.get("midloan_review", {})
    conditions = mid.get("condition_review", {}).get("conditions") or mid.get("condition_review", {}).get("condition_results") or []
    evidence = mid.get("evidence_review", {})
    missing = missing_materials(case)
    candidates = mid.get("catalog_retrieval", {}).get("top_candidates", [])
    if assessment:
        official_candidates(candidates)
    if assessment and case_id == "DEMO-A":
        explanations = {
            "4.2.1": "排序分由TF-IDF、关键词、行业一致和申报条目加分组成；不是46%合规概率。",
            "4.3.1": "因行业一致和“风电”关键词进入备选，但缺少源网荷储/多能互补事实。",
            "4.1.1": "含“风电”关键词，但该条是装备制造活动，与本项目建设活动不一致。",
        }
        for candidate in candidates:
            candidate["score_explanation"] = explanations.get(candidate.get("catalog_code"), "仅用于候选排序，不是合规概率。")
    if assessment and case_id == "DEMO-B":
        for candidate in candidates:
            candidate["industry_state"] = "activity_match" if candidate.get("catalog_code") == "1.3.4" else "candidate_only"
            candidate["score_explanation"] = "由公开项目文件人工映射，未计算排序分；条目条件仍须逐项核验。"
    bta = case.get("bta_metrics", [])
    if not bta:
        path = case_storage / case_id / "bta_result.json"
        if path.exists():
            bta = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "case": case,
        "overview": case_overview(case_id, case, case_storage / case_id),
        "summary": business_summary(case_id, case, missing),
        "profile": profile_rows(case),
        "candidates": candidates,
        "conditions": conditions,
        "rule_assessments": case.get("rule_assessments", []),
        "project_check": {
            "category": ("4.2.1 活动映射已证明" if case_id == "DEMO-A" else "1.3.4 回测活动相符") if assessment else ("目录候选已召回" if mid.get("catalog_retrieval", {}).get("state") == "reliable_candidate" or case_id == "DEMO-D" else "待核验"),
            "category_basis": (assessment.get("catalog_result", "") + "；召回分只用于排序，不是绿色程度。") if assessment else "依据绿色目录候选召回、行业一致性和已申报项目类别；召回分不是绿色程度。",
            "conditions": ("该条无数值阈值" if case_id == "DEMO-A" else "回测标准符合性待补") if assessment else ("逐条核验" if conditions else "尚待逐项核验"),
            "conditions_basis": "详见下方规则级矩阵；不以比例替代判断。" if assessment else "仅以条件级项目值和证据判断，不由文本相似度推定满足。",
            "evidence": "存在冲突与待补证" if assessment else ("有待补事项" if missing else "当前预置证据已核验"),
            "evidence_basis": "仅指当前逐条规则状态，不宣称完整授信材料齐全。" if assessment else "证据完整性以适用规则和银行清单为准。",
            "bank": "无法判定（规则未接入）" if assessment else "银行规则待确认",
            "bank_basis": (assessment.get("bank_result", "") + "；未接入内部清单时不判断材料完整性。") if assessment else "工行内部行业、产品和分行清单未接入时，银行材料完整性无法判定。",
            "performance": "明显偏离" if case_id == "DEMO-D" else ("Target与Actual不可比" if case_id == "DEMO-B" and assessment else ("仅有设计值" if case_id == "DEMO-A" and assessment else ("部分公开实绩" if case_id == "DEMO-B" else ("已有监测数据" if bta else "暂无数据")))),
            "performance_basis": "2024实际折算减排20.34万吨，较发行期测算24.61万吨低17.35%。" if case_id == "DEMO-D" else ("设计值为全项目，2022公开转引实绩仅为一期；范围、期间和核算口径未对齐。" if case_id == "DEMO-B" else ("当前为预计发电量，不得表述为实际环境绩效。" if case_id == "DEMO-A" and assessment else ("依据已上传Actual数据计算。" if bta else "尚未进入或尚未上传贷后Actual数据。"))),
        },
        "missing": missing,
        "optional_evidence": missing_materials(case, optional=True),
        "human_checks": human_checks(case, case_id == "DEMO-D"),
        "bta": bta,
        "provenance": provenance(case_id),
    }


def build_view(case_id: str, case: dict[str, Any], case_storage: Path) -> dict[str, Any]:
    """Only demo loan-middle presentation changes; source Case and B-T-A stay intact."""
    from .simplified_demo_rules import assessment as indicator_assessment, STATUS_LABELS as labels
    case_id = canonical_case_id(case_id)
    assessment = indicator_assessment(case_id)
    if not assessment:
        return _legacy_build_view(case_id, case, case_storage)
    if case_id == "DEMO-D" and not case:
        case = demo_d_case(case_storage)
    case = copy.deepcopy(case)
    case["storage_case_id"] = case.get("case_id", case_id)
    case["case_id"] = case_id
    case["_simplified_rules"] = True
    case["_reassessment_key"] = case_id
    case["_reassessment"] = assessment
    case["rule_assessments"] = assessment["rules"]
    case["status"] = "HUMAN_REVIEW"
    mid = case.setdefault("midloan_review", {})
    mid["review_suggestion"] = "HUMAN_REVIEW"
    mid["review_label"] = assessment["main_status"]
    mid["manual_review_required"] = True
    mid["review_reasons"] = [assessment["summary"], "按指标和证据辅助核验，不按文件份数认定完整或通过。"]
    mid["condition_review"] = {"display_mode": "indicator_matrix", "conditions": [], "rule_assessments": assessment["rules"]}
    mid["evidence_review"] = {"display_mode": "indicator_matrix", "notice": "证据内容支持指标；文件名称及份数不是通过条件。", "rule_assessments": assessment["rules"]}
    mid["field_worklist"] = {"notice": "任务来自同一指标矩阵，补充证据不自动改变核验结论。"}
    mid.pop("approved_catalog_code", None)
    mid["methodological_limitations"] = [assessment["scope_notice"], assessment["bank_result"], "当前Demo指标结果为公开材料预先结构化回测，材料登记不会自动确认技术标准符合性。"]
    routing = case.setdefault("routing", {})
    routing["route_reason"] = assessment["headline"]
    routing["transition_route"] = bool(assessment["transition_rules"])
    if assessment["transition_rules"]:
        routing["transition_status"] = "reference_backtest"
        case["transition_review"] = {
            "status": "reference_backtest", "mode": "reference_backtest", "notice": assessment["scope_notice"],
            "matched_rules": [{"rule_id": x["rule_id"], "field": x["claim"], "conditions": [x["requirement"]]} for x in assessment["transition_rules"]],
            "rule_assessments": assessment["transition_rules"],
        }
    candidates = copy.deepcopy(mid.get("catalog_retrieval", {}).get("top_candidates", []))
    official_candidates(candidates)
    if case_id == "DEMO-C":
        # Preserve actual retrieval outputs, but stop displaying irrelevant building
        # candidates as the best project fit. This new reference is a manual candidate.
        candidates = [{"catalog_code": "1.4.2", "industry_state": "candidate_only", "retrieval_score": None,
                       "score_explanation": "人工参考候选：集团低碳改造主题相关，具体工程、燃料及活动范围尚未证明；不冒充TF-IDF输出。"}]
        official_candidates(candidates)
    for candidate in candidates:
        if case_id == "DEMO-B":
            candidate["industry_state"] = "activity_match" if candidate.get("catalog_code") == "1.3.4" else "candidate_only"
            candidate["score_explanation"] = "公开项目活动人工映射，未计算排序分；引用标准仍需核实。1.4.1仅备选，不增加当前主路径任务。"
        elif case_id == "DEMO-A":
            candidate["score_explanation"] = "实际候选排序分由文本相似、关键词、行业及申报条目等组成，不是合规概率；行业关联与项目活动条件分别判断。"
    mid.setdefault("catalog_retrieval", {})["top_candidates"] = candidates
    bta = case.get("bta_metrics", [])
    if not bta:
        path = case_storage / case_id / "bta_result.json"
        if path.exists():
            bta = json.loads(path.read_text(encoding="utf-8-sig"))
    overview = case_overview(case_id, case, case_storage / case_id)
    overview.update(route=assessment["route_label"], status=assessment["main_status"])
    green = assessment["green_rules"]
    technical = [green[2]] + [x for x in assessment["transition_rules"] if x["rule_id"] in {"H02", "H03", "J02", "J03"}]
    conditions_label = "参考对标待核实" if any(x["status"] == "pending_evidence" for x in technical) else labels[green[2]["status"]]
    performance = {
        "DEMO-A": ("仅有设计值", "当前为预计发电量，不表述为实际环境绩效。"),
        "DEMO-B": ("设计与一期实绩不可直接比较", "全项目设计值与2022一期实绩范围、期间及口径尚未对齐。"),
        "DEMO-C": ("集团公开实绩", "99.84kgce/吨熟料、0.8112吨CO2e/吨熟料及13%为集团指标，不推定单线达标。"),
        "DEMO-D": ("明显偏离", "2024实际折算减排20.34万吨，较发行期测算24.61万吨低17.35%。"),
    }[case_id]
    return {
        "case": case, "overview": overview, "summary": assessment["summary"], "profile": profile_rows(case),
        "candidates": candidates, "conditions": [], "rule_assessments": assessment["rules"],
        "green_rules": green, "transition_rules": assessment["transition_rules"],
        "project_check": {
            # Keep this D field unchanged because the existing post-loan contrast
            # consumes it; the new G01 row gives the precise loan-middle activity.
            "category": "目录候选已召回" if case_id == "DEMO-D" else "活动相符" if green[0]["status"] == "proven" else "具体活动待核实",
            "category_basis": green[0]["fact"], "conditions": conditions_label,
            "conditions_basis": "按明文技术条件与参考指标判断；没有附加门槛的明确说明，不换算评分。",
            "evidence": labels[green[3]["status"]], "evidence_basis": green[3]["fact"],
            "bank": "无法判断（未接入）", "bank_basis": assessment["bank_result"],
            "performance": performance[0], "performance_basis": performance[1],
        },
        "missing": missing_materials(case), "optional_evidence": [],
        "human_checks": assessment["human_checks"], "bta": bta, "provenance": provenance(case_id),
    }
