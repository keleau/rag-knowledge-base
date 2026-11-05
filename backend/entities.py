from __future__ import annotations

import re
from typing import Any

import jieba
import jieba.posseg as pseg

from textmatch import STOPWORDS

IDENTIFIER = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
COMPOUND_IDENTIFIER = re.compile(r"\b([A-Za-z]{2,}(?:-[A-Za-z0-9]+)+)\b")
FILE_NAME = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*\.(?:py|js|ts|vue|json|md|css|html|sql))\b")
METRIC = re.compile(r"\d+(?:\.\d+)?\s*(?:%|ms|秒|分钟|步|次|倍|天|周|个月|年|MB|KB|GB|字|题|条|篇|种|层)")

IDENTIFIER_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "true", "false", "null",
    "none", "self", "def", "class", "return", "import", "async", "await", "const",
    "let", "var", "function", "new", "typeof", "string", "number", "boolean",
    "object", "array", "json", "http", "https", "get", "post", "put", "delete",
    "api", "app", "main", "test", "tests", "data", "src", "dist", "node",
}

API_CALL = re.compile(r"\b(?:api|axios|http|client|service)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
COMPONENT = re.compile(r"(?:defineComponent|export\s+default)\s*(?:<[^>]+>)?\s*\{?")
JIEBA_KINDS = {"n", "nz", "vn", "nt", "nr", "eng"}


def _kind_for(token: str) -> str:
    if token.endswith((".py", ".js", ".ts", ".vue", ".json", ".md", ".css", ".html", ".sql")):
        return "term"
    if re.fullmatch(r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+", token):
        return "component"
    if token.isupper() and len(token) > 2:
        return "term"
    if "_" in token or re.fullmatch(r"[a-z]+[A-Z][A-Za-z0-9]*", token):
        return "function"
    return "term"


def extract_entities(text: str, limit: int = 40) -> list[dict[str, Any]]:
    """从项目文档/代码里抽取题目可以锚定的“项目实体”。

    顺序很重要：先抽英文标识符和数字指标，再分词抽中文名词。
    英文标识符不能交给 jieba，否则 DocumentDrawer 会被切碎。
    """
    value = str(text or "")
    if not value.strip():
        return []

    found: dict[str, dict[str, Any]] = {}

    def add(name: str, kind: str) -> None:
        name = name.strip()
        if not name or len(name) < 2:
            return
        if name.lower() in IDENTIFIER_STOPWORDS:
            return
        found.setdefault(name, {"name": name, "kind": kind, "count": value.count(name)})

    for match in METRIC.finditer(value):
        add(match.group(0).replace(" ", ""), "metric")
    for match in FILE_NAME.finditer(value):
        add(match.group(1), "term")
    for match in COMPOUND_IDENTIFIER.finditer(value):
        add(match.group(1), "term")
    for match in IDENTIFIER.finditer(value):
        add(match.group(1), _kind_for(match.group(1)))

    try:
        for word, flag in pseg.cut(value):
            word = word.strip()
            if len(word) < 2 or flag not in JIEBA_KINDS:
                continue
            if word in STOPWORDS or word.lower() in IDENTIFIER_STOPWORDS:
                continue
            if not any("一" <= ch <= "鿿" for ch in word):
                continue
            add(word, "term")
    except Exception:  # 分词失败不影响英文实体
        pass

    ranked = sorted(found.values(), key=lambda item: (item["count"], len(item["name"])), reverse=True)
    return [{"name": item["name"], "kind": item["kind"]} for item in ranked[:limit]]


def extract_api_calls(code: str) -> list[str]:
    return sorted({match.group(1) for match in API_CALL.finditer(code or "")})
