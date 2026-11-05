from __future__ import annotations

import re
from typing import Any

import config
import rag
from textmatch import STOPWORDS


def normalize(text: Any) -> str:
    value = str(text or "")
    value = value.replace("　", " ")
    for full, half in zip("，。；：！？（）【】“”‘’", ",.;:!?()[]\"\"''"):
        value = value.replace(full, half)
    return re.sub(r"\s+", "", value).lower()


def normalized_text(text: Any) -> str:
    return " ".join(re.sub(r"\s+", " ", str(text or "")).lower().split())


def significant_set(text: Any) -> set[str]:
    tokens = [
        token.lower()
        for token in rag.significant_tokens(str(text or ""))
        if len(token) >= 2 and token.lower() not in STOPWORDS
    ]
    return set(tokens)


def overlap(a: Any, b: Any) -> float:
    ta, tb = significant_set(a), significant_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def check_evidence(question: dict[str, Any], chunks: list[dict[str, Any]], code_content: str | None) -> tuple[bool, str]:
    source = question.get("source") or {}
    if question.get("type") == "code":
        if code_content is None:
            return False, "项目里没有上传代码"
        lines = code_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        try:
            start = int(source.get("line_start") or 0)
            end = int(source.get("line_end") or start)
        except (TypeError, ValueError):
            return False, "代码行号不是整数"
        if not (1 <= start <= end <= len(lines)):
            return False, "代码行号越界"
        quote = normalize(source.get("quote"))
        if quote and quote not in normalize("\n".join(lines[start - 1 : end])):
            return False, "代码引用的 quote 不在行区间内"
        return True, ""
    quote = normalize(source.get("quote"))
    if not quote:
        return False, "缺少来源引用"
    if not any(quote in normalize(chunk.get("text")) for chunk in chunks):
        return False, "引用的 quote 不在来源文档中"
    return True, ""


def check_entity(question: dict[str, Any], entity_names: set[str], symbol_names: set[str]) -> tuple[bool, str]:
    # 只看题干和选项：题目自带的 entities 字段是模型声明，不能拿来给自己“作证”
    haystack = normalize(
        " ".join(
            [str(question.get("prompt") or "")]
            + [str(option) for option in (question.get("options") or [])]
        )
    )
    for name in entity_names:
        if normalize(name) and normalize(name) in haystack:
            return True, ""
    for name in symbol_names:
        if normalize(name) and normalize(name) in haystack:
            return True, ""
    return False, "题干没有命中任何项目实体"


def check_dedup(question: dict[str, Any], seen_prompts: list[str], threshold: float | None = None) -> tuple[bool, str]:
    threshold = threshold if threshold is not None else config.DEDUP_OVERLAP_THRESHOLD
    prompt = question.get("prompt") or ""
    for previous in seen_prompts:
        if overlap(prompt, previous) >= threshold:
            return False, "与已有题目重复"
    return True, ""


def check_code_shape(question: dict[str, Any], code_content: str | None) -> tuple[bool, str]:
    if question.get("type") != "code":
        return True, ""
    source = question.get("source") or {}
    mode = question.get("code_mode")
    symbols = [str(item) for item in (source.get("symbols") or []) if item]
    if code_content is None:
        return False, "项目里没有上传代码"
    for symbol in symbols:
        bare = symbol.split(".")[-1]
        if not re.search(rf"\b{re.escape(bare)}\b", code_content):
            return False, f"符号 {symbol} 不在代码中"
    if mode == "implement":
        if len(symbols) < 2:
            return False, "实现题至少需要 2 个真实符号"
        rubric = question.get("rubric") or []
        if not any((item.get("kind") == "symbol") for item in rubric):
            return False, "实现题缺少 symbol 类得分点"
    if mode == "explain" and not symbols:
        return False, "讲解题至少要引用 1 个符号"
    return True, ""


def check_paper(questions: list[dict[str, Any]], entities_ok: int) -> tuple[bool, str]:
    if len(questions) < 3:
        return False, "题目太少"
    tags = [item.get("tag") for item in questions if item.get("tag")]
    if len(set(tags)) < min(5, len(tags)):
        return False, "覆盖标签不足"
    per_tag: dict[str, int] = {}
    for tag in tags:
        per_tag[tag] = per_tag.get(tag, 0) + 1
    if any(count > 3 for count in per_tag.values()):
        return False, "同一标签题目超过 3 道"
    code_items = [item for item in questions if item.get("type") == "code"]
    if code_items and all(item.get("code_mode") == "locate" for item in code_items):
        return False, "代码题不能全是定位题"
    return True, ""


def run_gates(
    question: dict[str, Any],
    *,
    chunks: list[dict[str, Any]],
    code_content: str | None,
    entity_names: set[str],
    symbol_names: set[str],
    seen_prompts: list[str],
) -> tuple[bool, str]:
    for ok, reason in (
        check_evidence(question, chunks, code_content),
        check_entity(question, entity_names, symbol_names),
        check_code_shape(question, code_content),
        check_dedup(question, seen_prompts),
    ):
        if not ok:
            return False, reason
    return True, ""


def symbol_mentions(answer: str, symbols: list[str]) -> list[dict[str, Any]]:
    text = str(answer or "")
    text_lower = text.lower()
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        bare = symbol.split(".")[-1]
        variants = {symbol, bare, bare.replace("_", "").replace("-", "")}
        mentioned = any(variant and (variant in text or variant.lower() in text_lower) for variant in variants)
        results.append({"symbol": symbol, "mentioned": mentioned})
    return results
