from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict[str, Any]:
    """Small YAML reader with safe defaults; PyYAML is optional at runtime."""
    defaults = {
        "project_root": PROJECT_ROOT, "case_storage": PROJECT_ROOT / "agent_cases",
        "upload_dir": PROJECT_ROOT / "runtime_uploads", "report_output": PROJECT_ROOT / "reports",
        "green_catalog": PROJECT_ROOT / "loan_review/data/catalog_entries_2025_full.json",
        "transition_rules": PROJECT_ROOT / "agent/rule_packs/transition_rules.json",
        "policy_sources": PROJECT_ROOT.parent / "data_policy", "bert_multitask_model": PROJECT_ROOT / "models/green_multitask",
        "bge_model": PROJECT_ROOT / "models/bge", "demo_data_dir": PROJECT_ROOT / "loan_review/data/public_cases_2023_2025/projects",
    }
    path = PROJECT_ROOT / "config/app_config.yaml"
    if not path.exists(): return defaults
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1); values[key.strip()] = value.strip().strip("'\"")
    for key, value in values.items():
        if key in defaults and key != "project_root":
            defaults[key] = (PROJECT_ROOT / value).resolve()
    return defaults

