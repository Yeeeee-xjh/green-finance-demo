"""Shared shell for the loan-case dossier workspace."""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote


def e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


CASE_STATUS_LABELS = {
    "draft": "草稿",
    "ingesting": "材料入库中",
    "parse_review": "解析待复核",
    "classifying": "行业定标中",
    "verifying": "风险核验中",
    "action_required": "待处理事项",
    "human_review": "待人工确认",
    "monitoring": "贷后监测中",
    "closed": "已关闭",
    "failed": "处理失败",
}

GLOBAL_NAV = (
    ("dashboard", "/dashboard", "案件概览"),
    ("cases", "/cases", "全部案件"),
    ("new_case", "/cases/new", "新建案件"),
    ("tasks", "/tasks", "待办任务"),
    ("rules", "/rules", "行业规则"),
)

CASE_NAV = (
    ("overview", "overview", "案件主页", ""),
    ("documents", "documents", "材料与证据", "判断依据"),
    ("classification", "classification", "行业与阶段", ""),
    ("risks", "risks", "风险识别", "双核验"),
    ("verification", "verification", "辅助核验", ""),
    ("reading", "reading", "辅助阅读", ""),
    ("conflicts", "conflicts", "冲突台账", ""),
    ("monitoring", "monitoring", "贷后监测", "后续作业"),
    ("reports", "reports", "报告与审计", ""),
)

STEPS = (
    (1, "材料入库"),
    (2, "行业与阶段"),
    (3, "风险与证据核验"),
    (4, "补件与人工确认"),
    (5, "贷后监测"),
)


def case_step(case: dict[str, Any] | None) -> int | None:
    if not case:
        return None
    status = case.get("failed_from_status") if case.get("status") == "failed" else case.get("status")
    return {
        "draft": 1,
        "ingesting": 1,
        "parse_review": 1,
        "classifying": 2,
        "verifying": 3,
        "action_required": 4,
        "human_review": 4,
        "monitoring": 5,
        "closed": 5,
    }.get(status, 1)


def _global_navigation(active: str) -> str:
    links = []
    for code, href, label in GLOBAL_NAV:
        current = ' class="active" aria-current="page"' if code == active else ""
        links.append(f'<a href="{href}"{current}>{e(label)}</a>')
    return "".join(links)


def _case_navigation(case: dict[str, Any], active: str) -> str:
    case_id = quote(str(case["case_id"]), safe="")
    links = []
    for code, suffix, label, group in CASE_NAV:
        if group:
            links.append(f'<span class="case-nav-group">{e(group)}</span>')
        current = ' class="active" aria-current="page"' if code == active else ""
        links.append(f'<a href="/cases/{case_id}/{suffix}"{current}>{e(label)}</a>')
    project = case.get("project_name") or case.get("case_name") or "未命名项目"
    return f'''<div class="case-index">
      <a class="back-to-cases" href="/cases">← 返回案件队列</a>
      <div class="case-context"><span>当前案件</span><b>{e(project)}</b></div>
      <nav>{"".join(links)}</nav>
    </div>'''


def _stepper(case: dict[str, Any] | None) -> str:
    current = case_step(case)
    items = []
    for number, label in STEPS:
        state = "done" if current and number < current else "current" if current == number else ""
        items.append(f'<li class="{state}"><span>{number}</span><b>{e(label)}</b></li>')
    return '<ol class="process-rail">' + "".join(items) + "</ol>"


def _case_header(case: dict[str, Any], workflow: dict[str, Any] | None = None) -> str:
    is_demo = case.get("record_origin") == "legacy_demo"
    is_fullchain_showcase = is_demo and "fullchain_showcase" in str(case.get("legacy_note") or "")
    origin = "全链路合成演示数据" if is_fullchain_showcase else "公开案例演示数据" if is_demo else "正式案件数据"
    workflow = workflow or {}
    action_href = e(workflow.get("action_href") or "#")
    action_label = e(workflow.get("action_label") or "查看案件")
    disclosure_text = (
        "本案的企业、项目材料和业务数值均为合成演示数据，只用于验证全链路功能；相关结果不计入正式统计，不作为授信或政策认定结论。"
        if is_fullchain_showcase else
        "本案用于验证作业流程，历史预置核验状态与测算不作为真实模型结果，也不计入正式业务统计。"
    )
    disclosure = (
        f'<div class="simulation-disclosure"><b>{"合成演示案例" if is_fullchain_showcase else "演示数据"}</b><span>{e(disclosure_text)}</span></div>'
        if is_demo else ""
    )
    return f'''<header class="dossier-heading">
      <div class="dossier-title">
        <h1>{e(case.get("project_name") or case.get("case_name") or "未命名项目")}</h1>
        <span>{e(case.get("borrower_name") or "借款企业待填写")}</span>
      </div>
      <dl class="dossier-meta">
        <div><dt>状态</dt><dd>{e(CASE_STATUS_LABELS.get(case.get("status"), case.get("status") or "未记录"))}</dd></div>
        <div><dt>经办人</dt><dd>{e(case.get("assignee") or "待分配")}</dd></div>
        <div><dt>贷款阶段</dt><dd>{e(case.get("loan_stage") or "贷前调查")}</dd></div>
        <div><dt>数据口径</dt><dd>{e(origin)}</dd></div>
      </dl>
    </header>
    <section class="case-now" aria-label="当前步骤与下一步">
      <div><span>当前步骤</span><b>{e(workflow.get("current_label") or "案件处理中")}</b></div>
      <div class="next-action"><span>下一步</span><b>{e(workflow.get("next_action") or "查看案件待办")}</b></div>
      <a class="button primary" href="{action_href}">{action_label}</a>
    </section>{disclosure}'''


def render_layout(
    *,
    title: str,
    content: str,
    active: str,
    case: dict[str, Any] | None = None,
    workflow: dict[str, Any] | None = None,
    subtitle: str | None = None,
) -> str:
    case_nav = _case_navigation(case, active) if case else ""
    case_header = _case_header(case, workflow) if case else ""
    global_navigation = "" if case else f'<nav class="global-nav">{_global_navigation(active)}</nav>'
    settings_link = '<a href="/settings/integrations">系统边界与对接</a>' if not case else ""
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{e(title)}｜数绿融通</title>
  <link rel="stylesheet" href="/assets/phase2.css">
</head>
<body>
  <a class="skip-link" href="#main">跳到主要内容</a>
  <div class="ambient ambient-one" aria-hidden="true"></div>
  <div class="ambient ambient-two" aria-hidden="true"></div>
  <button class="nav-toggle" type="button" aria-label="收起目录" aria-controls="sidebar" aria-expanded="true" data-sidebar-toggle><span></span><span></span></button>
  <aside class="sidebar" id="sidebar">
    <a class="brand" href="/dashboard"><i aria-hidden="true"><span>数</span><span>绿</span></i><div><b>数绿融通</b><span>绿色金融贷款风险识别与辅助核验</span></div></a>
    {global_navigation}
    {case_nav}
    <footer><b>使用边界</b><span>系统提供风险线索与核验依据，最终判断由授权人员完成。</span>{settings_link}<a href="/legacy">历史版本只读入口</a></footer>
  </aside>
  <div class="workspace">
    <header class="topbar">
      <div><span>{e(subtitle or "绿色金融贷款项目作业")}</span><b>{e(title)}</b></div>
      {_stepper(case)}
      <em>本地沙盒</em>
    </header>
    <main id="main" class="page" data-page-root="{e(active)}">
      {case_header}
      {content}
    </main>
    <footer class="site-footer"><span>案件材料、判断与操作统一留痕</span><span>风险分用于复核排序，不替代授信审批</span></footer>
  </div>
  <script src="/assets/phase2.js" defer></script>
</body>
</html>'''
