from __future__ import annotations

import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".docx", ".pdf"}


class ParseError(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ").replace("\ufeff", "")
    text = re.sub(r"[\u200b-\u200d\u2060]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_plain(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ParseError("服务端缺少 python-docx，无法解析 Word 文档") from exc

    document = Document(str(path))
    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower()
        if style.startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            lines.append(f"{'#' * min(int(level), 6)} {text}")
        else:
            lines.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n\n".join(lines)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParseError("服务端缺少 pypdf，无法解析 PDF 文档") from exc

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ParseError("PDF 已加密，暂时无法读取")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"PDF 解析失败：{exc}") from exc
    return "\n\n".join(page for page in pages if page)


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ParseError(f"暂不支持 {extension or '该'} 格式，请上传 txt / md / docx / pdf")
    try:
        if extension in {".txt", ".md", ".markdown"}:
            text = _read_plain(path)
        elif extension == ".docx":
            text = _read_docx(path)
        else:
            text = _read_pdf(path)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"文档读取失败：{exc}") from exc

    cleaned = _clean(text)
    if not cleaned:
        raise ParseError("未能从文档中提取到有效文字")
    return cleaned
