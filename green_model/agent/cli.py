from __future__ import annotations

import argparse
import json
from pathlib import Path

from .orchestrator import GreenCreditAgent


def main() -> None:
    p = argparse.ArgumentParser(description="数绿融通单Agent演示入口")
    p.add_argument("--case-id", required=True)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--profile", type=Path)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--case-root", type=Path, default=Path("agent_cases"))
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    transition = root / "agent" / "rule_packs" / "transition_rules.json"
    result = GreenCreditAgent(root, args.case_root, args.catalog, transition).start_case(args.case_id, args.project, args.profile)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
