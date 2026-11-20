from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _text_from_bytes(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".txt", ".csv"}: return data.decode("utf-8-sig", errors="replace")
    if suffix == ".json": return data.decode("utf-8-sig", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            from io import BytesIO
            return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
        except Exception: return "PDF已保存；当前环境未安装可用的文本提取器。"
    if suffix == ".docx":
        try:
            from docx import Document
            from io import BytesIO
            return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)
        except Exception: return "DOCX已保存；当前环境未安装可用的文本提取器。"
    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
            from io import BytesIO
            return pd.read_excel(BytesIO(data)).to_csv(index=False)
        except Exception: return "Excel已保存；请使用结构化数据页面导入。"
    return "不支持的文件类型。"


def save_and_adapt(uploaded: Any, target: Path, material_type: str) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    name = Path(uploaded.name).name
    data = uploaded.getvalue()
    destination = target / name
    stem, suffix, index = destination.stem, destination.suffix, 1
    while destination.exists():
        destination = target / f"{stem}_{index}{suffix}"; index += 1
    destination.write_bytes(data)
    text = _text_from_bytes(name, data)
    return {"file_name": destination.name, "path": str(destination), "material_type": material_type,
            "sha256": hashlib.sha256(data).hexdigest(), "text": text[:50000], "characters": len(text),
            "keywords": sorted(set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", text)))[:80]}


def project_from_material(case_id: str, company: str, project: str, industry: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(x.get("text", "") for x in materials)
    evidence = [{"id": f"UP-{i+1}", "type": x["material_type"], "name": x["file_name"], "source": "用户上传",
                 "verification_status": "unverified", "page": "待复核"} for i, x in enumerate(materials)]
    return {"project_id": case_id, "company_name": company, "project_name": project, "industry_name": industry,
            "project_description": text[:12000], "fund_use": text[:4000], "evidence_items": evidence,
            "source_note": "用户上传材料自动解析；结论需人工复核。"}
