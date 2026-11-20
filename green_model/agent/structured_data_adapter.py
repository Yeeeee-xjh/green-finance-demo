from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


SUPPORTED_METRICS = {"能耗", "电耗", "水耗", "产量", "碳排", "发电量", "节能量", "项目进度"}


def baseline_target_actual(row: dict[str, Any]) -> dict[str, Any]:
    def num(v):
        try: return float(v) if v not in (None, "") else None
        except (TypeError, ValueError): return None
    target, actual = num(row.get("target_value")), num(row.get("actual_value"))
    expected, progressed = num(row.get("expected_progress")), num(row.get("actual_progress"))
    deviation = None
    if expected not in (None, 0) and progressed is not None:
        deviation = (progressed - expected) / abs(expected)
    elif target not in (None, 0) and actual is not None:
        deviation = (actual - target) / abs(target)
    return {k: row.get(k) for k in ("metric_name", "unit", "baseline_value", "baseline_period", "target_value", "target_date", "actual_value", "actual_period", "expected_progress", "actual_progress", "evidence_source", "confidence")} | {"deviation": deviation, "availability": "not_available" if actual is None else "available", "manual_attention": actual is None or (deviation is not None and deviation < -0.15)}


def load_structured(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig")); rows = payload if isinstance(payload, list) else payload.get("metrics", [payload])
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f: rows = list(csv.DictReader(f))
    elif suffix in {".xlsx", ".xls"}:
        import pandas as pd
        rows = pd.read_excel(path).to_dict("records")
    else:
        raise ValueError("结构化适配器支持CSV、Excel、JSON；PDF/Word由材料上传层保存并进入人工/文本抽取流程。")
    return [baseline_target_actual(x) for x in rows]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); result = load_structured(a.input); a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
