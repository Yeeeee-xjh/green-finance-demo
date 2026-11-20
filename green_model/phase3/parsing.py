"""Auditable local document parsing.

The parser keeps all extracted text.  It chunks long content into evidence
records instead of truncating it, and it never assigns a page number to a
format that has no stable page concept.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


CHUNK_SIZE = 8_000


@dataclass(frozen=True)
class ParsedFragment:
    text: str
    page_number: int | None
    bbox: dict[str, float] | None
    locator_type: str
    locator: dict[str, Any]
    extraction_method: str
    table_cell: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    parser_name: str
    parser_version: str
    page_count: int | None
    fragments: list[ParsedFragment] = field(default_factory=list)
    needs_ocr: bool = False
    ocr_reason: str | None = None


class UnsupportedDocument(ValueError):
    pass


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunks(text: str, size: int = CHUNK_SIZE) -> Iterable[tuple[int, str]]:
    if not text:
        return
    for start in range(0, len(text), size):
        yield start, text[start : start + size]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())


class LocalDocumentParser:
    version = "phase3-local-parser/1.0"

    def parse(self, path: str | Path, *, mime_type: str | None = None) -> ParsedDocument:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"原始文件不存在：{source}")
        suffix = source.suffix.lower()
        if suffix == ".pdf" or mime_type == "application/pdf":
            return self._pdf(source)
        if suffix == ".docx":
            return self._docx(source)
        if suffix in {".xlsx", ".xlsm"}:
            return self._xlsx(source)
        if suffix in {".html", ".htm"}:
            return self._html(source)
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return ParsedDocument(
                parser_name="image-ocr-router",
                parser_version=self.version,
                page_count=1,
                needs_ocr=True,
                ocr_reason="图片材料需要OCR，当前阶段不生成项目事实。",
            )
        if suffix in {".txt", ".csv", ".json", ".jsonl", ".md"}:
            return self._text(source)
        raise UnsupportedDocument(f"暂不支持该文件类型：{suffix or '无扩展名'}")

    def _pdf(self, path: Path) -> ParsedDocument:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        fragments: list[ParsedFragment] = []
        total_visible_chars = 0
        for page_no, page in enumerate(reader.pages, start=1):
            positioned: list[tuple[str, float, float, float]] = []

            def visitor(text, _cm, tm, _font, font_size):
                cleaned = str(text or "")
                if cleaned.strip():
                    try:
                        positioned.append((cleaned, float(tm[4]), float(tm[5]), float(font_size or 0)))
                    except (TypeError, ValueError, IndexError):
                        positioned.append((cleaned, 0.0, 0.0, float(font_size or 0)))

            text = page.extract_text(visitor_text=visitor) or ""
            total_visible_chars += len(text.strip())
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if positioned:
                x0 = max(0.0, min(item[1] for item in positioned))
                y0 = max(0.0, min(item[2] for item in positioned))
                x1 = min(width, max(item[1] + max(len(item[0]), 1) * max(item[3], 8.0) * 0.55 for item in positioned))
                y1 = min(height, max(item[2] + max(item[3], 8.0) for item in positioned))
                bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "page_width": width, "page_height": height}
            elif text.strip():
                bbox = {"x0": 0.0, "y0": 0.0, "x1": width, "y1": height, "page_width": width, "page_height": height}
            else:
                bbox = None
            for start, chunk in _chunks(text):
                fragments.append(ParsedFragment(
                    text=chunk,
                    page_number=page_no,
                    bbox=bbox,
                    locator_type="pdf_page_bbox",
                    locator={"page": page_no, "char_start": start, "char_end": start + len(chunk)},
                    extraction_method="pypdf_text_operator",
                ))
        needs_ocr = bool(reader.pages) and total_visible_chars < max(20, len(reader.pages) * 5)
        if needs_ocr:
            fragments = []
        return ParsedDocument(
            parser_name="pypdf",
            parser_version=self.version,
            page_count=len(reader.pages),
            fragments=fragments,
            needs_ocr=needs_ocr,
            ocr_reason="PDF未提取到足够的文本层，已转入OCR待处理。" if needs_ocr else None,
        )

    def _docx(self, path: Path) -> ParsedDocument:
        from docx import Document as DocxDocument

        document = DocxDocument(str(path))
        fragments: list[ParsedFragment] = []
        for index, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text.strip()
            for start, chunk in _chunks(text):
                fragments.append(ParsedFragment(
                    text=chunk,
                    page_number=None,
                    bbox=None,
                    locator_type="docx_paragraph",
                    locator={"paragraph": index, "char_start": start, "char_end": start + len(chunk)},
                    extraction_method="python_docx",
                ))
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if text:
                    fragments.append(ParsedFragment(
                        text=text,
                        page_number=None,
                        bbox=None,
                        locator_type="docx_table_row",
                        locator={"table": table_index, "row": row_index},
                        extraction_method="python_docx",
                        table_cell=f"表{table_index}第{row_index}行",
                    ))
        return ParsedDocument("python-docx", self.version, None, fragments)

    def _xlsx(self, path: Path) -> ParsedDocument:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        fragments: list[ParsedFragment] = []
        try:
            for sheet in workbook.worksheets:
                for row_index, row in enumerate(sheet.iter_rows(), start=1):
                    values = [str(cell.value).strip() for cell in row if cell.value not in (None, "")]
                    if not values:
                        continue
                    text = " | ".join(values)
                    fragments.append(ParsedFragment(
                        text=text,
                        page_number=None,
                        bbox=None,
                        locator_type="xlsx_row",
                        locator={"sheet": sheet.title, "row": row_index},
                        extraction_method="openpyxl",
                        table_cell=f"{sheet.title}!{row_index}:{row_index}",
                    ))
        finally:
            workbook.close()
        return ParsedDocument("openpyxl", self.version, None, fragments)

    def _html(self, path: Path) -> ParsedDocument:
        data = path.read_bytes()
        text = data.decode("utf-8-sig", errors="replace")
        parser = _VisibleTextParser()
        parser.feed(text)
        snapshot_hash = hashlib.sha256(data).hexdigest()
        fragments: list[ParsedFragment] = []
        for index, paragraph in enumerate(parser.parts, start=1):
            for start, chunk in _chunks(paragraph):
                fragments.append(ParsedFragment(
                    text=chunk,
                    page_number=None,
                    bbox=None,
                    locator_type="html_snapshot_paragraph",
                    locator={"snapshot_sha256": snapshot_hash, "paragraph": index, "char_start": start, "char_end": start + len(chunk)},
                    extraction_method="stdlib_html_parser",
                ))
        return ParsedDocument("html-snapshot", self.version, None, fragments)

    def _text(self, path: Path) -> ParsedDocument:
        data = path.read_bytes()
        text = data.decode("utf-8-sig", errors="replace")
        fragments: list[ParsedFragment] = []
        line = 1
        for start, chunk in _chunks(text):
            line_end = line + chunk.count("\n")
            fragments.append(ParsedFragment(
                text=chunk,
                page_number=None,
                bbox=None,
                locator_type="text_lines",
                locator={"line_start": line, "line_end": line_end, "char_start": start, "char_end": start + len(chunk)},
                extraction_method="utf8_text",
            ))
            line = line_end + 1
        return ParsedDocument("plain-text", self.version, None, fragments)
