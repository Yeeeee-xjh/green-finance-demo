from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from green_model.agent.domain.enums import (
    CaseStatus, DataOrigin, VerificationStatus,
)
from green_model.agent.domain.models import Case, RuleVersion, Task, VerificationItem
from green_model.phase2_ui import Phase2Application
from green_model.phase2_ui.pages import monitoring_page


class CaseWorkspaceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "workspace.sqlite3"
        self.app = Phase2Application(
            self.database_path,
            legacy_renderer=lambda: '<html><body><input><button>保存</button></body></html>',
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def text(response) -> str:
        return response.body.decode("utf-8")

    def add_case(self, case_id: str = "CASE-1", *, origin=DataOrigin.USER_UPLOAD) -> None:
        self.app.repository.add(Case(
            case_id=case_id,
            case_name="储能项目贷款审查",
            borrower_name="测试能源有限公司",
            project_name="100MWh储能项目",
            primary_industry="储能",
            project_activity="电化学储能建设",
            enterprise_stage="成长期",
            project_stage="建设期",
            loan_stage="贷中审查审批",
            assignee="李经理",
            status=CaseStatus.VERIFYING,
            record_origin=origin,
        ))

    def test_dashboard_and_queue_are_accessible(self) -> None:
        self.assertEqual(self.app.handle_get("/dashboard").status, 200)
        self.assertEqual(self.app.handle_get("/cases").status, 200)
        self.assertIn("绿色金融贷款项目工作台", self.text(self.app.handle_get("/dashboard")))

    def test_all_functional_routes_are_accessible(self) -> None:
        self.add_case()
        suffixes = ("overview", "documents", "classification", "risks", "conflicts", "verification", "reading", "monitoring", "reports")
        for suffix in suffixes:
            with self.subTest(suffix=suffix):
                response = self.app.handle_get(f"/cases/CASE-1/{suffix}")
                self.assertEqual(response.status, 200)
                self.assertEqual(self.text(response).count("data-page-root="), 1)
        for path in ("/tasks", "/rules", "/settings/integrations"):
            self.assertEqual(self.app.handle_get(path).status, 200)

    def test_overview_uses_one_loan_story_and_two_workfaces(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        for phrase in ("行业判断", "分配经办", "企业阶段", "项目阶段", "风险识别", "辅助核验", "辅助阅读", "补充材料", "下载报告"):
            self.assertIn(phrase, text)

    def test_case_first_screen_states_current_step_and_next_action(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        self.assertIn("当前步骤", text)
        self.assertIn("风险识别与辅助核验", text)
        self.assertIn("下一步", text)
        self.assertIn("登记项目材料，建立可追溯证据台账", text)

    def test_risk_and_verification_workfaces_have_clear_detail_entries(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        self.assertIn('href="/cases/CASE-1/risks">进入风险明细</a>', text)
        self.assertIn('href="/cases/CASE-1/verification">进入核验明细</a>', text)

    def test_overview_exposes_signal_chain_and_task_closure_without_fake_results(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        for phrase in ("规则核验", "跨文件冲突", "企业披露筛查", "贷后实绩", "补件与任务闭环", "解析与重核", "人工确认", "报告归档"):
            self.assertIn(phrase, text)
        self.assertIn("企业披露筛查</span><b>未运行", text)
        self.assertIn("0 个指标已定义", text)

    def test_risk_page_connects_bert_to_the_same_evidence_chain(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/risks"))
        self.assertIn("企业披露文本风险筛查（BERT）", text)
        self.assertIn("运行披露文本筛查", text)
        self.assertIn("风险依据台账", text)
        self.assertIn("无可计分核验项，保持待计算", text)

    def test_industry_and_both_stages_have_basis_entries(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        self.assertIn('/classification#industry-basis', text)
        self.assertIn('/classification#enterprise-stage-basis', text)
        self.assertIn('/classification#project-stage-basis', text)
        classification = self.text(self.app.handle_get("/cases/CASE-1/classification"))
        for anchor in ('id="industry-basis"', 'id="enterprise-stage-basis"', 'id="project-stage-basis"'):
            self.assertIn(anchor, classification)
        self.assertIn('id="manager-basis"', classification)
        self.assertIn("依据待复核", classification)

    def test_empty_case_does_not_invent_risk_scores(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/risks"))
        self.assertIn("当前没有足够的适用核验项，暂不计算分值", text)
        self.assertEqual(text.count('<div class="risk-number empty"><b>未计算</b>'), 5)
        self.assertEqual(text.count('暂无可计算数据'), 5)
        self.assertNotIn('<div class="risk-scale"><div><i', text)

    def test_risk_score_is_computed_from_verification_status(self) -> None:
        self.add_case()
        rule = RuleVersion(rule_version_id="RULE-V1", rule_id="T01", rule_name="测试要求", requirement_text="核对项目边界")
        self.app.repository.add(rule)
        self.app.repository.add(VerificationItem(
            verification_id="VERIFY-1", case_id="CASE-1", risk_dimension="project_boundary",
            rule_version_id="RULE-V1", status=VerificationStatus.EVIDENCE_CONFLICT,
            requirement_text="核对项目边界", applicability_reason="项目事实：范围不一致｜证据：可研第1页与环评第2页",
        ))
        text = self.text(self.app.handle_get("/cases/CASE-1/risks"))
        self.assertIn(">80<", text)
        self.assertIn("证据冲突80", text)

    def test_new_case_is_persisted_and_redirects_to_overview(self) -> None:
        payload = urlencode({
            "case_name": "新材料项目", "borrower_name": "测试公司", "project_name": "负极材料项目",
            "primary_industry": "新能源材料", "project_activity": "负极材料生产", "assignee": "王经理", "notes": "新建",
        }).encode("utf-8")
        response = self.app.handle_post("/cases/new", payload)
        self.assertEqual(response.status, 303)
        self.assertTrue(response.headers["Location"].endswith("/overview"))
        case_id = response.headers["Location"].split("/")[2]
        self.assertEqual(self.app.repository.get("cases", case_id)["status"], "draft")

    def test_supplement_creates_document_task_and_audit_without_changing_conclusion(self) -> None:
        self.add_case()
        boundary = "BOUNDARY123"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_type\"\r\n\r\n项目材料\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"related_item\"\r\n\r\nG04\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"evidence.txt\"\r\nContent-Type: text/plain\r\n\r\nnew evidence\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        response = self.app.handle_post("/cases/CASE-1/supplements", body, f"multipart/form-data; boundary={boundary}")
        self.assertEqual(response.status, 303)
        self.assertEqual(len(self.app.repository.find("documents", filters={"case_id": "CASE-1"})), 1)
        self.assertEqual(len(self.app.repository.find("tasks", filters={"case_id": "CASE-1"})), 1)
        audits = self.app.repository.find("audit_logs", filters={"case_id": "CASE-1"})
        self.assertFalse(json.loads(audits[-1]["details_json"])["conclusion_changed"])

    def test_pdf_and_json_reports_download(self) -> None:
        self.add_case()
        pdf = self.app.handle_get("/cases/CASE-1/reports/download.pdf")
        report_json = self.app.handle_get("/cases/CASE-1/reports/download.json")
        self.assertEqual(pdf.status, 200)
        self.assertTrue(pdf.body.startswith(b"%PDF"))
        self.assertEqual(report_json.status, 200)
        self.assertEqual(json.loads(report_json.body)["case"]["case_id"], "CASE-1")

    def test_legacy_demo_is_excluded_from_formal_dashboard_count(self) -> None:
        self.add_case("LEGACY", origin=DataOrigin.LEGACY_DEMO)
        text = self.text(self.app.handle_get("/dashboard"))
        self.assertIn('data-metric="case_count" data-value="0"', text)
        self.assertIn("公开案例参考", text)

    def test_fullchain_showcase_has_a_separate_case_queue_entry(self) -> None:
        self.add_case("SHOWCASE", origin=DataOrigin.LEGACY_DEMO)
        self.app.repository.update(
            "cases", "SHOWCASE", {"legacy_note": "synthetic_fullchain_showcase"}
        )
        text = self.text(self.app.handle_get("/cases"))
        self.assertIn("全链路展示案例", text)
        self.assertIn("合成演示 · 不计入正式统计", text)
        self.assertIn('href="/cases/SHOWCASE/overview"', text)

    def test_legacy_case_measurements_are_visibly_disclosed_as_demo(self) -> None:
        self.add_case("LEGACY", origin=DataOrigin.LEGACY_DEMO)
        text = self.text(self.app.handle_get("/cases/LEGACY/overview"))
        self.assertIn("演示数据", text)
        self.assertIn("不作为真实模型结果", text)
        self.assertIn("演示测算 · 非真实模型结果", text)

    def test_verification_page_never_falls_back_to_internal_item_id(self) -> None:
        self.add_case()
        self.app.repository.add(VerificationItem(
            verification_id="verify_6c83c6e7-8a6c-477b-9c20-149ffad2b607",
            case_id="CASE-1",
            risk_dimension="project_boundary",
            status=VerificationStatus.PENDING_VERIFICATION,
            requirement_text="核对项目范围",
        ))
        text = self.text(self.app.handle_get("/cases/CASE-1/verification"))
        self.assertIn("行业核验项", text)
        self.assertNotIn("verify_6c83c6e7", text)

    def test_navigation_contains_full_case_chain(self) -> None:
        self.add_case()
        text = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        for suffix in ("overview", "documents", "classification", "risks", "verification", "reading", "conflicts", "monitoring", "reports"):
            self.assertIn(f'/cases/CASE-1/{suffix}', text)

    def test_case_ui_hides_internal_ids_json_label_and_english_task_types(self) -> None:
        self.add_case()
        self.app.repository.add(Task(
            case_id="CASE-1", task_type="supplement_review", trigger_reason="核对补件",
        ))
        overview = self.text(self.app.handle_get("/cases/CASE-1/overview"))
        tasks = self.text(self.app.handle_get("/tasks"))
        reports = self.text(self.app.handle_get("/cases/CASE-1/reports"))
        self.assertNotIn(">CASE-1<", overview)
        self.assertNotIn("supplement_review", tasks)
        self.assertNotIn("task_", tasks)
        self.assertIn("补件复核", tasks)
        self.assertNotIn("下载 JSON", reports)
        self.assertIn("下载结构化数据", reports)

    def test_legacy_route_remains_read_only(self) -> None:
        text = self.text(self.app.handle_get("/legacy"))
        self.assertIn("历史版本只读回放", text)
        self.assertIn("<input disabled", text)
        self.assertIn("<button disabled", text)

    def test_css_is_responsive_without_forced_desktop_min_width(self) -> None:
        css = self.app.handle_get("/assets/phase2.css").body.decode("utf-8")
        self.assertIn("@media(max-width:900px)", css)
        self.assertNotIn("min-width:1180px", css)

    def test_monitoring_page_renders_current_bta_observation_columns(self) -> None:
        html = monitoring_page({
            "case": {"case_id": "CASE-1"},
            "bta_observations": [{
                "indicator": {
                    "indicator_id": "BTA-1",
                    "indicator_name": "建设进度完成率",
                    "indicator_category": "construction_progress",
                    "unit": "%",
                    "status": "warning",
                },
                "series": {
                    "baseline": {"raw_value": "10"},
                    "target": {"normalized_value": "20"},
                    "actual": {"raw_value": "18"},
                },
            }],
            "postloan_evaluations": [],
        })
        self.assertIn('<b>10</b>', html)
        self.assertIn('<b>20</b>', html)
        self.assertIn('<b>18</b>', html)


if __name__ == "__main__":
    unittest.main()
