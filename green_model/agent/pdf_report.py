"""Generate a review-ready Chinese PDF report from the same Case view."""
from __future__ import annotations

from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from agent.product_intelligence import SOURCE_IDS

FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))
STATUS_CN = {"proven":"满足", "met":"满足", "verified":"满足", "not_applicable":"不适用", "evidence_conflict":"证据冲突", "conflict":"证据冲突", "pending_evidence":"待核实", "cannot_determine":"无法判断", "information":"属性说明"}


def _p(text, style):
    text = str(text if text is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    return Paragraph(text, style)


def build_pdf_bytes(case_id: str, view: dict, product: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm, title=f"数绿融通_{case_id}_业务报告")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("cn-title", parent=styles["Title"], fontName=FONT, fontSize=21, leading=30, textColor=colors.HexColor("#173F37"), alignment=TA_LEFT, spaceAfter=8)
    sub = ParagraphStyle("cn-sub", parent=styles["Normal"], fontName=FONT, fontSize=9, leading=15, textColor=colors.HexColor("#66736F"))
    h1 = ParagraphStyle("cn-h1", parent=styles["Heading1"], fontName=FONT, fontSize=14, leading=21, textColor=colors.HexColor("#173F37"), spaceBefore=10, spaceAfter=8)
    h2 = ParagraphStyle("cn-h2", parent=styles["Heading2"], fontName=FONT, fontSize=11, leading=17, textColor=colors.HexColor("#285E52"), spaceBefore=6, spaceAfter=5)
    body = ParagraphStyle("cn-body", parent=styles["BodyText"], fontName=FONT, fontSize=8.6, leading=13.5, textColor=colors.HexColor("#27332F"))
    small = ParagraphStyle("cn-small", parent=body, fontSize=7.3, leading=10.8, textColor=colors.HexColor("#52635E"))
    center = ParagraphStyle("cn-center", parent=body, alignment=TA_CENTER)

    def table(data, widths=None, header=True):
        result = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [("FONTNAME", (0,0), (-1,-1), FONT), ("FONTSIZE", (0,0), (-1,-1), 7.2), ("LEADING", (0,0), (-1,-1), 10.5), ("VALIGN", (0,0), (-1,-1), "TOP"), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CBD8D3")), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]
        if header:
            commands += [("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E8F0ED")), ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#173F37"))]
        result.setStyle(TableStyle(commands))
        return result

    story = [_p("数绿融通绿色金融贷款辅助核验报告", title), _p(f"Case：{case_id}　生成口径：行业识别—风险扫描—行业辅助核验—人工确认—贷后续办", sub), Spacer(1, 5*mm)]
    o = view.get("overview", {})
    overview = [
        [_p("项目", small), _p(o.get("project"), body), _p("企业", small), _p(o.get("company"), body)],
        [_p("行业", small), _p(product["industry"], body), _p("企业阶段", small), _p(product["enterprise_stage"], body)],
        [_p("项目阶段", small), _p(product["project_stage"], body), _p("建议状态", small), _p(o.get("status"), body)],
        [_p("银行内部规则", small), _p("未接入 / 无法判断", body), _p("绿色金融关系", small), _p(product["green_relation"], body)],
    ]
    story += [table(overview, [25*mm, 60*mm, 28*mm, 57*mm], header=False), Spacer(1, 4*mm), _p("报告摘要", h1), _p(view.get("summary"), body), _p("本报告为辅助核验结果，不替代授信审批、法律意见、环境评价或授权人员最终认定。", small)]
    story += [_p("一、Agent任务状态", h1)]
    data = [[_p("步骤", small), _p("任务", small), _p("状态", small), _p("结果", small)]]
    for x in product["agent_steps"]:
        data.append([_p(x["no"], center), _p(x["name"], small), _p(x["status"], small), _p(x["detail"], small)])
    story.append(table(data, [14*mm, 34*mm, 24*mm, 98*mm]))
    story += [_p("二、五维风险识别", h1), _p(product["score_note"], small)]
    data = [[_p("风险维度", small), _p("关注指数", small), _p("等级", small), _p("当前判断", small), _p("依据", small)]]
    for x in product["risk_dimensions"]:
        data.append([_p(x["name"], small), _p(x["score"], center), _p(x["level"], center), _p(x["summary"], small), _p(x["source_ids"], small)])
    story.append(table(data, [34*mm, 20*mm, 17*mm, 78*mm, 21*mm]))
    story += [_p("重点风险事项", h2)]
    data = [[_p("事项", small), _p("系统发现", small), _p("建议动作", small), _p("规则/来源", small)]]
    for x in product["risk_signals"]:
        data.append([_p(x["title"], small), _p(x["finding"], small), _p(x["action"], small), _p(f"{x['rule_id']} / {x['source_ids']}", small)])
    story.append(table(data, [31*mm, 54*mm, 62*mm, 23*mm]))
    story += [_p("三、行业辅助核验", h1), _p(f"企业主行业：{product['industry']}（{product['industry_code']}）；企业阶段：{product['enterprise_stage']}；项目阶段：{product['project_stage']}。企业行业与项目活动分别记录，阶段标签用于调整核验重点，不作为银行评级。", body), _p("当前阶段辅助重点：" + "；".join(product["stage_focus"]), small)]
    items = view.get("rule_assessments") or view.get("green_rules") or view.get("conditions") or []
    data = [[_p("核验事项", small), _p("规则要求", small), _p("项目事实", small), _p("证据/定位", small), _p("状态", small), _p("下一步", small)]]
    for item in items:
        rid = item.get("rule_id") or item.get("id") or item.get("rule") or "—"
        claim = item.get("claim") or item.get("name") or item.get("description") or "—"
        requirement = item.get("requirement") or item.get("description") or item.get("policy_requirement") or "—"
        fact = item.get("fact") or item.get("project_fact") or item.get("value") or "—"
        evidence = item.get("evidence") or item.get("source") or item.get("basis") or "—"
        status = item.get("status") or "待核实"
        status = STATUS_CN.get(str(status), status)
        action = item.get("next_evidence") or item.get("next_step") or "人工确认或补充证据"
        data.append([_p(f"{rid} {claim}", small), _p(requirement, small), _p(fact, small), _p(evidence, small), _p(status, small), _p(action, small)])
    story.append(table(data, [27*mm, 36*mm, 36*mm, 33*mm, 18*mm, 28*mm]))
    story += [_p("四、建议人工重点核验", h1)]
    checks = view.get("human_checks", [])
    if checks:
        for idx, item in enumerate(checks, 1):
            story += [_p(f"{idx}. {item.get('check')}", h2), _p(item.get("why"), body)]
    else:
        story.append(_p("当前未生成具体人工核验项；银行内部规则仍未接入。", body))
    story += [_p("五、贷后B-T-A监测", h1)]
    bta = view.get("bta", [])
    if bta:
        data = [[_p("指标", small), _p("Baseline", small), _p("Target/测算", small), _p("Actual", small), _p("偏离", small), _p("人工复核", small)]]
        for x in bta:
            dev = x.get("deviation")
            dev = "暂无数据" if dev is None else f"{float(dev)*100:.2f}%"
            data.append([_p(x.get("metric_name"), small), _p(x.get("baseline_value"), small), _p(x.get("target_value"), small), _p(x.get("actual_value"), small), _p(dev, small), _p("是" if x.get("manual_attention") else "否", small)])
        story.append(table(data, [39*mm, 25*mm, 28*mm, 25*mm, 25*mm, 28*mm]))
    else:
        story.append(_p("当前尚未进入贷后实绩监测；未监测不按0分处理。", body))
    story += [PageBreak(), _p("六、责任边界与数据来源", h1), _p(product["bank_rule_note"], body), _p("报告中的S01—S11为公开来源编号，完整网址、使用方式和禁止推断事项单列于《数绿融通公开数据与规则来源清单》。Case原始文件、页码、哈希与审计事件由系统留痕。", body)]
    source_rows = [[_p("编号", small), _p("公开来源", small)]] + [[_p(sid, center), _p(name, small)] for sid, name in SOURCE_IDS.items()]
    story += [Spacer(1, 3*mm), table(source_rows, [20*mm, 150*mm]), Spacer(1, 5*mm), _p("结论边界：候选不等于认定；缺失不等于违规；偏离不等于处罚；绿色属性不等于授信批准。", h2)]
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2DF"))
        canvas.line(15*mm, 9*mm, 195*mm, 9*mm)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor("#71807B"))
        canvas.drawString(15*mm, 5.5*mm, f"数绿融通 · {case_id} · 辅助核验，不替代授信审批")
        canvas.drawRightString(195*mm, 5.5*mm, f"第 {document.page} 页")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
