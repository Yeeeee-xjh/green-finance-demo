from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaseManager:
    """以一个Case串联贷前、贷中、人工确认和贷后，审计记录只追加不覆盖。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, case_id: str) -> Path:
        safe = "".join(c for c in case_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("case_id不能为空")
        path = self.root / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_artifact(self, case_id: str, name: str, payload: Any) -> Path:
        path = self._dir(case_id) / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.append_audit(case_id, "artifact_saved", {"name": name, "sha256": self.sha256(path)})
        return path

    def append_audit(self, case_id: str, event: str, details: dict[str, Any]) -> None:
        row = {"at": datetime.now(timezone.utc).isoformat(), "event": event, "details": details}
        with (self._dir(case_id) / "audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
