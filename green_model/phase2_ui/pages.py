"""Evidence-first HTML views for the loan-case dossier."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote

from .intelligence import RiskAxis
from .layout import CASE_STATUS_LABELS, e
from .queries import DashboardSnapshot


TASK_LABELS = {
    "pending": "待处理",
    "in_progress": "处理中",
    "pending_review": "待审核",
    "returned": "已退回",
    "closed": "已关闭",
}

TASK_TYPE_LABELS = {
    "supplement_review": "补件复核",
    "supplement": "补件复核",
    "supplement_request": "补件任务",
    "conflict_review": "冲突核实",
    "conflict": "冲突核实",
    "warning": "贷后预警复核",
    "postloan_warning": "贷后预警复核",
    "postloan_alert": "贷后预警复核",
    "verification_review": "核验事项复核",
    "onsite_verification": "现场核验",
    "risk_clue_review": "风险线索复核",
}

AUDIT_ACTION_LABELS = {
    "case_created": "建立案件",
    "supplement_registered": "登记补充材料",
    "legacy_case_migrated": "迁入历史案例",
    "status_transition": "更新案件状态",
    "task_transition": "更新任务状态",
    "document_parsed": "完成材料解析",
    "document_parse_failed": "材料解析失败",
    "document_requires_ocr": "材料转入OCR待处理",
    "rule_registry_synced": "更新行业规则库",
}

PARSE_STATUS_LABELS = {
    "uploaded": "已上传",
    "queued": "等待解析",
    "parsing": "解析中",
    "parsed": "已解析",
    "needs_ocr": "需要OCR",
    "parse_failed": "解析失败",
    "human_verified": "人工校验完成",
}


def _empty(title: str, message: str) -> str:
    return f'<div class="empty-state"><b>{e(title)}</b><p>{e(message)}</p></div>'


def _status_badge(status: str | None, label: str | None = None) -> str:
    tone = {
        "satisfied": "ok",
        "attribute_only": "info",
        "not_applicable": "muted",
        "pending_verification": "warn",
        "cannot_determine": "unknown",
        "evidence_conflict": "danger",
        "not_satisfied": "danger",
        "closed": "ok",
        "low": "ok",
        "medium": "warn",
        "high": "danger",
        "critical": "danger",
        "unknown": "unknown",
    }.get(status or "", "muted")
    text = label or CASE_STATUS_LABELS.get(status, TASK_LABELS.get(status or "", status or "未记录"))
    return f'<span class="status {tone}">{e(text)}</span>'


def _page_intro(kicker: str, title: str, text: str, action: str = "") -> str:
    return f'''<section class="page-intro"><div><h1>{e(title)}</h1><span>{e(text)}</span></div>{action}</section>'''


def _risk_bar(axis: RiskAxis, detailed: bool = False) -> str:
    source = f'<small>{e(axis.score_source)}</small>' if detailed else ""
    if axis.score is None:
        scale = '<div class="risk-scale empty"><span>暂无可计算数据</span></div>'
        score = '<div class="risk-number empty"><b>未计算</b><span>等待适用核验项</span></div>'
    else:
        scale = f'<div class="risk-scale"><div><i style="left:{axis.score}%"></i></div><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>'
        score = f'<div class="risk-number"><b>{axis.score}</b><span>{e(axis.level)}</span></div>'
    return f'''<article class="risk-row {e(axis.tone)}">
      <div class="risk-name"><b>{e(axis.label)}</b><span>{e(axis.definition)}</span>{source}</div>
      {scale}{score}
      <div class="risk-count"><b>{axis.unresolved_count}</b><span>待处理 / {axis.applicable_count} 项适用</span></div>
    </article>'''


def _mock_tag(value: Any) -> str:
    return '<span class="mock-tag">示例规则</span>' if value else ""


def _radar_chart(axes: list[RiskAxis]) -> str:
    """Render only measured values; an incomplete axis never becomes a fake zero."""
    size, center, radius = 286, 143, 102
    points = []
    rings = []
    for ratio in (.25, .5, .75, 1.0):
        ring = []
        for index in range(5):
            angle = -math.pi / 2 + index * 2 * math.pi / 5
            ring.append(f"{center + radius * ratio * math.cos(angle):.1f},{center + radius * ratio * math.sin(angle):.1f}")
        rings.append(f'<polygon points="{" ".join(ring)}"/>')
    labels = []
    for index, axis in enumerate(axes):
        angle = -math.pi / 2 + index * 2 * math.pi / 5
        x = center + (radius + 27) * math.cos(angle)
        y = center + (radius + 19) * math.sin(angle)
        labels.append(f'<text x="{x:.1f}" y="{y:.1f}">{e(axis.label[:6])}</text>')
        if axis.score is not None:
            value_radius = radius * axis.score / 100
            points.append(f"{center + value_radius * math.cos(angle):.1f},{center + value_radius * math.sin(angle):.1f}")
    complete = len(points) == len(axes) == 5
    polygon = f'<polygon class="radar-value" points="{" ".join(points)}"/>' if complete else ""
    note = "" if complete else '<p>存在未计算维度，图形不连线，避免把缺失值当作 0。</p>'
    dots = "".join(
        f'<circle cx="{point.split(",")[0]}" cy="{point.split(",")[1]}" r="3"/>'
        for point in points
    )
    return f'''<div class="radar-wrap"><svg class="risk-radar" viewBox="0 0 {size} {size}" role="img" aria-label="五维风险剖面"><g class="radar-grid">{"".join(rings)}</g>{polygon}<g class="radar-dots">{dots}</g><g class="radar-labels">{"".join(labels)}</g></svg>{note}</div>'''


def _coverage_heatmap(coverage: dict[str, int]) -> str:
    total = max(int(coverage.get("rules") or 0), 1)
    cells = []
    for key, label in (("rules", "适用规则"), ("facts", "项目事实"), ("evidence", "证据定位"), ("tasks", "闭环任务")):
        value = int(coverage.get(key) or 0)
        ratio = value / total if key != "rules" else (1 if value else 0)
        level = "strong" if ratio >= .75 else "medium" if ratio >= .4 else "weak" if value else "empty"
        cells.append(f'<div class="coverage-cell {level}"><span>{e(label)}</span><b>{value}</b><small>{round(ratio * 100)}%</small></div>')
    return '<div class="coverage-heatmap">' + "".join(cells) + "</div>"


def _task_funnel(counts: dict[str, int]) -> str:
    stages = (("pending", "待处理"), ("in_progress", "处理中"), ("pending_review", "待审核"), ("closed", "已关闭"))
    maximum = max([int(counts.get(code) or 0) for code, _ in stages] + [1])
    return '<div class="task-funnel">' + "".join(
        f'<div style="--funnel-width:{36 + round(64 * int(counts.get(code) or 0) / maximum)}%"><span>{e(label)}</span><b>{int(counts.get(code) or 0)}</b></div>'
        for code, label in stages
    ) + '</div>'


def _evidence_distribution(counts: dict[str, int]) -> str:
    if not counts:
        return _empty("暂无证据来源", "材料解析后将显示原文来源分布。")
    maximum = max(counts.values())
    rows = "".join(
        f'<div><span>{e(name)}</span><i><em style="width:{round(value / maximum * 100)}%"></em></i><b>{value}</b></div>'
        for name, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    )
    return f'<div class="evidence-distribution">{rows}</div>'


def dashboard_page(snapshot: DashboardSnapshot) -> str:
    metric_specs = (
        ("case_count", "在办案件"),
        ("open_task_count", "待处理任务"),
        ("conflict_count", "未闭合冲突"),
        ("supplement_count", "待补材料"),
        ("postloan_warning_count", "贷后预警"),
        ("overdue_task_count", "逾期任务"),
    )
    metrics = "".join(
        f'<div data-metric="{e(code)}" data-value="{snapshot.metrics[code]}"><span>{e(label)}</span><b>{snapshot.metrics[code]}</b></div>' for code, label in metric_specs
    )
    if snapshot.recent_cases:
        rows = "".join(
            f'''<tr><td><a href="/cases/{quote(str(row['case_id']), safe='')}/overview"><b>{e(row.get('project_name') or row.get('case_name'))}</b><small>{e(row.get('borrower_name'))}</small></a></td>
            <td>{e(row.get('primary_industry') or '待定标')}</td><td>{e(row.get('assignee') or '待分配')}</td>
            <td>{_status_badge(row.get('status'))}</td><td>{e((row.get('updated_at') or '')[:16].replace('T', ' '))}</td></tr>'''
            for row in snapshot.recent_cases
        )
        recent = f'<div class="table-wrap"><table><thead><tr><th>项目与企业</th><th>行业</th><th>经办人</th><th>状态</th><th>更新</th></tr></thead><tbody>{rows}</tbody></table></div>'
    else:
        recent = _empty("暂无正式案件", "新建案件后，将按材料入库、行业定标、风险核验和任务闭环推进。")
    legacy = "".join(
        f'<a href="/cases/{quote(str(row["case_id"]), safe="")}/overview"><b>{e(row.get("project_name") or row.get("case_name") or "未命名演示案例")}</b><span>{e(row.get("borrower_name") or "演示案例")} · {"全链路合成演示" if "fullchain_showcase" in str(row.get("legacy_note") or "") else "流程参考"}</span></a>'
        for row in snapshot.legacy_demo_cases
    ) or '<span class="muted-copy">暂无演示案例参考</span>'
    risk_max = max([item["count"] for item in snapshot.risk_distribution] or [1]) or 1
    task_max = max([item["count"] for item in snapshot.task_distribution] or [1]) or 1
    has_risk_data = any(item["count"] for item in snapshot.risk_distribution)
    has_task_data = any(item["count"] for item in snapshot.task_distribution)
    risk_bars = "".join(
        f'<div data-risk="{e(item["code"])}" data-count="{item["count"]}"><span>{e(item["label"])}</span><i><b style="width:{item["count"] / risk_max * 100:.1f}%"></b></i><em>{item["count"]}</em></div>'
        for item in snapshot.risk_distribution
    ) if has_risk_data else ""
    task_bars = "".join(
        f'<div><span>{e(item["label"])}</span><i><b style="width:{item["count"] / task_max * 100:.1f}%"></b></i><em>{item["count"]}</em></div>'
        for item in snapshot.task_distribution
    ) if has_task_data else ""
    risk_empty = '<div class="chart-empty">0 项｜当前没有可计入正式统计的风险事项</div>' if not has_risk_data else ""
    task_empty = '<div class="chart-empty">0 项｜当前没有正式任务记录</div>' if not has_task_data else ""
    return _page_intro(
        "业务总览", "绿色金融贷款项目工作台", "从一笔贷款出发，把材料、行业规则、风险、证据、任务和贷后实绩连成同一份卷宗。",
        '<a class="button primary" href="/cases/new">新建贷款案件</a>',
    ) + f'''<section class="metric-strip">{metrics}</section>
    <section class="operations-charts"><article><header><h2>五维风险事项分布</h2></header><div class="micro-bars">{risk_bars}</div>{risk_empty}</article>
    <article><header><h2>任务处理状态分布</h2></header><div class="micro-bars task-bars">{task_bars}</div>{task_empty}</article></section>
    <section class="sheet"><header><div><h2>最近更新的正式案件</h2></div><a href="/cases">查看全部</a></header>{recent}</section>
    <section class="reference-register"><div><p>演示与公开案例参考</p><span>仅用于验证产品流程，不计入正式风险统计；合成案例在案件页持续标识。</span></div><nav>{legacy}</nav></section>'''


def cases_page(view: dict[str, Any]) -> str:
    def options(values, selected):
        return '<option value="">全部</option>' + "".join(
            f'<option value="{e(value)}" {"selected" if value == selected else ""}>{e(CASE_STATUS_LABELS.get(value, value))}</option>'
            for value in values
        )
    rows = "".join(
        f'''<tr><td><a href="/cases/{quote(str(row['case_id']), safe='')}/overview"><b>{e(row.get('project_name') or row.get('case_name'))}</b><small>{e(row.get('borrower_name'))}</small></a></td>
        <td>{e(row.get('primary_industry') or '待定标')}</td><td>{e(row.get('enterprise_stage') or '待判断')}</td>
        <td>{e(row.get('loan_stage') or '贷前调查')}</td><td>{e(row.get('assignee') or '待分配')}</td>
        <td>{_status_badge(row.get('status'))}</td><td class="number">{row.get('open_task_count', 0)}</td></tr>'''
        for row in view["cases"]
    )
    table = f'<div class="table-wrap"><table><thead><tr><th>项目与企业</th><th>行业</th><th>企业阶段</th><th>贷款阶段</th><th>经办人</th><th>状态</th><th>待办</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else _empty("没有符合条件的案件", "调整筛选条件或新建贷款案件。")
    showcase_cards = "".join(
        f'''<article>
          <div class="showcase-kicker"><span>录屏主案例</span><em>合成演示 · 不计入正式统计</em></div>
          <div class="showcase-body"><div><h2>{e(row.get('project_name') or row.get('case_name') or '全链路展示案例')}</h2>
          <p>{e(row.get('borrower_name') or '合成脱敏企业')}<span>{e(row.get('primary_industry') or '行业待定标')}</span></p></div>
          <a class="button primary" href="/cases/{quote(str(row['case_id']), safe='')}/overview">进入全链路案例</a></div>
          <dl><div><dt>项目材料</dt><dd>{int(row.get('document_count') or 0)} 份</dd></div>
          <div><dt>核验项</dt><dd>{int(row.get('verification_count') or 0)} 项</dd></div>
          <div><dt>待闭环任务</dt><dd>{int(row.get('open_task_count') or 0)} 项</dd></div>
          <div><dt>B-T-A指标</dt><dd>{int(row.get('indicator_count') or 0)} 组</dd></div></dl>
        </article>'''
        for row in view.get("showcase_cases", [])
    )
    showcase = (
        f'<section class="showcase-queue"><header><p>全链路展示案例</p><span>专用于录屏、讲解和全功能验证</span></header>{showcase_cards}</section>'
        if showcase_cards else ""
    )
    s = view["selected"]
    return _page_intro("案件队列", "贷款案件", "以单笔项目为最小工作对象，所有材料、判断与任务均回到同一案件。", '<a class="button primary" href="/cases/new">新建案件</a>') + showcase + f'''<section class="sheet">
      <form class="filter-bar" method="get"><label>案件状态<select name="status">{options(view['filters']['statuses'], s['status'])}</select></label>
      <label>所属行业<select name="industry">{options(view['filters']['industries'], s['industry'])}</select></label>
      <label>责任人<select name="assignee">{options(view['filters']['assignees'], s['assignee'])}</select></label>
      <button class="button" type="submit">应用筛选</button></form>{table}</section>'''


def new_case_page(error: str | None = None, values: dict[str, str] | None = None) -> str:
    values = values or {}
    error_html = f'<div class="form-error">{e(error)}</div>' if error else ""
    def val(name): return e(values.get(name, ""))
    return _page_intro("新建卷宗", "建立贷款案件", "先记录企业、项目和经办责任；材料上传后再由证据支持行业与阶段判断。") + f'''<section class="sheet form-sheet">{error_html}<form class="case-form" method="post" action="/cases/new">
      <div class="form-grid"><label>案件名称<input name="case_name" maxlength="120" value="{val('case_name')}" required></label>
      <label>借款企业<input name="borrower_name" maxlength="160" value="{val('borrower_name')}" required></label>
      <label>项目名称<input name="project_name" maxlength="200" value="{val('project_name')}" required></label>
      <label>企业主行业<input name="primary_industry" maxlength="100" value="{val('primary_industry')}" placeholder="可暂空，待材料定标"></label>
      <label>项目活动<input name="project_activity" maxlength="200" value="{val('project_activity')}" placeholder="例如：风电设施建设"></label>
      <label>责任人<input name="assignee" maxlength="80" value="{val('assignee')}" placeholder="未填写则进入待分配"></label></div>
      <label>备注<textarea name="notes" rows="4" maxlength="1000">{val('notes')}</textarea></label>
      <div class="form-actions"><a class="button" href="/cases">取消</a><button class="button primary" type="submit">建立卷宗</button></div></form></section>'''


def overview_page(view: dict[str, Any]) -> str:
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    classification = view["classification"]
    risk_rows = "".join(_risk_bar(axis) for axis in view["risk_axes"])
    status_counts: dict[str, int] = {}
    for item in view["verification_items"]:
        status_counts[item["status_label"]] = status_counts.get(item["status_label"], 0) + 1
    ordered_statuses = ("证据冲突", "不满足", "无法判断", "待核实", "待补证", "已证明", "属性说明", "不适用")
    status_summary = "".join(
        f'<div><b>{status_counts[label]}</b><span>{e(label)}</span></div>'
        for label in ordered_statuses if status_counts.get(label)
    ) or '<span class="muted-copy">尚未生成核验项</span>'
    unresolved_statuses = {"pending_verification", "cannot_determine", "evidence_conflict", "not_satisfied"}
    priority_items = [item for item in view["verification_items"] if item.get("status") in unresolved_statuses][:3]
    priority_rows = "".join(
        f'''<a href="/cases/{cid}/verification"><span>{e(item.get('rule_id') or '行业核验项')}</span>
        <b>{e(item.get('rule_name') or item.get('requirement_text') or '待核验事项')}</b>
        {_status_badge(item.get('status'), item.get('status_label'))}
        <em>{e(item.get('next_action') or '进入明细确认项目事实与证据')}</em></a>'''
        for item in priority_items
    ) or '<div class="verification-queue-empty"><b>当前没有待处理核验项</b><span>新材料解析或规则装载后，这里会按优先级列出下一步。</span></div>'
    score = view["overall_score"] if view["overall_score"] is not None else "未计算"
    decision_class = "decision-strip" if view["overall_score"] is not None else "decision-strip empty"
    decision_source = (
        '<span class="decision-source">演示测算 · 非真实模型结果</span>'
        if view["is_legacy_demo"]
        else '<span class="decision-source">由当前核验状态实时计算</span>'
    )
    return f'''<section class="case-story">
      <div class="story-step"><span>01</span><p>行业判断</p><b>{e(classification['industry'])}</b><small>{e(classification['project_activity'])}</small><a href="/cases/{cid}/classification#industry-basis">依据</a></div>
      <div class="story-step"><span>02</span><p>分配经办</p><b>{e(classification['manager'])}</b><small>{e(classification['recommended_team'])}</small><a href="/cases/{cid}/classification#manager-basis">分配逻辑</a></div>
      <div class="story-step"><span>03</span><p>企业阶段</p><b>{e(classification['enterprise_stage'])}</b><small>{e(classification['enterprise_stage_basis'])}</small><a href="/cases/{cid}/classification#enterprise-stage-basis">依据</a></div>
      <div class="story-step"><span>04</span><p>项目阶段</p><b>{e(classification['project_stage'])}</b><small>{e(classification['project_stage_basis'])}</small><a href="/cases/{cid}/classification#project-stage-basis">依据</a></div>
    </section>
    <section class="{decision_class}"><div><span>本案复核优先级</span><b>{score}</b><em>{e(view['overall_level'])}</em>{decision_source}</div><p>{e(view['risk_boundary'])}<br>{e(view['risk_standard'])}</p></section>
    <section class="dual-workbench">
      <article class="workbench-block risk-workbench"><header><div><h2>风险识别</h2><span>发现异常并安排人工复核优先级</span></div><a href="/cases/{cid}/risks">进入风险明细</a></header>
        <p class="section-lead">综合规则不满足、跨文件冲突、企业披露文本风险线索与贷后偏离；缺少适用核验项时保持未计算。</p>
        <div class="risk-input-chain" aria-label="风险识别信号来源"><a href="/cases/{cid}/verification"><span>规则核验</span><b>{view['counts']['verification']} 项</b></a><a href="/cases/{cid}/conflicts"><span>跨文件冲突</span><b>{view['counts']['conflicts']} 项</b></a><a href="/cases/{cid}/reading"><span>企业披露筛查</span><b>{e(view['model_state']['label'])}</b></a><a href="/cases/{cid}/monitoring"><span>贷后实绩</span><b>{len(view['bta_indicators'])} 项</b></a></div>
        <div class="risk-ledger">{risk_rows}</div></article>
      <article class="workbench-block verification-workbench"><header><div><h2>辅助核验</h2><span>逐项对齐规则、事实、证据与任务</span></div><a href="/cases/{cid}/verification">进入核验明细</a></header>
        <p class="section-lead">把行业规则要求、项目事实、材料证据和当前状态逐项对齐，回答“核什么、证据在哪、下一步做什么”。</p>
        <div class="verification-summary">{status_summary}</div>
        <dl class="evidence-stats"><div><dt>材料</dt><dd>{view['counts']['documents']}</dd></div><div><dt>证据</dt><dd>{view['counts']['evidence']}</dd></div><div><dt>核验项</dt><dd>{view['counts']['verification']}</dd></div><div><dt>冲突</dt><dd>{view['counts']['conflicts']}</dd></div></dl>
        <div class="verification-queue"><div class="queue-title"><b>当前优先核验事项</b><span>最多显示 3 项</span></div>{priority_rows}</div>
        <a class="reading-entry" href="/cases/{cid}/reading"><b>辅助阅读</b><span>按行业词汇、规则含义与原文位置阅读材料，而不是让客户经理先成为行业专家。</span><i>查看证据原文 →</i></a>
      </article>
    </section>
    <section class="case-close-loop"><header><div><h2>补件与任务闭环</h2><span>补件先形成新证据，再重新核验并进入人工确认；任何一步都不会自动改变授信结论。</span></div><b>{view['counts']['unresolved']} 项待核实 · {view['counts']['tasks']} 项任务</b></header>
      <ol><li><span>补充材料</span><b>{view['counts']['documents']} 份材料在册</b><a href="/cases/{cid}/documents#supplement">登记补件</a></li>
      <li><span>解析与重核</span><b>{view['counts']['evidence']} 条证据在册</b><a href="/cases/{cid}/documents">查看解析</a></li>
      <li><span>人工确认</span><b>{view['counts']['tasks']} 项任务待闭环</b><a href="/tasks">进入任务中心</a></li>
      <li><span>贷后监测</span><b>{len(view['bta_indicators'])} 个指标已定义</b><a href="/cases/{cid}/monitoring">查看监测</a></li>
      <li><span>报告归档</span><b>PDF 与审计记录</b><a href="/cases/{cid}/reports">下载报告</a></li></ol></section>'''


def documents_page(view: dict[str, Any], message: str | None = None, error: str | None = None) -> str:
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    rows = "".join(
        f'''<tr><td><b>{e(row.get('file_name'))}</b><small>{e(row.get('file_type') or row.get('mime_type') or '类型待识别')}</small></td>
        <td>{e(row.get('page_count') or '—')}</td><td><code>{e((row.get('sha256') or '待生成')[:18])}</code></td>
        <td>{_status_badge(row.get('parse_status'), PARSE_STATUS_LABELS.get(row.get('parse_status'), '未解析'))}</td>
        <td>{e({'pypdf': 'PDF文本层', 'plain-text': '文本解析', 'python-docx': 'Word结构解析', 'openpyxl': '表格结构解析', 'html-snapshot': '网页快照解析'}.get((row.get('latest_parse_run') or {}).get('parser_name'), ((row.get('latest_parse_run') or {}).get('parser_name') or '—')))}<small>{e(((row.get('latest_parse_run') or {}).get('error_message') or ''))}</small></td>
        <td><form method="post" action="/cases/{cid}/documents/{quote(str(row.get('doc_id')), safe='')}/parse"><button class="table-action" type="submit">{'重新解析' if row.get('parse_status') in {'parsed','parse_failed','needs_ocr'} else '开始解析'}</button></form></td></tr>'''
        for row in view["documents"]
    )
    table = f'<div class="table-wrap"><table><thead><tr><th>材料名称</th><th>页数</th><th>文件哈希</th><th>解析状态</th><th>最近解析</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else _empty("尚无材料", "上传原件后将记录哈希、解析状态和来源。")
    notice = f'<div class="notice ok">{e(message)}</div>' if message else f'<div class="notice danger">{e(error)}</div>' if error else ""
    trace_rows = "".join(
        f'''<tr><td>{e(row.get('file_name'))}</td><td>{e(row.get('page_number') or '非分页格式')}</td><td>{e({'pdf_page_bbox': 'PDF页码与坐标', 'docx_paragraph': 'Word段落', 'docx_table_row': 'Word表格行', 'xlsx_row': '表格工作表与行', 'html_snapshot_paragraph': '网页快照段落', 'text_lines': '文本行号'}.get(row.get('locator_type'), '待定位'))}</td><td>{e((row.get('raw_excerpt') or '')[:180])}</td></tr>'''
        for row in view["evidence"][:12]
    )
    trace = f'<div class="table-wrap"><table><thead><tr><th>来源材料</th><th>页码</th><th>定位方式</th><th>原文片段</th></tr></thead><tbody>{trace_rows}</tbody></table></div>' if trace_rows else _empty("尚无证据片段", "材料解析成功后，原文、页码或稳定定位信息将在此登记。")
    return _page_intro("卷宗材料", "材料与证据台账", "材料原件、来源、哈希和证据片段统一留痕；只有解析成功的内容才能形成项目事实。") + f'''<section class="sheet">{notice}{table}</section>
    <section class="sheet"><header><div><h2>证据定位预览</h2></div><a href="/cases/{cid}/reading">进入辅助阅读</a></header>{trace}</section>
    <section id="supplement" class="sheet supplement"><header><div><h2>补充材料并触发重新核验</h2></div></header>
      <form method="post" action="/cases/{cid}/supplements" enctype="multipart/form-data">
        <label>材料类型<select name="file_type"><option>项目材料</option><option>环评与合规材料</option><option>合同与凭证</option><option>第三方证明</option><option>结构化数据</option></select></label>
        <label>关联核验事项<input name="related_item" placeholder="例如：G04 合规底线"></label>
        <label class="file-picker">选择文件<input type="file" name="file" required></label>
        <button class="button primary" type="submit">登记补件</button>
      </form><p>登记后文件状态为“已上传”，同时生成待审核任务。系统不会因上传动作自动把待核实改为已证明。</p></section>'''


def classification_page(view: dict[str, Any]) -> str:
    c = view["classification"]
    def basis_badge(value: str, basis: str) -> str:
        unresolved = (
            not value
            or "待" in value
            or any(marker in basis for marker in ("缺少", "尚无", "需", "历史案件"))
        )
        return _status_badge(
            "pending_verification" if unresolved else "satisfied",
            "依据待复核" if unresolved else "依据已定位",
        )

    industry_badge = basis_badge(c["industry"], c["industry_basis"])
    enterprise_badge = basis_badge(c["enterprise_stage"], c["enterprise_stage_basis"])
    project_badge = basis_badge(c["project_stage"], c["project_stage_basis"])
    manager_badge = _status_badge(
        "pending_verification" if c["manager"] == "待分配" else "satisfied",
        "待分配" if c["manager"] == "待分配" else "已分配",
    )
    return _page_intro("案件定标", "行业、经办人与阶段", "先确认项目属于什么行业、由谁负责、处于什么阶段，再调用对应规则和材料清单。") + f'''<section class="classification-ledger">
      <header><span>判断事项</span><span>当前结果</span><span>依据与业务作用</span><span>状态</span></header>
      <article id="industry-basis"><div><b>行业定标</b><small>决定调用哪套行业规则包</small></div><div><h2>{e(c['industry'])}</h2><span>{e(c['project_activity'])}</span></div><p>{e(c['industry_basis'])}<small>企业主营行业不能直接替代本次融资项目活动。</small></p>{industry_badge}</article>
      <article id="manager-basis"><div><b>经办分配</b><small>按行业与项目活动分组</small></div><div><h2>{e(c['manager'])}</h2><span>{e(c['recommended_team'])}</span></div><p>正式业务接入人员与行业团队映射后自动分派。<small>{e(c['bank_rule_state'])}</small></p>{manager_badge}</article>
      <article id="enterprise-stage-basis"><div><b>企业阶段</b><small>调整材料重点与尽调深度</small></div><div><h2>{e(c['enterprise_stage'])}</h2><span>不直接决定授信结果</span></div><p>{e(c['enterprise_stage_basis'])}</p>{enterprise_badge}</article>
      <article id="project-stage-basis"><div><b>项目阶段</b><small>确定当前应核手续与建设事实</small></div><div><h2>{e(c['project_stage'])}</h2><span>贷款阶段：{e(c['loan_stage'])}</span></div><p>{e(c['project_stage_basis'])}</p>{project_badge}</article>
    </section><section class="boundary-note"><b>定标边界</b><p>行业和阶段会改变适用规则、材料重点和贷后指标。没有可定位事实时，系统保持“待判断”，不根据企业名称猜测。</p></section>'''


def risks_page(view: dict[str, Any]) -> str:
    axes = "".join(_risk_bar(axis, detailed=True) for axis in view["risk_axes"])
    radar = _radar_chart(view["risk_axes"])
    detail = "".join(
        f'''<tr><td><b>{e(axis.label)}</b><small>{e(axis.definition)}</small></td><td>{_status_badge(axis.tone, axis.level)}</td>
        <td>{e(axis.basis)}</td><td>{e(axis.score_source)}</td><td class="number">{axis.applicable_count}</td><td class="number">{axis.unresolved_count}</td></tr>'''
        for axis in view["risk_axes"]
    )
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    model = view["model_state"]
    score_notice = ""
    if not any(axis.score is not None for axis in view["risk_axes"]):
        score_notice = '<div class="notice neutral"><b>暂不生成评分</b>：当前没有足够的适用核验项，暂不计算分值。</div>'
    demo_notice = '<div class="notice warn"><b>演示测算</b>：本案历史预置状态只用于展示流程，不作为真实模型运行结果。</div>' if view["is_legacy_demo"] else ""
    return _page_intro("风险工作面", "五维风险识别与核验", "把规则、材料冲突、企业披露风险线索和贷后偏离汇入同一证据链，再安排人工复核优先级。") + f'''{demo_notice}{score_notice}<section class="risk-source-register" aria-label="风险信号来源">
      <a href="/cases/{cid}/verification"><span>规则与合规核验</span><b>{view['counts']['verification']} 项</b><small>规则要求与项目证据</small></a>
      <a href="/cases/{cid}/conflicts"><span>跨文件一致性</span><b>{view['counts']['conflicts']} 项冲突</b><small>金额、范围、指标与版本</small></a>
      <a href="/cases/{cid}/reading"><span>企业披露文本风险筛查（BERT）</span><b>{e(model['label'])}</b><small>企业披露文本筛查：{e(model['detail'])}</small></a>
      <a href="/cases/{cid}/monitoring"><span>贷后实绩偏离</span><b>{len(view['bta_indicators'])} 个指标</b><small>基准、目标、实际同口径比对</small></a>
      <form method="post" action="/cases/{cid}/assess"><button class="button primary" type="submit">运行披露文本筛查与全案核验</button></form>
    </section><section class="method-banner"><b>统一计分标准</b><p>{e(view['risk_standard'])}</p><span>{e(view['risk_boundary'])}</span></section>
    <section class="risk-visual-grid"><article><header><h2>五维风险剖面</h2><span>仅连接已实际计算的五个维度</span></header>{radar}</article><article><header><h2>任务闭环漏斗</h2><span>展示当前任务在人工流程中的分布</span></header>{_task_funnel(view.get('task_funnel') or {})}</article></section>
    <section class="risk-profile"><header><h2>本案风险明细</h2><span>越靠右表示越需要优先复核</span></header>{axes}</section>
    <section class="sheet"><header><div><h2>风险依据台账</h2><span>逐维度说明来源、状态和待处理数量</span></div></header><div class="table-wrap"><table class="risk-basis-table"><thead><tr><th>风险维度</th><th>关注级别</th><th>事实与证据依据</th><th>计算来源</th><th>适用项</th><th>待处理</th></tr></thead><tbody>{detail}</tbody></table></div></section>'''


def _verification_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        evidence_locations = item.get("evidence_locations") or []
        evidence_html = "".join(
            f'<a class="evidence-link" href="/cases/{quote(str(item.get("case_id") or ""), safe="")}/reading#evidence-{quote(str(loc.get("evidence_id") or ""), safe="")}">{e(loc.get("file_name"))} · 第 {e(loc.get("page_number") or "—")} 页</a>'
            for loc in evidence_locations
        ) or '<span class="muted">证据待定位</span>'
        requirements = item.get("required_evidence") or []
        requirement_html = "".join(
            f'<li class="{e(req.get("status") or "pending")}">{e(req.get("label"))}</li>'
            for req in requirements
        )
        source = e(item.get("source_title") or item.get("rule_version") or "来源待登记")
        if item.get("source_url"):
            source = f'<a href="{e(item.get("source_url"))}" target="_blank" rel="noreferrer">{source}</a>'
        rows.append(f'''<tr><td><b>{e(item.get('rule_id') or '行业核验项')}</b>{_mock_tag(item.get('is_mock'))}<small>{e(item.get('rule_name') or item.get('rule_module') or '')}</small></td>
        <td><p>{e(item.get('requirement_text') or item.get('rule_requirement') or '要求待配置')}</p><small>为什么要核：{e(item.get('why_verify') or '待补充')}</small></td>
        <td>{e(item.get('fact_summary') or '项目事实待提取')}<small>客户经理应看：{e(item.get('customer_manager_focus') or '核对材料原文与版本')}</small></td>
        <td>{evidence_html}<small>{e(item.get('source_locator') or '')} · {source}</small>{f'<ul class="requirement-list">{requirement_html}</ul>' if requirement_html else ''}</td>
        <td>{_status_badge(item.get('status'), item.get('status_label'))}</td><td>{e(item.get('next_action') or '无需当前动作')}</td></tr>''')
    return "".join(rows)


def verification_page(view: dict[str, Any]) -> str:
    rows = _verification_rows(view["verification_items"])
    content = f'<div class="table-wrap"><table class="verification-table"><thead><tr><th>规则 / 指标</th><th>核验要求</th><th>项目事实</th><th>证据与定位</th><th>状态</th><th>下一步</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else _empty("尚未形成核验矩阵", "完成行业定标并装载适用规则后生成。")
    return _page_intro("辅助核验工作面", "规则—事实—证据矩阵", "不是数材料份数，而是逐项说明核什么、什么事实已经找到、由哪段证据支持、还需做什么。") + f'''<section class="sheet coverage-sheet"><header><div><h2>覆盖热力图</h2><span>规则装载后，直接显示事实、证据和任务的缺口</span></div></header>{_coverage_heatmap(view.get('verification_coverage') or {})}</section><section class="sheet matrix-sheet">{content}</section>
    <section class="boundary-note"><b>银行内部规则</b><p>{e(view['classification']['bank_rule_state'])}。公开规则用于演示行业核验能力，不能替代银行准入、额度、尽调和审批制度。</p></section>'''


def conflicts_page(view: dict[str, Any]) -> str:
    rows = "".join(
        f'''<tr><td><b>{e(row.get('field_name') or '未命名字段')}</b><small>{e(row.get('conflict_type'))}</small></td><td>{e(row.get('raw_value_a') or '—')}</td><td>{e(row.get('raw_value_b') or '—')}</td>
        <td>{e(row.get('difference_value') or '—')} {e(row.get('difference_unit') or '')}</td><td>{e(row.get('comparison_method') or '待确认比较口径')}</td><td>{_status_badge('evidence_conflict', '待人工核实')}</td></tr>'''
        for row in view["conflicts"]
    )
    comparisons = "".join(
        f'''<article class="conflict-compare"><header><div><b>{e(row.get('field_name') or '冲突字段')}</b><span>{e(row.get('comparison_method') or '比较口径待确认')}</span></div>{_status_badge('evidence_conflict', '待人工核实')}</header><div>
        <section><h3>{e((row.get('evidence_a') or {}).get('file_name') or '材料 A')} · 第 {e((row.get('evidence_a') or {}).get('page_number') or '—')} 页</h3><blockquote>{e((row.get('evidence_a') or {}).get('excerpt') or row.get('raw_value_a') or '原文待定位')}</blockquote><strong>{e(row.get('raw_value_a') or '—')}</strong></section>
        <section><h3>{e((row.get('evidence_b') or {}).get('file_name') or '材料 B')} · 第 {e((row.get('evidence_b') or {}).get('page_number') or '—')} 页</h3><blockquote>{e((row.get('evidence_b') or {}).get('excerpt') or row.get('raw_value_b') or '原文待定位')}</blockquote><strong>{e(row.get('raw_value_b') or '—')}</strong></section></div></article>'''
        for row in view["conflicts"][:8]
    )
    content = f'<div class="table-wrap"><table><thead><tr><th>冲突字段</th><th>材料 A</th><th>材料 B</th><th>差异值</th><th>计算口径</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else _empty("未发现已登记冲突", "没有冲突记录不等于没有风险，只表示当前尚无可比较的跨文件字段冲突。")
    return _page_intro("跨文件核对", "冲突台账", "同名字段先确认项目范围、期间和单位是否可比，再计算差异；系统不自行认定哪份文件正确。") + f'<section class="sheet">{content}</section>{f"<section class=\"conflict-stack\">{comparisons}</section>" if comparisons else ""}'


def reading_page(view: dict[str, Any]) -> str:
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    evidence_cards = "".join(
        f'''<article class="excerpt" id="evidence-{e(row.get('evidence_id') or '')}"><header><b>{e(row.get('file_name'))}</b><span>第 {e(row.get('page_number') or '—')} 页</span></header>
        <blockquote>{e(row.get('raw_excerpt') or '该证据片段尚未写入可展示原文；请回到原件定位核对。')}</blockquote><footer>{_status_badge(row.get('verification_status'), '证据状态')}</footer></article>'''
        for row in view["evidence"][:12]
    ) or _empty("暂无可展示原文", "当前只保存了结构化核验结果，原文阅读待材料解析后启用。")
    term_rows = view.get("term_cards") or []
    terms = "".join(
        f'<details><summary>{e(row.get("term"))}{_mock_tag(row.get("is_mock"))}</summary><p>{e(row.get("definition_text"))}</p><small>{e(row.get("usage_note") or "核对材料中的实际用法和统计口径。")}</small></details>'
        for row in term_rows
    ) or _empty("行业术语卡待装载", "完成行业定标后，将从对应行业规则包动态载入。")
    guides = "".join(
        f'''<article><header><b>{e(item.get('rule_name') or item.get('rule_id') or '行业核验项')}</b>{_mock_tag(item.get('is_mock'))}</header><p><strong>为什么要核</strong>{e(item.get('why_verify') or '待建立业务说明')}</p><p><strong>客户经理看什么</strong>{e(item.get('customer_manager_focus') or '对照规则要求查看项目事实与原文证据')}</p><small>{e(item.get('source_locator') or item.get('source_title') or '')}</small></article>'''
        for item in view.get("verification_items", [])[:12]
    ) or _empty("暂无阅读任务", "核验项生成后，每项都会说明“为什么核”和“应该看什么”。")
    model = view["model_state"]
    model_action = f'''<form method="post" action="/cases/{cid}/models/green-profile/run"><button class="button" type="submit">运行企业披露文本筛查</button></form>'''
    return _page_intro("材料阅读助手", "辅助阅读与证据定位", "把新行业术语、规则要求和材料原文放在同一阅读上下文，帮助客户经理理解，不替客户经理作判断。") + f'''<section class="model-state"><div><span>企业披露文本筛查</span><b>{e(model['label'])}</b><p>{e(model['detail'])}</p></div>{model_action}</section>
    <section class="reading-layout"><aside><h2>本案行业术语</h2>{terms}</aside><div><h2>证据原文</h2>{evidence_cards}</div></section><section class="sheet reading-guide"><header><div><h2>客户经理阅读任务</h2><span>每项从行业规则包动态装载</span></div></header><div>{guides}</div></section><section class="sheet evidence-source-sheet"><header><div><h2>证据来源分布</h2><span>只统计已实际定位的原文片段</span></div></header>{_evidence_distribution(view.get('evidence_distribution') or {})}</section>'''


def monitoring_page(view: dict[str, Any]) -> str:
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    evaluation_by_indicator = {str(row.get("indicator_id")): row for row in view.get("postloan_evaluations", [])}
    panels = []
    for entry in view["bta_observations"]:
        indicator = entry["indicator"]
        series = entry["series"]
        values = []
        for code, label in (("baseline", "基准"), ("target", "目标"), ("actual", "实际")):
            row = series.get(code) or {}
            # bta_observations stores values as raw_value / normalized_value.
            # Keep the legacy aliases as fallbacks so historical databases still
            # render after an in-place upgrade.
            value = row.get("raw_value")
            if value in (None, ""):
                value = row.get("normalized_value")
            if value in (None, ""):
                value = row.get("value_raw")
            if value in (None, ""):
                value = row.get("value_normalized")
            values.append((label, value if value not in (None, "") else "—"))
        numeric = []
        for _, value in values:
            try:
                numeric.append(float(str(value).replace(",", "")))
            except (TypeError, ValueError):
                numeric.append(None)
        maximum = max([abs(value) for value in numeric if value is not None] + [1])
        bars = "".join(
            f'<div><span>{e(label)}</span><i><em style="height:{round(abs(numeric[index]) / maximum * 100) if numeric[index] is not None else 0}%"></em></i><b>{e(value)}</b></div>'
            for index, (label, value) in enumerate(values)
        )
        evaluation = evaluation_by_indicator.get(str(indicator.get("indicator_id"))) or {}
        evaluation_text = {
            "comparable": "口径一致，已完成偏离评估",
            "missing_series": "缺少基准、目标或实际值",
            "basis_mismatch": "单位或统计口径不一致",
        }.get(evaluation.get("comparability_status"), "尚未评估同口径可比性")
        panels.append(f'''<article class="bta-panel"><header><div><p>{e(indicator.get('indicator_name') or '未命名指标')}{_mock_tag(indicator.get('is_mock'))}</p><span>{e(indicator.get('indicator_category') or '指标类别待确认')} · {e(indicator.get('unit') or '单位待确认')}</span></div>{_status_badge(indicator.get('status'), '待核实' if indicator.get('is_mock') else indicator.get('status') or '待监测')}</header>
        <div class="bta-chart">{bars}</div><p>{e(evaluation_text)}{f' · 偏离率 {e(evaluation.get("target_actual_deviation_ratio"))}' if evaluation.get('target_actual_deviation_ratio') else ''}</p>
        <small>统计口径：{e(indicator.get('statistical_scope') or '待核对')} · 频率：{e(indicator.get('reporting_frequency') or '待设置')} · 边界：{e(indicator.get('measurement_boundary') or '待设置')}</small></article>''')
    content = "".join(panels) or _empty("尚未形成可比的贷后序列", "需先定义同口径的基准值、承诺目标和实际值，再计算偏离。")
    actions = f'''<div class="monitor-actions"><form method="post" action="/cases/{cid}/monitoring/load"><button class="button" type="submit">从行业包装载贷后指标</button></form><form method="post" action="/cases/{cid}/monitoring/evaluate"><button class="button primary" type="submit">检查同口径与偏离</button></form></div>'''
    return _page_intro("持续监测", "B-T-A 贷后监测", "把贷中基准、融资承诺目标与贷后实际表现按同一口径持续比对，偏离只触发复核，不直接处罚。", actions) + f'<section class="bta-grid">{content}</section>'


def reports_page(view: dict[str, Any], *, message: str = "", error: str = "") -> str:
    case = view["case"]
    cid = quote(str(case["case_id"]), safe="")
    flash = ""
    if message:
        flash = f'<div class="notice ok">{e(message)}</div>'
    elif error:
        flash = f'<div class="notice danger">{e(error)}</div>'
    audit_rows = "".join(
        f'<tr><td>{e((row.get("occurred_at") or "")[:19].replace("T", " "))}</td><td>{e(AUDIT_ACTION_LABELS.get(row.get("action"), "案件操作"))}</td><td>{e(row.get("actor") or "系统")}</td><td><code>{e(row.get("file_hash") or "—")}</code></td></tr>'
        for row in view["audits"][:20]
    )
    audits = f'<div class="table-wrap"><table><thead><tr><th>时间</th><th>动作</th><th>执行者</th><th>文件哈希</th></tr></thead><tbody>{audit_rows}</tbody></table></div>' if audit_rows else _empty("暂无审计记录", "案件动作将在此留痕。")
    snapshot_rows = "".join(
        f'''<tr><td><b>第 {int(row.get('snapshot_revision') or 0)} 版</b></td><td>{e((row.get('generated_at') or '')[:19].replace('T', ' '))}</td><td>{_status_badge(row.get('status'), '已归档')}</td><td><code>{e((row.get('snapshot_hash') or '')[:16])}…</code></td><td><a href="/cases/{cid}/reports/versions/{int(row.get('snapshot_revision') or 0)}.pdf">PDF</a> · <a href="/cases/{cid}/reports/versions/{int(row.get('snapshot_revision') or 0)}.json">数据包</a></td></tr>'''
        for row in (view.get("report_snapshots") or [])
    )
    snapshots = f'<div class="table-wrap"><table><thead><tr><th>版本</th><th>生成时间</th><th>状态</th><th>快照哈希</th><th>归档文件</th></tr></thead><tbody>{snapshot_rows}</tbody></table></div>' if snapshot_rows else _empty("尚无冻结版本", "完成补件重算并经人工审核后，系统将保留不可覆盖的报告版本。")
    review_forms = "".join(
        f'''<article><div><b>{e(TASK_TYPE_LABELS.get(row.get('task_type'), '人工复核任务'))}</b><span>{e(row.get('trigger_reason') or '请复核补件后的核验结果')}</span><small>关闭条件：{e(row.get('closure_condition') or '授权人员确认后关闭')}</small></div><form method="post" action="/cases/{cid}/tasks/{quote(str(row.get('task_id') or ''), safe='')}/review"><label>审核意见<input name="reason" required placeholder="填写通过或退回依据"></label><button class="button" name="decision" value="reject" type="submit">退回补充</button><button class="button primary" name="decision" value="approve" type="submit">确认并冻结报告</button></form></article>'''
        for row in (view.get("tasks") or []) if row.get("status") == "pending_review"
    ) or _empty("暂无待审核任务", "补件重算完成后，任务会进入待审核，不能由系统自动关闭。")
    decision_rows = "".join(
        f'''<tr><td>{e((row.get('decided_at') or '')[:19].replace('T', ' '))}</td><td>{e(row.get('actor') or '人工审核员')}</td><td>{e('确认通过' if row.get('decision') == 'approved' else '退回补充' if row.get('decision') == 'rejected' else row.get('decision') or '待确认')}</td><td>{e(row.get('reason') or '—')}</td></tr>'''
        for row in (view.get("human_decisions") or [])
    )
    decisions = f'<div class="table-wrap"><table><thead><tr><th>时间</th><th>审核人</th><th>决定</th><th>依据</th></tr></thead><tbody>{decision_rows}</tbody></table></div>' if decision_rows else _empty("暂无人工决定", "系统不会代替审批人员形成授信结论。")
    return _page_intro("交付与留痕", "报告与审计", "报告固化当前规则版本、证据状态、风险复核优先级和待办任务，便于人工复核与归档。") + f'''{flash}<section class="report-actions"><article><h2>{e(case.get('project_name'))}</h2><span>可阅读报告与结构化数据包均不构成授信审批结论。</span><nav><a class="button primary" href="/cases/{cid}/reports/download.pdf">下载核验报告</a><a class="button" href="/cases/{cid}/reports/download.json">下载结构化数据</a></nav></article>
      <dl><div><dt>风险维度</dt><dd>5</dd></div><div><dt>核验项</dt><dd>{view['counts']['verification']}</dd></div><div><dt>待处理</dt><dd>{view['counts']['unresolved']}</dd></div><div><dt>证据冲突</dt><dd>{view['counts']['conflicts']}</dd></div></dl></section>
      <section class="sheet review-queue"><header><div><h2>人工审核与版本冻结</h2><span>补件只触发重算；只有授权人员确认后任务关闭并生成新版本。</span></div></header>{review_forms}</section>
      <section class="sheet"><header><div><h2>报告版本历史</h2><span>旧版本保留，不被新补件覆盖。</span></div></header>{snapshots}</section>
      <section class="sheet"><header><div><h2>人工决定记录</h2></div></header>{decisions}</section>
      <section class="sheet"><header><div><h2>可审计操作时间线</h2></div></header>{audits}</section>'''


def tasks_page(tasks: list[dict[str, Any]]) -> str:
    rows = "".join(
        f'<tr><td><b>{e(TASK_TYPE_LABELS.get(row.get("task_type"), "人工复核任务"))}</b></td><td><a href="/cases/{quote(str(row.get("case_id")), safe="")}/overview">{e(row.get("case_label") or "查看关联案件")}</a></td><td>{e(row.get("trigger_reason") or "—")}</td><td>{e(row.get("assignee") or "待分配")}</td><td>{_status_badge(row.get("status"))}</td><td>{e(row.get("due_at") or "—")}</td></tr>'
        for row in tasks
    )
    content = f'<div class="table-wrap"><table><thead><tr><th>任务</th><th>案件</th><th>触发原因</th><th>负责人</th><th>状态</th><th>截止时间</th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else _empty("暂无任务", "核验待补证、证据冲突和贷后偏离会形成可跟踪任务。")
    return _page_intro("闭环管理", "任务中心", "补件不能直接关闭任务，必须经过重新核验、待审核和授权人员确认。") + f'<section class="sheet">{content}</section>'


def rules_page(view: dict[str, Any]) -> str:
    """National-industry-first master data browser."""
    counts = view.get("counts") or {}
    selection = view.get("selection") or {}

    def node_href(row: dict[str, Any]) -> str:
        level = row.get("level")
        code = quote(str(row.get("code") or ""), safe="")
        if level == "section":
            return f"/rules?section={code}"
        if level == "division":
            return f"/rules?section={quote(str(row.get('section_code') or ''), safe='')}&division={code}"
        if level == "group":
            return f"/rules?section={quote(str(row.get('section_code') or ''), safe='')}&division={quote(str(row.get('parent_code') or ''), safe='')}&group={code}"
        return f"/rules?class={code}"

    def node_list(rows: list[dict[str, Any]], selected: str, empty_text: str) -> str:
        if not rows:
            return f'<p class="taxonomy-empty">{e(empty_text)}</p>'
        items = []
        for row in rows:
            active = " selected" if str(row.get("code")) == selected else ""
            build = ""
            if row.get("level") == "class":
                label = {
                    "depth_public_sources": "已建公开规则包",
                    "partial_public_sources": "部分建设",
                    "pending": "待建设",
                    "base_only": "仅基础行业信息 / 深度规则包待建设",
                }.get(row.get("build_status"), "待建设")
                build = f'<small class="industry-build-state">{e(label)}</small>'
            items.append(f'<a class="taxonomy-node{active}" href="{node_href(row)}"><b>{e(row.get("code"))}</b><span>{e(row.get("name"))}</span>{build}</a>')
        return "".join(items)

    section_nodes = node_list(view.get("sections") or [], selection.get("section") or "", "暂无门类")
    division_nodes = node_list(view.get("divisions") or [], selection.get("division") or "", "请先选择门类")
    group_nodes = node_list(view.get("groups") or [], selection.get("group") or "", "请先选择大类")
    class_nodes = node_list(view.get("classes") or [], selection.get("class_code") or "", "请先选择中类")

    search_results = ""
    if view.get("query"):
        result_rows = "".join(
            f'<tr><td><a href="{node_href(row)}"><b>{e(row.get("code"))}</b></a></td><td>{e(row.get("name"))}</td><td>{e({"section":"门类","division":"大类","group":"中类","class":"小类"}.get(row.get("level"), row.get("level")))}</td><td>{e(row.get("official_description") or "官方注释未单列")}</td></tr>'
            for row in view.get("search_rows") or []
        )
        search_results = f'<section class="sheet industry-search-results"><header><div><h2>搜索结果</h2><span>关键词：{e(view.get("query"))}</span></div></header><div class="table-wrap"><table><thead><tr><th>代码</th><th>行业名称</th><th>层级</th><th>官方说明</th></tr></thead><tbody>{result_rows or '<tr><td colspan="4">未找到匹配行业</td></tr>'}</tbody></table></div></section>'

    profile = dict(view.get("profile") or {})
    profile_html = ""
    if profile:
        density = profile.get("density_assessment") or {}
        is_density = profile.get("assessment_source") == "phase36_density"
        status_label = {
            "depth_public_sources": "已建公开规则包",
            "partial_public_sources": "公开资料部分建设",
            "pending": "待建设",
            "base_only": "仅基础行业信息 / 深度规则包待建设",
        }.get(profile.get("build_status"), "待建设")
        completion = int(profile.get("completion_percent") or 0)
        review_label = (
            "来源合格性与密度门槛已重算"
            if is_density else
            "已完成模块覆盖复核" if profile.get("coverage_review_status") == "reviewed" else "待人工覆盖复核"
        )
        missing = "".join(f"<li>{e(item)}</li>" for item in profile.get("missing_modules") or [])
        sources_by_id = {row["source_id"]: row for row in profile.get("sources") or []}

        threshold_status = {
            "met": "明文数值阈值达到门槛",
            "not_required": "未设置统一数值阈值硬门槛",
            "public_channel_not_obtained": "公开渠道未取得统一数值阈值",
            "insufficient": "明文数值阈值数量不足",
        }.get(density.get("numeric_threshold_status"), "尚未进行数值阈值专项评估")
        target_tier = {
            "first_tier": "第一梯队·深度建设",
            "second_tier": "第二梯队·中等建设",
            "base": "基础行业信息",
        }.get(density.get("target_tier"), "公开内容覆盖评估")
        density_meta = ""
        if is_density:
            density_meta = f'''
            <section class="density-assessment-meta" aria-label="规则密度评估依据">
              <div><span>建设梯队</span><b>{e(target_tier)}</b></div>
              <div><span>合格官方来源</span><b>{int(density.get("official_source_count") or 0)} 份</b></div>
              <div><span>模拟条目</span><b>{int(density.get("simulation_count") or 0)} 条 · 不计入</b></div>
              <div><span>数值阈值状态</span><b>{e(threshold_status)}</b></div>
              <div><span>最近评估</span><b>{e(density.get("assessed_at") or "尚未记录")}</b></div>
            </section>'''

        gray_package_notice = ""
        if profile.get("build_status") in {"base_only", "pending"}:
            gray_title = (
                "仅基础行业信息 / 深度规则包待建设"
                if profile.get("build_status") == "base_only" else
                "深度规则包待建设 / 当前未达到公开来源密度门槛"
            )
            gray_package_notice = f'''
            <section class="industry-package-gap" role="status">
              <b>{e(gray_title)}</b>
              <span>当前页面只提供行业分类与已登记公开信息，不能据此形成项目核验结论。</span>
              <ul>{missing or '<li>流程、设备、标准、指标、手续、证据、风险、术语和贷后模块待建设</li>'}</ul>
            </section>'''

        def proof(row):
            source = sources_by_id.get(row.get("source_id"), {})
            title = source.get("source_name") or "来源未登记"
            link = f'<a href="{e(source.get("source_url"))}" target="_blank" rel="noreferrer">{e(title)}</a>' if source.get("source_url") else e(title)
            return f'<small class="industry-proof">{link} · {e(row.get("source_page") or row.get("source_locator") or "原文位置待补")}</small>'

        module_rows = "".join(
            f'<tr class="{"module-gap" if row.get("status") in {"gap", "missing", "unqualified"} else ""}">'
            f'<td>{e(row.get("label"))}</td>'
            f'<td>{int(row.get("raw_count") or 0)}</td>'
            f'<td><b>{int(row.get("qualified_count") or 0)}</b></td>'
            f'<td>{e(row.get("required_count") if row.get("required_count") is not None else "不设统一门槛" if is_density else "待密度评估")}</td>'
            f'<td>{max(int(row.get("required_count") or 0) - int(row.get("qualified_count") or 0), 0) if row.get("required_count") is not None else "—"}</td>'
            f'<td>{e(row.get("reason"))}</td></tr>'
            for row in (profile.get("modules") or {}).values()
        )
        module_explainer = (
            "按 Phase 3.6 密度门槛逐项验收。已登记不等于合格；只有来源、原件哈希、适用范围、原文定位、字段和业务映射均通过校验才计入。模拟条目永不计入。"
            if is_density else
            "按公开内容模块覆盖逐项验收；分类树和映射数量不加分。该评估尚未启用 Phase 3.6 密度门槛。"
        )
        module_table = f'<section class="sheet"><header><div><h2>内容逐项验收</h2><span>{e(module_explainer)}</span></div></header><div class="table-wrap"><table><thead><tr><th>内容模块</th><th>已登记</th><th>来源合格</th><th>密度门槛</th><th>缺口</th><th>依据与缺口原因</th></tr></thead><tbody>{module_rows}</tbody></table></div></section>'
        # Keep legacy/mapping-generated entries visible for audit, not in the core work list.
        unreviewed = []
        for key in ("standards", "indicators", "thresholds", "permits", "documents", "evidence", "risks", "postloan", "terms"):
            all_rows = profile.get(key) or []
            for row in all_rows:
                if row.get("scope_status") != "core":
                    label = next((row.get(k) for k in ("indicator_name", "threshold_text", "standard_name", "permit_name", "document_name", "evidence_object", "risk_title", "term") if row.get(k)), "已登记条目")
                    unreviewed.append(f'<tr class="module-gap"><td>{e(label)}</td><td>{"相邻可能活动" if row.get("scope_status")=="adjacent" else "核心适用性尚未复核"}</td><td>{proof(row)}</td></tr>')
            profile[key] = [row for row in all_rows if row.get("scope_status") == "core"]
        archive_html = '<details class="sheet industry-audit-archive"><summary>其他已登记内容（不计入当前核心内容覆盖）</summary><div class="table-wrap"><table><thead><tr><th>内容</th><th>未计入原因</th><th>来源</th></tr></thead><tbody>' + ''.join(unreviewed) + '</tbody></table></div></details>' if unreviewed else ''
        knowledge_html = '<section class="industry-requirements">' + ''.join(
            '<article><h3>' + title + '</h3>' + (''.join(f'<div><b>{e(row.get("title"))}</b><p>{e(row.get("content"))}</p>{proof(row)}</div>' for row in profile.get("knowledge") or [] if row.get("module")==key and row.get("scope_status")=="core") or '<p class="taxonomy-empty">公开内容待建设，不自行填充。</p>') + '</article>'
            for key, title in (("process", "典型流程"), ("equipment", "核心设备与设施"), ("route", "技术路线"))
        ) + '</section>'

        mapping_rows = "".join(
            f'<tr class="{"module-gap" if row.get("relationship_role")!="core" else ""}"><td><b>{e("绿色目录属性" if row.get("mapping_domain")=="green_catalog" else "地方转型规则")}</b><small>{e(row.get("applicable_region") or "—")}</small></td><td>{e(row.get("project_activity_name"))}<small>{e({"core":"核心映射","adjacent":"相邻可能活动"}.get(row.get("relationship_role"),"候选映射待核查"))}</small></td><td>{e({"direct":"直接对应","partial":"部分对应","conditional":"条件对应","cannot_directly_map":"无法直接对应"}.get(row.get("mapping_type"), row.get("mapping_type")))}</td><td>{e(row.get("applicable_conditions") or "原文未设附加条件")}<small>{e(row.get("non_applicable_conditions") or "")}</small></td><td>{e(row.get("evidence_requirement") or "核对项目活动边界")}</td><td>{proof(row)}</td></tr>'
            for row in profile.get("mappings") or []
        )
        mapping_table = f'<div class="table-wrap"><table class="industry-detail-table"><thead><tr><th>属性映射</th><th>项目活动</th><th>映射方式</th><th>适用条件</th><th>证据对象</th><th>来源</th></tr></thead><tbody>{mapping_rows}</tbody></table></div>' if mapping_rows else _empty("未查询到目录映射", "该状态不代表项目不符合，只表示当前公开规则库尚无对应关系。")

        standard_rows = "".join(
            f'<tr><td><b>{e(row.get("standard_no") or "编号未识别")}</b></td><td>{e(row.get("standard_name"))}{proof(row)}</td><td>{e(row.get("applicability"))}</td><td>{_status_badge("cannot_determine", "仅官方摘要/引用，全文待获取" if row.get("full_text_status") != "full_text_obtained" else "全文已获取（效力另核）")}<small>{e(row.get("public_scope_note") or "")}</small></td></tr>'
            for row in profile.get("standards") or []
        )
        indicator_rows = "".join(
            f'<tr><td><b>{e(row.get("indicator_name"))}</b>{proof(row)}</td><td>{e(row.get("definition_text"))}</td><td>{e(row.get("formula_text") or "原文未给出统一公式")}</td><td>{e(row.get("unit") or "按原文口径")}</td><td>{e("政策明文" if row.get("derivation_type")=="policy_explicit" else "来源衍生核验建议")}</td></tr>'
            for row in profile.get("indicators") or []
        )
        threshold_rows = "".join(
            f'<tr><td>{e(row.get("threshold_text"))}<small>{e("明文数值：" + str(row.get("threshold_value")) + " " + str(row.get("unit") or "") if row.get("threshold_kind")=="explicit_numeric" else "文字性要求，不计明文数值阈值")}</small></td><td>{e(row.get("applicable_region") or "按来源适用范围")}</td><td>{proof(row)}</td></tr>'
            for row in profile.get("thresholds") or []
        )

        requirement_groups = (
            ("审批与许可", profile.get("permits") or [], "permit_name", "requirement_text"),
            ("申请材料要求", profile.get("documents") or [], "document_name", "requirement_text"),
            ("证据要求", profile.get("evidence") or [], "evidence_object", "requirement_text"),
        )
        requirement_html = "".join(
            f'<article><h3>{e(title)}</h3>' + ("".join(f'<div><b>{e(row.get(name_key))}</b><p>{e(row.get(text_key))}</p><small>{e("政策明文" if row.get("derivation_type")=="policy_explicit" else "来源衍生的核验建议" if row.get("derivation_type")=="source_derived" else "按条款适用范围核验")} · {e(row.get("applicable_stage") or "依条款和项目阶段")}</small>{proof(row)}</div>' for row in rows) if rows else f'<p class="taxonomy-empty">{e("公开来源尚未结构化到该行业的专属要求，不自行生成清单。")}</p>') + '</article>'
            for title, rows, name_key, text_key in requirement_groups
        )

        risk_rows = "".join(
            f'<tr><td><b>{e(row.get("risk_category"))}</b></td><td>{e(row.get("risk_title"))}{proof(row)}</td><td>{e(row.get("review_focus") or "回到原文与证据复核")}</td><td>{e("政策明文" if row.get("derivation_type")=="policy_explicit" else "来源衍生，非正式规则")}</td></tr>'
            for row in profile.get("risks") or []
        )
        postloan_rows = "".join(
            f'<tr><td><b>{e(row.get("indicator_name"))}</b>{proof(row)}</td><td>{e(row.get("definition_text"))}<small>{e("政策明文" if row.get("derivation_type")=="policy_explicit" else "来源衍生的贷后核验建议，非银行内部规定")}</small></td><td>{e(row.get("frequency") or "按来源或合同确定")}</td><td>{e(row.get("evidence_object") or "—")}</td></tr>'
            for row in profile.get("postloan") or []
        )
        term_rows = "".join(
            f'<div><b>{e(row.get("term"))}</b><p>{e(row.get("definition_text"))}</p><small>{e(row.get("usage_note") or "")}</small>{proof(row)}</div>'
            for row in profile.get("terms") or []
        )
        source_rows = "".join(
            f'<tr><td><b>{e(row.get("source_name"))}</b><small>{e(row.get("issuer"))}</small></td><td>{e(row.get("version_label") or "—")}</td><td>{e(row.get("effective_at") or "未登记")}</td><td>{e(row.get("expires_at") or "未登记")}</td><td>{_status_badge("attribute_only" if row.get("availability_status")=="full_text_obtained" else "cannot_determine", "官方全文已获取" if row.get("availability_status")=="full_text_obtained" else "历史/公开信息不完整")}</td><td>{e(row.get("relation_note") or ("由 " + row.get("replaced_by_name") + " 替代" if row.get("replaced_by_name") else "当前未登记替代关系"))}</td><td>{f"<a href='{e(row.get('source_url'))}' target='_blank' rel='noreferrer'>查看官方来源</a>" if row.get("source_url") else "本地历史原件"}<small><code>{e((row.get("sha256") or "")[:16])}…</code></small></td></tr>'
            for row in profile.get("sources") or []
        )

        profile_html = f'''
        <section class="industry-profile-head">
          <div><span>GB/T 4754—2017 小类</span><h2>{e(profile.get("code"))} {e(profile.get("name"))}</h2><p>{e(profile.get("official_description") or "官方注释未单列。")}</p></div>
          <dl><div><dt>规则包状态</dt><dd class="{"module-gap" if profile.get("build_status") in ("base_only", "pending") else ""}">{e(status_label)}</dd></div><div><dt>{"公开规则密度" if is_density else "公开内容模块覆盖"}</dt><dd>{completion}% · {e(review_label)}</dd></div><div><dt>银行内部规则</dt><dd>未接入·无法判断</dd></div></dl>
        </section>
        {gray_package_notice}
        {density_meta}
        <section class="industry-boundary-grid">
          <article><h3>官方定义</h3><p>{e(profile.get("industry_definition") or "官方未单列定义。")}</p></article>
          <article><h3>包含活动</h3><p>{e(profile.get("included_activities") or "官方注释未单列。")}</p></article>
          <article><h3>不包含活动</h3><p>{e(profile.get("excluded_activities") or "官方注释未单列。")}</p></article>
        </section>
        <section class="industry-completeness"><div><b>{"公开规则密度完成度" if is_density else "行业规则包完成度"}</b><span>这是公开来源建设进度，不是项目合规评分，也不表示资料齐全。</span></div><i><b style="width:{completion}%"></b></i><ul>{missing or '<li>当前公开来源密度门槛已达到</li>'}</ul></section>
        {module_table}
        {knowledge_html}
        {archive_html}
        <section class="sheet"><header><div><h2>项目活动与政策属性映射</h2><span>先定行业，再查看活动映射；一个行业可对应多个目录活动。</span></div></header>{mapping_table}</section>
        <section class="sheet"><header><div><h2>技术标准与指标</h2><span>标准引用、指标口径和明文阈值分开管理。</span></div></header><div class="industry-tabs-grid"><article><h3>引用标准</h3>{f'<div class="table-wrap"><table><thead><tr><th>标准号</th><th>名称</th><th>适用性</th><th>全文状态</th></tr></thead><tbody>{standard_rows}</tbody></table></div>' if standard_rows else _empty("暂无标准引用", "不自行补写标准。")}</article><article><h3>指标定义</h3>{f'<div class="table-wrap"><table><thead><tr><th>指标</th><th>定义/要求</th><th>公式</th><th>单位</th><th>属性</th></tr></thead><tbody>{indicator_rows}</tbody></table></div>' if indicator_rows else _empty("暂无行业指标", "公开来源未明确时保持空缺。")}</article><article><h3>明文阈值/准入要求</h3>{f'<div class="table-wrap"><table><thead><tr><th>原文要求</th><th>地域</th><th>位置</th></tr></thead><tbody>{threshold_rows}</tbody></table></div>' if threshold_rows else _empty("暂无明文阈值", "不将模型设计值冒充政策阈值。")}</article></div></section>
        <section class="industry-requirements">{requirement_html}</section>
        <section class="sheet"><header><div><h2>审查重点与贷后指标</h2><span>风险提示与正式政策要求明确区分。</span></div></header><div class="industry-tabs-grid"><article><h3>行业风险点</h3>{f'<div class="table-wrap"><table><thead><tr><th>类别</th><th>风险点</th><th>复核重点</th><th>属性</th></tr></thead><tbody>{risk_rows}</tbody></table></div>' if risk_rows else _empty("暂无已登记风险点", "不从相似行业拷贝风险。")}</article><article><h3>贷后持续跟踪</h3>{f'<div class="table-wrap"><table><thead><tr><th>指标</th><th>定义</th><th>频率</th><th>证据对象</th></tr></thead><tbody>{postloan_rows}</tbody></table></div>' if postloan_rows else _empty("暂无行业专属贷后指标", "后续项目不得自动套用通用阈值。")}</article></div></section>
        <section class="sheet"><header><div><h2>专业术语卡</h2><span>用于辅助客户经理阅读，不代替原文核验。</span></div></header><div class="term-card-list">{term_rows or _empty("暂无术语卡", "等待权威来源补充。")}</div></section>
        <section class="sheet"><header><div><h2>来源、版本与效力</h2><span>每个指标、阈值和映射都可返回此处的官方来源。</span></div></header><div class="table-wrap"><table><thead><tr><th>来源文件</th><th>版本</th><th>生效</th><th>失效</th><th>全文状态</th><th>替代关系</th><th>溯源</th></tr></thead><tbody>{source_rows}</tbody></table></div></section>
        <section class="bank-boundary"><b>银行内部规则</b><span>{e(profile.get("bank_rule_status") or "银行内部规则未接入，无法判断。")}</span></section>'''

    intro = _page_intro(
        "GB/T 4754—2017",
        "行业规则库",
        "以国家标准行业树为主索引，再在行业小类下挂载技术标准、指标、证据要求和政策属性映射。",
    )
    return intro + f'''
      <section class="industry-master-summary">
        <dl><div><dt>门类</dt><dd>{counts.get("section", 0)}</dd></div><div><dt>大类</dt><dd>{counts.get("division", 0)}</dd></div><div><dt>中类</dt><dd>{counts.get("group", 0)}</dd></div><div><dt>小类</dt><dd>{counts.get("class", 0)}</dd></div></dl>
        <form method="get" action="/rules"><label for="industry-search">按代码或名称搜索</label><div><input id="industry-search" name="q" value="{e(view.get('query') or '')}" placeholder="例如：4415 或 风力发电"><button class="button primary" type="submit">搜索</button></div></form>
      </section>
      {search_results}
      <section class="taxonomy-browser" aria-label="国民经济行业分类树">
        <article><header><b>1 门类</b><span>A–T</span></header><nav>{section_nodes}</nav></article>
        <article><header><b>2 大类</b><span>两位代码</span></header><nav>{division_nodes}</nav></article>
        <article><header><b>3 中类</b><span>三位代码</span></header><nav>{group_nodes}</nav></article>
        <article><header><b>4 小类</b><span>四位代码</span></header><nav>{class_nodes}</nav></article>
      </section>
      {profile_html or '<section class="industry-prompt"><b>请选择行业小类</b><span>选择后查看行业定义、适用规则、证据要求、风险点和来源版本。</span></section>'}
    '''


def integrations_page() -> str:
    rows = (
        ("银行内部授信规则", "未接入", "行业准入、额度、尽调、审批和贷后制度"),
        ("行内客户与项目主数据", "未接入", "企业、项目、经办团队和额度信息"),
        ("征信与外部合规数据", "未接入", "处罚、失信、许可状态与舆情"),
        ("文件解析服务", "本地原型", "PDF、DOCX、表格的结构化抽取与证据定位"),
    )
    content = "".join(f'<div><b>{e(name)}</b>{_status_badge("cannot_determine", state)}<p>{e(scope)}</p></div>' for name, state, scope in rows)
    return _page_intro("系统边界", "系统对接", "未接入的数据源固定显示无法判断，不以公开资料或模型猜测填补银行内部结论。") + f'<section class="integration-list">{content}</section>'


def placeholder_page(title: str) -> str:
    return _page_intro("建设中", title, "该模块将在后续阶段实现，当前数据来自 Phase 1 数据层。")


def not_found_page(message: str) -> str:
    return f'<section class="not-found"><b>未找到</b><p>{e(message)}</p><a class="button" href="/dashboard">返回工作台</a></section>'
