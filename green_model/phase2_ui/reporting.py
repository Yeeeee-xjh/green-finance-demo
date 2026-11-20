"""公网跨平台报告生成模块，支持PDF与JSON导出，无Windows硬编码路径。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase.ttfonts import TTFont


def _register_chinese_font() -> str:
    """自动探测可用中文字体，优先系统TTF，最后降级到内置CID字体。"""
    # 内置CID字体无需外部文件，保证中文不会乱码
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass

    candidate_fonts = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for font_path in candidate_fonts:
        if Path(font_path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("ChineseFont", font_path))
                return "ChineseFont"
            except Exception:
                continue
    return "STSong-Light"


FONT_NAME = _register_chinese_font()


def _build_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title",
            fontName=FONT_NAME,
            fontSize=18,
            leading=24,
            spaceAfter=12,
            textColor=colors.HexColor("#0F5D4F"),
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=FONT_NAME,
            fontSize=14,
            leading=20,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#0F5D4F"),
        ),
        "body": ParagraphStyle(
            "body",
            fontName=FONT_NAME,
            fontSize=10,
            leading=16,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "small",
            fontName=FONT_NAME,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#555555"),
            wordWrap="CJK",
        ),
    }


def report_payload(view: dict[str, Any]) -> dict[str, Any]:
    """返回公网演示报告结构化字典，用于审计快照。"""
    case = view.get("case", {})
    return {
        "case": {
            "case_id": case.get("case_id"),
            "project_name": case.get("project_name"),
            "borrower_name": case.get("borrower_name"),
            "primary_industry": case.get("primary_industry"),
            "status": case.get("status"),
        },
        "report_type": "离线演示核验报告",
        "disclaimer": "本报告为公网合成演示数据，不构成任何授信审批、风险认定或投资建议。",
        "summary": view.get("summary", {}),
        "risk_findings": view.get("risks", []),
        "verification_items": view.get("verification", []),
        "model_status": "not_run_offline_demo",
    }


def json_bytes(view: dict[str, Any]) -> bytes:
    """生成脱敏演示JSON报告字节。"""
    public_view = report_payload(view)
    return json.dumps(public_view, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def pdf_bytes(view: dict[str, Any]) -> bytes:
    """生成PDF报告字节，全程内存操作，不写临时文件。"""
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="数绿融通离线演示报告",
    )
    styles = _build_styles()
    story = []

    case = view.get("case", {})
    story.append(Paragraph("数绿融通绿色信贷智能体 · 核验报告", styles["title"]))
    story.append(Paragraph(
        "【公网离线演示版本】本报告基于合成脱敏数据生成，不构成银行授信结论、风险认定或投资建议。",
        styles["small"],
    ))
    story.append(Spacer(1, 8 * mm))

    # 基础信息表
    basic_data = [
        ["案件编号", str(case.get("case_id", "-"))],
        ["项目名称", str(case.get("project_name", "-"))],
        ["借款主体", str(case.get("borrower_name", "-"))],
        ["所属行业", str(case.get("primary_industry", "-"))],
        ["案件状态", str(case.get("status", "-"))],
        ["模型状态", "未运行（离线演示结果）"],
    ]
    basic_table = Table(basic_data, colWidths=[40 * mm, 130 * mm])
    basic_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F3F0")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#0F5D4F")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(basic_table)
    story.append(Spacer(1, 8 * mm))

    # 风险摘要
    story.append(Paragraph("一、风险线索摘要", styles["h2"]))
    risks = view.get("risks", [])
    if not risks:
        story.append(Paragraph("当前演示案件无待核实风险线索。", styles["body"]))
    else:
        risk_data = [["风险维度", "线索数量", "演示状态"]]
        for axis in risks:
            risk_data.append([
                str(axis.get("axis_name", "-")),
                str(axis.get("finding_count", 0)),
                "待人工核实（离线演示）",
            ])
        risk_table = Table(risk_data, colWidths=[50 * mm, 35 * mm, 85 * mm])
        risk_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F5D4F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(risk_table)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("二、合规声明", styles["h2"]))
    story.append(Paragraph(
        "1. 本系统为公网演示环境，所有数据均为合成脱敏或公开来源数据，不包含任何真实客户信息；<br/>"
        "2. BERT大模型未在公网环境运行，所有分析结果均为离线演示结果，不代表真实模型输出；<br/>"
        "3. 系统不会自动作出授信批准、拒绝、停贷或违规认定，所有业务结论需由持牌机构人工复核；<br/>"
        "4. 演示规则均标记为模拟规则，不代表任何商业银行内部正式风控规则。",
        styles["body"],
    ))

    doc.build(story)
    return buffer.getvalue()
