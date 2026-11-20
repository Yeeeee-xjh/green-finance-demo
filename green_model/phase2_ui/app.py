"""Framework-agnostic Phase 2 router.

The HTTP adapter in ``web_app_phase2.py`` delegates here.  Keeping routing and
rendering independent of sockets makes every route testable without starting a
server or touching legacy JSON.
"""

from __future__ import annotations

import re
import sys
import hashlib
from email import policy
from email.parser import BytesParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import parse_qs, quote, unquote

from green_model.agent.domain.enums import CaseStatus, DataOrigin, RoleType
from green_model.agent.domain.models import AuditLog, Case, new_id
from green_model.agent.storage import Database, SQLiteRepository
from green_model.phase3 import BertInferenceAdapter, DocumentProcessingService, RuleRegistry
from green_model.phase35 import IndustryMasterQueries

from .layout import render_layout
from .intelligence import CaseIntelligence
from .pages import (
    cases_page,
    classification_page,
    conflicts_page,
    dashboard_page,
    documents_page,
    integrations_page,
    monitoring_page,
    new_case_page,
    not_found_page,
    overview_page,
    reading_page,
    reports_page,
    risks_page,
    rules_page,
    tasks_page,
    verification_page,
)
from .queries import Phase2Queries
from .reporting import json_bytes, pdf_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "phase1" / "green_finance_phase1.sqlite3"
STATIC_ROOT = Path(__file__).with_name("static")
LEGACY_ASSETS = PROJECT_ROOT / "competition_ui"

CASE_ROUTE_NAMES = {
    "overview": "案件总览",
    "documents": "文件与证据台账",
    "classification": "行业定标",
    "risks": "风险识别",
    "conflicts": "冲突台账",
    "verification": "核验矩阵",
    "reading": "辅助阅读",
    "monitoring": "贷后监测",
    "reports": "报告与审计",
}

@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def html(cls, body: str, status: int = 200) -> "Response":
        data = body.encode("utf-8")
        return cls(
            status=status,
            body=data,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": str(len(data)),
            },
        )

    @classmethod
    def redirect(cls, location: str, status: int = 303) -> "Response":
        return cls(status=status, headers={"Location": location, "Content-Length": "0"})

    @classmethod
    def binary(cls, body: bytes, content_type: str, filename: str) -> "Response":
        return cls(
            status=200,
            body=body,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                "Cache-Control": "no-store",
            },
        )


class Phase2Application:
    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE,
        *,
        legacy_renderer: Callable[[], str] | None = None,
    ):
        # Imported lazily to keep the Phase 4 workflow's dependency on the
        # Phase 2 read model acyclic during package initialisation.
        from green_model.phase4.case_intelligence import CaseIntelligenceService
        from green_model.phase4.postloan_monitoring import PostloanMonitoringService
        from green_model.phase4.supplement_workflow import (
            SupplementUpload,
            SupplementWorkflowService,
        )

        self.database = Database(database_path)
        self.database.initialize()
        self.repository = SQLiteRepository(self.database)
        self.queries = Phase2Queries(self.repository)
        self.intelligence = CaseIntelligence(self.repository)
        self.document_processing = DocumentProcessingService(self.repository)
        self.bert_inference = BertInferenceAdapter(self.repository)
        self.case_intelligence_service = CaseIntelligenceService(self.repository)
        self.supplement_workflow = SupplementWorkflowService(
            self.repository,
            upload_root=PROJECT_ROOT / "data" / "uploads",
            report_root=PROJECT_ROOT / "data" / "reports",
            document_service=self.document_processing,
            intelligence_service=self.case_intelligence_service,
            read_model=self.intelligence,
        )
        self.postloan_monitoring = PostloanMonitoringService(self.repository)
        self._supplement_upload_type = SupplementUpload
        self.rule_registry = RuleRegistry(self.repository, PROJECT_ROOT.parent)
        self.rule_registry_result = self.rule_registry.sync()
        self.industry_master = IndustryMasterQueries(self.repository)
        self._legacy_renderer = legacy_renderer

    @staticmethod
    def _first(query: Mapping[str, list[str]], key: str) -> str:
        values = query.get(key) or []
        return values[0].strip() if values else ""

    def handle_get(
        self, path: str, query: Mapping[str, list[str]] | None = None
    ) -> Response:
        query = query or {}
        if path == "/":
            return Response.redirect("/dashboard", status=302)
        if path == "/assets/phase2.css":
            data = (STATIC_ROOT / "phase2.css").read_bytes()
            return Response(
                200,
                data,
                {
                    "Content-Type": "text/css; charset=utf-8",
                    "Content-Length": str(len(data)),
                    "Cache-Control": "no-store",
                },
            )
        if path == "/assets/phase2.js":
            data = (STATIC_ROOT / "phase2.js").read_bytes()
            return Response(
                200,
                data,
                {
                    "Content-Type": "application/javascript; charset=utf-8",
                    "Content-Length": str(len(data)),
                    "Cache-Control": "no-store",
                },
            )
        if path == "/competition.css":
            data = (LEGACY_ASSETS / "competition.css").read_bytes()
            return Response(
                200,
                data,
                {
                    "Content-Type": "text/css; charset=utf-8",
                    "Content-Length": str(len(data)),
                    "Cache-Control": "no-store",
                },
            )
        if path == "/dashboard":
            body = dashboard_page(self.queries.dashboard())
            return Response.html(
                render_layout(title="概览工作台", content=body, active="dashboard")
            )
        if path == "/cases":
            view = self.queries.case_queue(
                status=self._first(query, "status") or None,
                industry=self._first(query, "industry") or None,
                assignee=self._first(query, "assignee") or None,
                sort=self._first(query, "sort") or "updated_desc",
            )
            return Response.html(
                render_layout(
                    title="案件队列",
                    content=cases_page(view),
                    active="cases",
                )
            )
        if path == "/cases/new":
            return Response.html(
                render_layout(
                    title="新建案件",
                    content=new_case_page(),
                    active="new_case",
                )
            )
        if path == "/tasks":
            cases = {
                row["case_id"]: row
                for row in self.repository.find("cases")
            }
            tasks = []
            for row in self.repository.find("tasks", order_by="-updated_at"):
                related_case = cases.get(row.get("case_id")) or {}
                tasks.append({
                    **row,
                    "case_label": related_case.get("project_name") or related_case.get("case_name") or "关联案件",
                })
            return Response.html(
                render_layout(
                    title="任务中心",
                    content=tasks_page(tasks),
                    active="tasks",
                )
            )
        if path == "/rules":
            view = self.industry_master.browse(
                section=self._first(query, "section"),
                division=self._first(query, "division"),
                group=self._first(query, "group"),
                class_code=self._first(query, "class"),
                query=self._first(query, "q"),
            )
            return Response.html(render_layout(title="行业规则库", content=rules_page(view), active="rules"))
        if path == "/settings/integrations":
            return Response.html(render_layout(title="系统对接", content=integrations_page(), active="integrations"))
        if path == "/legacy":
            return Response.html(self._render_legacy())

        history_report_match = re.fullmatch(r"/cases/([^/]+)/reports/versions/(\d+)\.(pdf|json)", path)
        if history_report_match:
            case_id = unquote(history_report_match.group(1))
            revision = int(history_report_match.group(2))
            kind = history_report_match.group(3)
            rows = self.repository.find(
                "report_snapshots",
                filters={"case_id": case_id, "snapshot_revision": revision},
            )
            if not rows:
                return Response.html(render_layout(title="报告不存在", content=not_found_page("未找到该报告版本。"), active="cases"), status=404)
            row = rows[0]
            key = "pdf_path" if kind == "pdf" else "json_path"
            hash_key = "pdf_hash" if kind == "pdf" else "json_hash"
            stored_path = row.get(key)
            if not stored_path:
                return Response.html(render_layout(title="报告不可用", content=not_found_page("该版本未保存对应文件。"), active="cases"), status=404)
            candidate = Path(str(stored_path)).resolve()
            data_root = (PROJECT_ROOT / "data").resolve()
            try:
                candidate.relative_to(data_root)
            except ValueError:
                return Response.html(render_layout(title="报告不可用", content=not_found_page("报告文件路径未通过安全校验。"), active="cases"), status=409)
            if not candidate.is_file():
                return Response.html(render_layout(title="报告不可用", content=not_found_page("报告归档文件不存在。"), active="cases"), status=404)
            content = candidate.read_bytes()
            expected_hash = str(row.get(hash_key) or "")
            if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
                return Response.html(render_layout(title="报告不可用", content=not_found_page("报告文件哈希校验失败。"), active="cases"), status=409)
            media_type = "application/pdf" if kind == "pdf" else "application/json; charset=utf-8"
            return Response.binary(content, media_type, f"数绿融通_{case_id}_第{revision}版.{kind}")

        report_match = re.fullmatch(r"/cases/([^/]+)/reports/download\.(pdf|json)", path)
        if report_match:
            case_id = unquote(report_match.group(1))
            view = self.intelligence.build(case_id)
            if view is None:
                return Response.html(render_layout(title="案件不存在", content=not_found_page(case_id), active="cases"), status=404)
            kind = report_match.group(2)
            if kind == "pdf":
                return Response.binary(pdf_bytes(view), "application/pdf", f"数绿融通_{case_id}_核验报告.pdf")
            return Response.binary(json_bytes(view), "application/json; charset=utf-8", f"数绿融通_{case_id}_核验报告.json")

        match = re.fullmatch(
            r"/cases/([^/]+)/(overview|documents|classification|risks|conflicts|verification|reading|monitoring|reports)",
            path,
        )
        if match:
            case_id = unquote(match.group(1))
            module = match.group(2)
            view = self.intelligence.build(case_id)
            if view is None:
                return Response.html(
                    render_layout(
                        title="案件不存在",
                        content=not_found_page(f"未找到案件：{case_id}"),
                        active="cases",
                    ),
                    status=404,
                )
            title = CASE_ROUTE_NAMES[module]
            pages = {
                "overview": lambda: overview_page(view),
                "documents": lambda: documents_page(view, message=self._first(query, "message"), error=self._first(query, "error")),
                "classification": lambda: classification_page(view),
                "risks": lambda: risks_page(view),
                "conflicts": lambda: conflicts_page(view),
                "verification": lambda: verification_page(view),
                "reading": lambda: reading_page(view),
                "monitoring": lambda: monitoring_page(view),
                "reports": lambda: reports_page(
                    view,
                    message=self._first(query, "message"),
                    error=self._first(query, "error"),
                ),
            }
            return Response.html(
                render_layout(
                    title=title,
                    content=pages[module](),
                    active=module,
                    case=view["case"],
                    workflow=view["workflow"],
                    subtitle="单笔贷款案件作业",
                )
            )

        return Response.html(
            render_layout(
                title="页面不存在",
                content=not_found_page(path),
                active="dashboard",
            ),
            status=404,
        )

    def handle_post(
        self,
        path: str,
        body: bytes,
        content_type: str = "application/x-www-form-urlencoded",
    ) -> Response:
        parse_match = re.fullmatch(r"/cases/([^/]+)/documents/([^/]+)/parse", path)
        if parse_match:
            case_id = unquote(parse_match.group(1))
            doc_id = unquote(parse_match.group(2))
            try:
                outcome = self.document_processing.process(case_id, doc_id)
            except LookupError as exc:
                return Response.redirect(
                    f"/cases/{quote(case_id, safe='')}/documents?error={quote(str(exc))}"
                )
            target = "message" if outcome.status == "completed" else "error"
            return Response.redirect(
                f"/cases/{quote(case_id, safe='')}/documents?{target}={quote(outcome.message)}"
            )

        assess_match = re.fullmatch(r"/cases/([^/]+)/assess", path)
        if assess_match:
            case_id = unquote(assess_match.group(1))
            try:
                result = self.case_intelligence_service.assess(
                    case_id,
                    run_kind="manual_rerun",
                    trigger_reason="用户在案件工作面重新运行全案核验",
                    actor="user",
                )
                risk_count = sum(axis.finding_count for axis in result.axes)
                message = f"全案核验完成：风险线索 {risk_count} 项，核验项 {result.verification_count} 项"
                return Response.redirect(
                    f"/cases/{quote(case_id, safe='')}/risks?message={quote(message)}"
                )
            except (LookupError, ValueError, RuntimeError) as exc:
                return Response.redirect(
                    f"/cases/{quote(case_id, safe='')}/risks?error={quote(str(exc))}"
                )

        model_match = re.fullmatch(r"/cases/([^/]+)/models/green-profile/run", path)
        if model_match:
            case_id = unquote(model_match.group(1))
            if self.repository.get("cases", case_id) is None:
                return Response.html(
                    render_layout(
                        title="案件不存在",
                        content=not_found_page(case_id),
                        active="cases",
                    ),
                    status=404,
                )
            view = self.intelligence.build(case_id) or {}
            texts = [
                str(row.get("raw_excerpt") or "")
                for row in view.get("evidence", [])
                if row.get("raw_excerpt")
            ]
            self.bert_inference.run(case_id, texts)
            return Response.redirect(
                f"/cases/{quote(case_id, safe='')}/reading", status=303
            )

        load_monitoring = re.fullmatch(r"/cases/([^/]+)/monitoring/load", path)
        if load_monitoring:
            case_id = unquote(load_monitoring.group(1))
            try:
                result = self.postloan_monitoring.load_industry_indicators(case_id, actor="user")
                message = f"已装载 {len(result.loaded_indicator_ids)} 个指标，复用 {len(result.reused_indicator_ids)} 个指标"
                return Response.redirect(f"/cases/{quote(case_id, safe='')}/monitoring?message={quote(message)}")
            except (KeyError, ValueError) as exc:
                return Response.redirect(f"/cases/{quote(case_id, safe='')}/monitoring?error={quote(str(exc))}")

        evaluate_monitoring = re.fullmatch(r"/cases/([^/]+)/monitoring/evaluate", path)
        if evaluate_monitoring:
            case_id = unquote(evaluate_monitoring.group(1))
            try:
                results = self.postloan_monitoring.evaluate_case(case_id, actor="user")
                message = f"已检查 {len(results)} 个贷后指标；不可比项保持待核实"
                return Response.redirect(f"/cases/{quote(case_id, safe='')}/monitoring?message={quote(message)}")
            except (KeyError, ValueError) as exc:
                return Response.redirect(f"/cases/{quote(case_id, safe='')}/monitoring?error={quote(str(exc))}")

        review_match = re.fullmatch(r"/cases/([^/]+)/tasks/([^/]+)/review", path)
        if review_match:
            case_id, task_id = map(unquote, review_match.groups())
            fields = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            try:
                result = self.supplement_workflow.review_task(
                    case_id,
                    task_id,
                    approve=(fields.get("decision") or [""])[0] == "approve",
                    reason=(fields.get("reason") or [""])[0],
                    actor=(fields.get("actor") or ["人工审核员"])[0],
                    actor_role=RoleType.REVIEWER,
                )
                return Response.redirect(
                    f"/cases/{quote(case_id, safe='')}/reports?message={quote(f'审核完成，已生成报告版本 {result.snapshot_revision}')}"
                )
            except (LookupError, ValueError, RuntimeError) as exc:
                return Response.redirect(f"/cases/{quote(case_id, safe='')}/reports?error={quote(str(exc))}")

        supplement_match = re.fullmatch(r"/cases/([^/]+)/supplements", path)
        if supplement_match:
            return self._handle_supplement(
                unquote(supplement_match.group(1)), body, content_type
            )
        if path != "/cases/new":
            return Response.html(
                render_layout(
                    title="操作不可用",
                    content=not_found_page("该写入操作未在 Phase 2 开放。"),
                    active="dashboard",
                ),
                status=405,
            )
        if not content_type.startswith("application/x-www-form-urlencoded"):
            return Response.html(
                render_layout(
                    title="新建案件",
                    content=new_case_page(error="仅支持标准表单提交。"),
                    active="new_case",
                ),
                status=415,
            )
        if len(body) > 32_768:
            return Response.html(
                render_layout(
                    title="新建案件",
                    content=new_case_page(error="表单内容超过允许长度。"),
                    active="new_case",
                ),
                status=413,
            )
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        values = {
            name: (parsed.get(name) or [""])[0].strip()
            for name in (
                "case_name",
                "borrower_name",
                "project_name",
                "primary_industry",
                "project_activity",
                "assignee",
                "notes",
            )
        }
        missing = [
            label
            for name, label in (
                ("case_name", "案件名称"),
                ("borrower_name", "借款企业"),
                ("project_name", "项目名称"),
            )
            if not values[name]
        ]
        limits = {
            "case_name": 120,
            "borrower_name": 160,
            "project_name": 200,
            "primary_industry": 100,
            "project_activity": 200,
            "assignee": 80,
            "notes": 1000,
        }
        too_long = [name for name, limit in limits.items() if len(values[name]) > limit]
        error = None
        if missing:
            error = "请填写：" + "、".join(missing)
        elif too_long:
            error = "以下字段超过长度限制：" + "、".join(too_long)
        if error:
            return Response.html(
                render_layout(
                    title="新建案件",
                    content=new_case_page(error=error, values=values),
                    active="new_case",
                ),
                status=400,
            )

        case_id = new_id("case")
        case = Case(
            case_id=case_id,
            case_name=values["case_name"],
            borrower_name=values["borrower_name"],
            project_name=values["project_name"],
            primary_industry=values["primary_industry"] or None,
            project_activity=values["project_activity"] or None,
            assignee=values["assignee"] or None,
            notes=values["notes"] or None,
            status=CaseStatus.DRAFT,
            record_origin=DataOrigin.USER_UPLOAD,
        )
        actor = values["assignee"] or "system"
        with self.repository.transaction() as uow:
            uow.add(case)
            uow.add(
                AuditLog(
                    case_id=case_id,
                    action="case_created",
                    actor=actor,
                    actor_role=(
                        RoleType.RELATIONSHIP_MANAGER
                        if values["assignee"]
                        else RoleType.SYSTEM
                    ),
                    after_state=CaseStatus.DRAFT.value,
                    details_json={
                        "source": "phase2_new_case_form",
                        "file_parsing_enabled": False,
                    },
                )
            )
        return Response.redirect(
            f"/cases/{quote(case_id, safe='')}/overview", status=303
        )

    def _handle_supplement(self, case_id: str, body: bytes, content_type: str) -> Response:
        if self.repository.get("cases", case_id) is None:
            return Response.html(render_layout(title="案件不存在", content=not_found_page(case_id), active="cases"), status=404)
        if not content_type.startswith("multipart/form-data"):
            return Response.redirect(f"/cases/{quote(case_id, safe='')}/documents?error={quote('补件必须使用文件表单')}")
        if len(body) > 25 * 1024 * 1024:
            return Response.redirect(f"/cases/{quote(case_id, safe='')}/documents?error={quote('单个补件不得超过25MB')}")
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        )
        fields: dict[str, str] = {}
        file_name = ""
        file_data = b""
        mime_type = "application/octet-stream"
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                file_name = Path(filename).name
                file_data = payload
                mime_type = part.get_content_type()
            elif name:
                fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        if not file_name or not file_data:
            return Response.redirect(f"/cases/{quote(case_id, safe='')}/documents?error={quote('请选择非空文件')}")
        try:
            result = self.supplement_workflow.upload_parse_and_reassess(
                case_id,
                self._supplement_upload_type(
                    file_name=file_name,
                    content=file_data,
                    mime_type=mime_type,
                    file_type=fields.get("file_type") or "补充材料",
                    related_item=fields.get("related_item") or None,
                ),
                task_id=fields.get("task_id") or None,
                actor="user",
            )
        except (LookupError, ValueError, RuntimeError) as exc:
            return Response.redirect(
                f"/cases/{quote(case_id, safe='')}/documents?error={quote(str(exc))}"
            )
        message_text = (
            f"补件已解析并重算，提取 {result.fact_count} 个事实、"
            f"{len(result.evidence_ids)} 段证据；任务已进入待审核，不会自动关闭"
        )
        return Response.redirect(
            f"/cases/{quote(case_id, safe='')}/documents?message={quote(message_text)}"
        )

    def _render_legacy(self) -> str:
        if self._legacy_renderer is not None:
            page = self._legacy_renderer()
        else:
            if str(PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(PROJECT_ROOT))
            from competition_ui.components import render as legacy_render

            page = legacy_render("DEMO-A")
        page = page.replace(
            '<script src="/competition.js" defer></script>', ""
        )
        page = re.sub(
            r"<(input|select|textarea|button)\b",
            r"<\1 disabled",
            page,
            flags=re.IGNORECASE,
        )
        banner = '''<div style="position:sticky;top:0;z-index:9999;background:#fff7e6;border-bottom:1px solid #e4c989;padding:10px 18px;color:#684b12;font:600 14px/1.4 system-ui;text-align:center">历史版本只读回放：数据来自旧 Case 文件，不参与 Phase 2 正式统计，所有写入控件已停用。</div>'''
        return re.sub(
            r"<body\b([^>]*)>",
            lambda match: '<body class="legacy-readonly"' + match.group(1) + ">" + banner,
            page,
            count=1,
            flags=re.IGNORECASE,
        )
