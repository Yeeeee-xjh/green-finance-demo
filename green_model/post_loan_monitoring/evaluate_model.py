#!/usr/bin/env python3
"""在带 gold_risk_level 的盲测案例数组上评价贷后模型。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from postloan_model import DEFAULT_CONFIG, analyze_case, deep_merge, hydrate_case, load_json


LABELS = ["GREEN", "YELLOW", "ORANGE", "RED", "GREY"]


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="含gold_risk_level的案例数组JSON")
    p.add_argument("--config", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cases = load_json(args.input)
    if not isinstance(cases, list) or not cases:
        raise ValueError("评价输入必须是非空案例数组")
    cfg = deep_merge(DEFAULT_CONFIG, load_json(args.config)) if args.config else DEFAULT_CONFIG
    pairs, rows = [], []
    for case in cases:
        gold = case.get("gold_risk_level")
        if gold not in LABELS:
            raise ValueError(f"项目{case.get('project_id')}的gold_risk_level无效：{gold}")
        pred = analyze_case(hydrate_case(case, args.input), cfg)
        pairs.append((gold, pred["risk_level"]))
        rows.append({"project_id": case.get("project_id"), "gold": gold, "pred": pred["risk_level"],
                     "score": pred["risk_score"], "confidence": pred["data_confidence"]})
    matrix = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p_ in pairs:
        matrix[g][p_] += 1
    f1s = []
    per_class = {}
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[g][label] for g in LABELS if g != label)
        fn = sum(matrix[label][p_] for p_ in LABELS if p_ != label)
        precision, recall = safe_div(tp, tp + fp), safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
                            "support": sum(matrix[label].values())}
        f1s.append(f1)
    high_gold = [(g, p_) for g, p_ in pairs if g in {"ORANGE", "RED"}]
    high_tp = sum(p_ in {"ORANGE", "RED"} for _, p_ in high_gold)
    high_pred = sum(p_ in {"ORANGE", "RED"} for _, p_ in pairs)
    report = {
        "case_count": len(pairs),
        "accuracy": round(safe_div(sum(g == p_ for g, p_ in pairs), len(pairs)), 4),
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "orange_red_recall": round(safe_div(high_tp, len(high_gold)), 4),
        "orange_red_precision": round(safe_div(high_tp, high_pred), 4),
        "prediction_distribution": dict(Counter(p_ for _, p_ in pairs)),
        "confusion_matrix": matrix, "per_class": per_class, "case_results": rows,
        "notice": "阈值只能在训练/验证集校准；本评价脚本应用于锁定后的独立测试集。"
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
