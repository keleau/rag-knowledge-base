from __future__ import annotations

import re
from typing import Any

LANGUAGE_BY_EXT = {".vue": "vue", ".ts": "typescript", ".js": "javascript"}


class CodeParseError(ValueError):
    pass


def _language(file_name: str) -> str:
    lower = file_name.lower()
    for ext, language in LANGUAGE_BY_EXT.items():
        if lower.endswith(ext):
            return language
    raise CodeParseError("只支持 .vue / .ts / .js 单文件")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _find_block_end(text: str, start: int) -> int:
    """从 start 位置（通常是 {）开始做括号匹配，跳过字符串与注释。返回结束字符下标。"""
    depth = 0
    index = start
    length = len(text)
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False
    while index < length:
        ch = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                index += 1
        elif in_string:
            if ch == "\\":
                index += 1
            elif ch == in_string:
                in_string = None
        elif ch in {"'", '"', "`"}:
            in_string = ch
        elif ch == "/" and nxt == "/":
            in_line_comment = True
            index += 1
        elif ch == "/" and nxt == "*":
            in_block_comment = True
            index += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return length - 1


def _script_blocks(content: str) -> list[tuple[str, int]]:
    """返回 (script 内容, 内容起始行号偏移)。"""
    blocks: list[tuple[str, int]] = []
    for match in re.finditer(r"<script\b[^>]*>(.*?)</script>", content, re.S):
        body = match.group(1)
        blocks.append((body, _line_of(content, match.start(1)) - 1))
    return blocks


def _template_block(content: str) -> tuple[str, int]:
    match = re.search(r"<template\b[^>]*>(.*?)</template>", content, re.S)
    if not match:
        return "", 0
    return match.group(1), _line_of(content, match.start(1)) - 1


def _add(symbols: list[dict[str, Any]], name: str, kind: str, line: int, end_line: int | None = None) -> None:
    name = (name or "").strip()
    if not name or len(name) < 2:
        return
    if any(item["name"] == name and item["kind"] == kind for item in symbols):
        return
    symbols.append({"name": name, "kind": kind, "line": line, "end_line": end_line or line})


def _parse_js(body: str, offset: int, symbols: list[dict[str, Any]]) -> None:
    lines = body.splitlines()

    for index, line in enumerate(lines, start=1):
        line_no = index + offset

        for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*ref(?:<[^>]*>)?\(", line):
            _add(symbols, match.group(1), "state", line_no)
        for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*reactive(?:<[^>]*>)?\(", line):
            _add(symbols, match.group(1), "state", line_no)
        for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*computed(?:<[^>]*>)?\(", line):
            _add(symbols, match.group(1), "computed", line_no)
        for match in re.finditer(r"\bwatch(?:Effect)?\(\s*(?:\(\)\s*=>\s*)?([A-Za-z_$][\w$.]*)", line):
            _add(symbols, match.group(1), "watch", line_no)
        for match in re.finditer(r"\bemit\(\s*['\"]([^'\"]+)['\"]", line):
            _add(symbols, match.group(1), "emit", line_no)
        for match in re.finditer(r"\b(?:api|axios|http|service)\.([A-Za-z_$][\w$]*)\s*\(", line):
            _add(symbols, f"api.{match.group(1)}", "api", line_no)
        for match in re.finditer(r"\bfetch\(\s*['\"]([^'\"]+)['\"]", line):
            _add(symbols, match.group(1), "api", line_no)
        for match in re.finditer(r"\bdefineProps(?:<[^>]*>)?\(\s*\[([^\]]*)\]", line):
            for name in re.findall(r"['\"]([A-Za-z_$][\w$]*)['\"]", match.group(1)):
                _add(symbols, name, "prop", line_no)
        for lifecycle in ("onMounted", "onUnmounted", "onBeforeMount", "onBeforeUnmount", "onUpdated", "onActivated", "onDeactivated"):
            if re.search(rf"\b{lifecycle}\(", line):
                _add(symbols, lifecycle, "lifecycle", line_no)

    # 函数：function foo( / const foo = (...) => / const foo = async (...) => / 对象方法 foo(...)
    # span 约定：line 是函数起始行，end_line 是包含闭合 } 的行（闭区间）。
    patterns = [
        re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*async\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"),
        re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"),
        re.compile(r"^\s{2,}([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(body):
            name = match.group(1)
            if name in {"if", "for", "while", "switch", "catch", "function", "return"}:
                continue
            line_no = _line_of(body, match.start()) + offset
            brace = body.find("{", match.end())
            if brace < 0:
                _add(symbols, name, "function", line_no)
                continue
            end_index = _find_block_end(body, brace)
            end_line = _line_of(body, end_index) + offset
            _add(symbols, name, "function", line_no, end_line)

    # 组件名：defineComponent({ name: 'X' }) 或 export default { name: 'X' }
    for match in re.finditer(r"\bname\s*:\s*['\"]([A-Za-z_$][\w$]*)['\"]", body):
        _add(symbols, match.group(1), "component", _line_of(body, match.start()) + offset)


def _parse_template(body: str, offset: int, symbols: list[dict[str, Any]]) -> None:
    for match in re.finditer(r"@([A-Za-z-]+)=\"([^\"]+)\"", body):
        handler = match.group(2).split("(")[0].strip()
        _add(symbols, handler, "binding", _line_of(body, match.start()) + offset)
    for match in re.finditer(r"v-(?:model|if|else-if|show)(?::[^\s=]+)?=\"([^\"]+)\"", body):
        expression = match.group(1).strip()
        for name in re.findall(r"[A-Za-z_$][\w$]*", expression):
            _add(symbols, name, "binding", _line_of(body, match.start()) + offset)
    for match in re.finditer(r"v-for=\"\(?\s*([A-Za-z_$][\w$]*)", body):
        _add(symbols, match.group(1), "binding", _line_of(body, match.start()) + offset)


def parse_code(file_name: str, content: str) -> dict[str, Any]:
    language = _language(file_name)
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise CodeParseError("代码文件是空的")
    line_count = text.count("\n") + 1
    symbols: list[dict[str, Any]] = []

    if language == "vue":
        script_blocks = _script_blocks(text)
        for body, offset in script_blocks:
            _parse_js(body, offset, symbols)
        template_body, template_offset = _template_block(text)
        if template_body:
            _parse_template(template_body, template_offset, symbols)
        if not script_blocks and not template_body:
            raise CodeParseError("这个 .vue 文件里没有找到 <script> 或 <template>")
    else:
        _parse_js(text, 0, symbols)

    component = next((item["name"] for item in symbols if item["kind"] == "component"), "")
    if not component and language == "vue":
        component = file_name.split("/")[-1].rsplit(".", 1)[0]

    return {
        "file_name": file_name,
        "language": language,
        "line_count": line_count,
        "component": component,
        "symbols": symbols,
        "symbol_names": [item["name"] for item in symbols],
    }


def get_lines(content: str) -> list[str]:
    return str(content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def line_text(content: str, line_no: int) -> str:
    lines = get_lines(content)
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


def snippet(content: str, start: int, end: int) -> str:
    lines = get_lines(content)
    start = max(1, start)
    end = min(len(lines), max(start, end))
    return "\n".join(lines[start - 1 : end])


def symbol_names(parsed: dict[str, Any]) -> list[str]:
    return list(parsed.get("symbol_names") or [])
