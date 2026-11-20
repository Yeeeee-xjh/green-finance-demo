from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def esc(value) -> str:
    return html.escape(str(value if value is not None else "—"))


def main() -> None:
    p = argparse.ArgumentParser(description="把Agent JSON生成可直接截图的16:9路演页")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    mid = data.get("midloan_review", {})
    retrieval = mid.get("catalog_retrieval", {})
    candidates = retrieval.get("top_candidates", [])
    best = candidates[0] if candidates else {}
    conditions = mid.get("condition_review", {})
    evidence = mid.get("evidence_review", {})
    work = mid.get("field_worklist", {})
    route = data.get("routing", {})
    page = f"""<!doctype html><meta charset='utf-8'><title>数绿融通 Agent</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#eef4f2;font-family:'Microsoft YaHei',sans-serif;color:#18332c}}
.page{{width:1600px;height:900px;margin:auto;background:#f7faf9;padding:48px 58px;overflow:hidden}}
h1{{margin:0;font-size:38px}} .sub{{color:#5c726b;margin:8px 0 28px}} .grid{{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:18px}}
.card{{background:white;border:1px solid #d8e4df;border-radius:18px;padding:22px;box-shadow:0 8px 24px #18332c0d;min-height:220px}}
.wide{{grid-column:span 2}} h2{{font-size:19px;color:#0c6b50;margin:0 0 16px}} .big{{font-size:32px;font-weight:700}}
.tag{{display:inline-block;padding:7px 12px;border-radius:99px;background:#dff4e9;margin:4px 6px 4px 0}} .warn{{background:#fff0c7}}
.line{{padding:9px 0;border-bottom:1px solid #edf2ef}} .foot{{margin-top:18px;padding:14px 18px;background:#173b32;color:white;border-radius:12px}}
</style><div class='page'>
<h1>数绿融通｜一笔Case的全流程智能作业</h1><div class='sub'>{esc(data.get('case_id'))} · {esc(data.get('project',{}).get('project_name'))} · AI辅助、人工决策</div>
<div class='grid'>
<div class='card'><h2>01 输入与双路由</h2><div class='line'>企业：{esc(data.get('project',{}).get('company_name'))}</div><div class='line'>绿色路径：{esc(route.get('green_route'))}</div><div class='line'>转型路径：{esc(route.get('transition_route'))}</div><p>{esc(route.get('route_reason'))}</p></div>
<div class='card'><h2>02 目录候选</h2><div class='big'>{esc(best.get('catalog_code'))}</div><p>{esc(best.get('level3') or best.get('project_name'))}</p><span class='tag'>召回分 {esc(best.get('retrieval_score'))}</span><p>召回用于缩小检索范围，不是合规概率。</p></div>
<div class='card'><h2>03 辅助审查结果</h2><div class='big'>{esc(mid.get('review_suggestion'))} 类</div><p>{esc(mid.get('review_label'))}</p><span class='tag'>条件 {esc(conditions.get('catalog_status'))}</span><span class='tag'>证据 {esc(evidence.get('evidence_status'))}</span></div>
<div class='card wide'><h2>04 条件—证据—缺口</h2><div class='line'>已核验条件：{esc(conditions.get('status_counts',{}).get('met',0))}</div><div class='line'>材料：要求 {esc(evidence.get('required_count',0))}｜已提供 {esc(evidence.get('available_count',0))}｜已核验 {esc(evidence.get('verified_count',0))}</div><div class='line'>待补材料：{esc(len(work.get('supplementation_list',[])))}</div><div class='line'>现场核查重点：{esc(len(work.get('site_inspection_priorities',[])))}</div></div>
<div class='card'><h2>05 人工确认门</h2><div class='big'>待确认</div><p>{esc(data.get('next_action'))}</p><span class='tag warn'>禁止自动审批</span></div>
</div><div class='foot'>输出可追溯证据、补件清单和核查任务；人工确认后才建立贷后Baseline–Target–Actual监测Case。</div></div>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
