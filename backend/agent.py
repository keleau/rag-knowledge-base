from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import config
import llm
import rag
import storage
import tools
from textmatch import STOPWORDS, token_matches

COMPARE_WORDS = (
    "对比", "比较", "区别", "差异", "各自", "分别", "两份", "两篇",
    "哪个文档", "哪份文档", "哪篇文档", "哪个文件",
)
SUMMARY_WORDS = ("总结", "概括", "核心内容", "主要内容", "讲了什么")
SMALL_TALK_WORDS = ("你好", "您好", "hi", "hello", "在吗", "谢谢", "再见", "你是谁", "你能做什么")

REFUSAL_TEXT = (
    "知识库中未找到与这个问题相关的依据，因此不做推测性回答。"
    "可以换一种问法，或补充上传相关资料后再试。"
)

WATCH_WORDS = (
    "手表", "x1", "防水", "续航", "心率", "血氧", "睡眠", "运动", "表带", "充电",
    "nfc", "保修", "质保", "屏幕", "分辨率", "配色", "久坐", "门禁", "蓝牙", "gps",
    "包装", "游泳", "桑拿", "重量", "材质", "血压", "体温", "摄像头", "语音", "太阳能",
    "卫星", "wifi", "鳄鱼",
)
TECH_WORDS = (
    "知问", "技术", "检索", "分块", "tf-idf", "fastapi", "vue", "mcp", "部署",
    "接口", "文档格式", "存储", "json", "sse", "向量", "分词", "余弦", "docker",
)

EVIDENCE_THRESHOLD = 0.75
LOW_SCORE_SUPPLEMENT = 0.15


def evidence_coverage(question: str, contexts: list[dict[str, Any]]) -> tuple[float, list[str]]:
    tokens = [
        token.lower()
        for token in rag.significant_tokens(question)
        if len(token) >= 2 and token.lower() not in STOPWORDS
    ]
    tokens = list(dict.fromkeys(tokens))
    if not tokens:
        return 1.0, []
    haystack = "\n".join(str(item.get("text") or "") for item in contexts).lower()
    missing = [token for token in tokens if not token_matches(token, haystack)]
    return (len(tokens) - len(missing)) / len(tokens), missing


def unknown_terms(question: str) -> list[str]:
    tokens = [
        token.lower()
        for token in rag.significant_tokens(question)
        if len(token) >= 2 and token.lower() not in STOPWORDS
    ]
    tokens = list(dict.fromkeys(tokens))
    if not tokens:
        return []
    kb_text = "\n".join(str(chunk.get("text") or "") for chunk in storage.all_chunks()).lower()
    return [token for token in tokens if not token_matches(token, kb_text)]


def validate_citations(answer: str, context_count: int) -> tuple[str, list[int]]:
    references = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    invalid = sorted({value for value in references if value < 1 or value > context_count})
    if not invalid:
        return answer.strip(), []

    def replace(match: re.Match[str]) -> str:
        value = int(match.group(1))
        return match.group(0) if 1 <= value <= context_count else ""

    cleaned = re.sub(r"\[(\d+)\]", replace, answer)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), invalid


class AgentRunner:
    def __init__(
        self,
        question: str,
        history: list[dict[str, Any]] | None = None,
        *,
        mode: str | None = None,
        top_k: int | None = None,
        planner: Callable[
            [list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]
        ]
        | None = None,
        answerer: Callable[[list[dict[str, Any]]], AsyncIterator[str]] | None = None,
    ) -> None:
        self.question = (question or "").strip()
        self.history = history or []
        self.mode = mode or ("demo" if config.DEMO_MODE else "llm")
        self.top_k = max(1, min(top_k or config.TOP_K, 10))
        self._planner = planner
        self._answerer = answerer
        self.answer = ""
        self.contexts: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self._seen_contexts: set[tuple[str, int]] = set()
        self._answer_parts: list[str] = []

    async def run(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if not self.question:
            raise llm.LLMError("问题不能为空")
        if self._is_small_talk():
            async for event in self._finalize():
                yield event
            return
        if self.mode == "demo":
            async for event in self._run_demo():
                yield event
        else:
            async for event in self._run_llm():
                yield event

    # ------------------------------------------------------------------ #
    # demo / deterministic planner
    # ------------------------------------------------------------------ #
    async def _run_demo(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        documents = storage.list_documents()
        compact = re.sub(r"\s+", "", self.question)
        compare_intent = any(word in compact for word in COMPARE_WORDS)
        bundle = compare_intent or any(word in compact for word in SUMMARY_WORDS)

        if not documents:
            step, _ = await self._call_tool("list_documents", {})
            yield "step", step
        elif bundle:
            step, _ = await self._call_tool("list_documents", {})
            yield "step", step
            targets = self._rank_documents(documents)[: 2 if compare_intent else 1]
            for document in targets:
                step, execution = await self._call_tool(
                    "get_document_chunks", {"document_id": document["id"]}
                )
                yield "step", step
                self._absorb("get_document_chunks", execution)
        else:
            step, execution = await self._call_tool(
                "search_knowledge", {"query": self.question, "top_k": self.top_k}
            )
            yield "step", step
            self._absorb("search_knowledge", execution)

            top_score = self._top_score()
            if not self.contexts or top_score < LOW_SCORE_SUPPLEMENT:
                step, _ = await self._call_tool("list_documents", {})
                yield "step", step
                if documents:
                    target = self._rank_documents(documents)[0]
                    step, execution = await self._call_tool(
                        "get_document_chunks", {"document_id": target["id"]}
                    )
                    yield "step", step
                    self._absorb("get_document_chunks", execution)

        async for event in self._finalize():
            yield event

    def _rank_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        question = self.question.lower()

        def score(document: dict[str, Any]) -> tuple[int, str]:
            name = str(document.get("name") or "").lower()
            words = TECH_WORDS if ("知问" in name or "技术" in name) else WATCH_WORDS
            hits = sum(1 for word in words if word in question)
            return hits, str(document.get("created_at") or "")

        return sorted(documents, key=score, reverse=True)

    def _top_score(self) -> float:
        scores = [
            float(item["score"])
            for item in self.contexts
            if isinstance(item.get("score"), (int, float))
        ]
        return max(scores) if scores else 0.0

    # ------------------------------------------------------------------ #
    # real LLM tool-calling loop
    # ------------------------------------------------------------------ #
    async def _run_llm(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        planner = self._planner or llm.plan_completion
        messages: list[dict[str, Any]] = llm.build_agent_messages(
            self.history, self.question, len(storage.list_documents())
        )
        reached_limit = False

        for step_index in range(config.AGENT_MAX_STEPS):
            try:
                plan = await planner(messages, tools.TOOL_SPECS)
            except Exception as exc:
                step = self._record_check(
                    "规划降级",
                    f"规划失败，改为单次检索：{str(exc)[:120]}",
                    status="error",
                )
                yield "step", step
                step, execution = await self._call_tool(
                    "search_knowledge", {"query": self.question, "top_k": self.top_k}
                )
                yield "step", step
                self._absorb("search_knowledge", execution)
                break

            self._accumulate_usage(plan.get("usage"))
            raw_calls = plan.get("tool_calls") or []
            if not raw_calls:
                break

            normalized: list[dict[str, Any]] = []
            for call in raw_calls[:3]:
                normalized.append(
                    {
                        "id": call.get("id") or f"call_{uuid.uuid4().hex[:10]}",
                        "type": "function",
                        "function": {
                            "name": (call.get("function") or {}).get("name") or "",
                            "arguments": (call.get("function") or {}).get("arguments") or "{}",
                        },
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": plan.get("content") or "",
                    "tool_calls": normalized,
                }
            )

            for call in normalized:
                name, arguments, error = self._parse_tool_call(call)
                if error:
                    step = self._record_check(
                        "工具调用失败", error, status="error", name="tool_error"
                    )
                    yield "step", step
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(
                                {"ok": False, "error": error}, ensure_ascii=False
                            ),
                        }
                    )
                    continue

                step, execution = await self._call_tool(name, arguments)
                yield "step", step
                self._absorb(name, execution)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": tools.observation_text(name, arguments, execution),
                    }
                )

            if step_index == config.AGENT_MAX_STEPS - 1:
                reached_limit = True

        if reached_limit:
            step = self._record_check(
                "达到步数上限",
                f"已完成 {config.AGENT_MAX_STEPS} 步，使用已收集资料回答",
            )
            yield "step", step

        async for event in self._finalize():
            yield event

    def _parse_tool_call(
        self, call: dict[str, Any]
    ) -> tuple[str, dict[str, Any], str]:
        function = call.get("function") or {}
        name = str(function.get("name") or "").strip()
        raw = function.get("arguments")
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            return name, {}, "工具参数不是合法 JSON"
        if not isinstance(arguments, dict):
            return name, {}, "工具参数必须是 JSON 对象"
        if name not in tools.TOOL_NAMES:
            return name, arguments, f"未知工具：{name or '(空)'}"
        return name, arguments, ""

    # ------------------------------------------------------------------ #
    # tools / context / trace
    # ------------------------------------------------------------------ #
    async def _call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        execution = await tools.execute(name, arguments)
        step = self._record_tool_step(name, arguments, execution)
        return step, execution

    def _record_tool_step(
        self, name: str, arguments: dict[str, Any], execution: dict[str, Any]
    ) -> dict[str, Any]:
        ok = bool(execution.get("ok"))
        result = execution.get("result")
        result_count: int | None = None
        if ok and name == "search_knowledge":
            result_count = len(result) if isinstance(result, list) else 0
            summary = f"命中 {result_count} 条片段" if result_count else "未命中相关片段"
        elif ok and name == "list_documents":
            result_count = len(result) if isinstance(result, list) else 0
            summary = f"共 {result_count} 篇文档"
        elif ok and name == "get_document_chunks":
            chunks = (result or {}).get("chunks", []) if isinstance(result, dict) else []
            result_count = len(chunks)
            document_name = (result or {}).get("document_name") if isinstance(result, dict) else ""
            summary = f"读取「{document_name}」的 {result_count} 个分块"
        elif ok:
            summary = "执行完成"
        else:
            summary = str(execution.get("error") or "执行失败")[:160]

        safe_args: dict[str, Any] = {}
        for key in ("query", "top_k", "document_id"):
            if arguments.get(key) is not None:
                safe_args[key] = arguments[key]
        if ok and name == "get_document_chunks" and isinstance(result, dict):
            safe_args["document_name"] = result.get("document_name")

        step = {
            "id": f"s{len(self.trace) + 1}",
            "name": name,
            "label": tools.TOOL_LABELS.get(name, name),
            "status": "done" if ok else "error",
            "summary": summary,
            "duration_ms": execution.get("duration_ms", 0),
            "result_count": result_count,
            "args": safe_args,
            "kind": "tool",
        }
        self.trace.append(step)
        return step

    def _record_check(
        self,
        label: str,
        summary: str,
        *,
        status: str = "done",
        name: str = "agent_check",
        result_count: int | None = None,
    ) -> dict[str, Any]:
        step = {
            "id": f"s{len(self.trace) + 1}",
            "name": name,
            "label": label,
            "status": status,
            "summary": summary,
            "result_count": result_count,
            "kind": "check",
        }
        self.trace.append(step)
        return step

    def _absorb(self, name: str, execution: dict[str, Any]) -> None:
        if not execution.get("ok"):
            return
        result = execution.get("result")
        if name == "search_knowledge" and isinstance(result, list):
            for item in result:
                self._add_context(item)
        elif name == "get_document_chunks" and isinstance(result, dict):
            document_id = result.get("document_id") or ""
            document_name = result.get("document_name") or ""
            for chunk in result.get("chunks", []):
                self._add_context(
                    {
                        "document_id": document_id,
                        "document_name": document_name,
                        "chunk_id": chunk.get("chunk_id"),
                        "chunk_index": chunk.get("chunk_index", 0),
                        "text": chunk.get("text", ""),
                    }
                )

    def _add_context(self, item: dict[str, Any]) -> None:
        key = (str(item.get("document_id") or ""), int(item.get("chunk_index") or 0))
        if key in self._seen_contexts:
            return
        if len(self.contexts) >= config.AGENT_MAX_CONTEXTS:
            return
        context = {
            "document_id": item.get("document_id"),
            "document_name": item.get("document_name"),
            "chunk_id": item.get("chunk_id"),
            "chunk_index": item.get("chunk_index", 0),
            "text": item.get("text") or "",
        }
        if isinstance(item.get("score"), (int, float)):
            context["score"] = item["score"]
        self.contexts.append(context)
        self._seen_contexts.add(key)

    # ------------------------------------------------------------------ #
    # final answer / evidence / citation checks
    # ------------------------------------------------------------------ #
    def _is_bundle_question(self) -> bool:
        compact = re.sub(r"\s+", "", self.question)
        return any(
            word in compact for word in SUMMARY_WORDS + COMPARE_WORDS
        )

    def _is_small_talk(self) -> bool:
        compact = re.sub(r"\s+", "", self.question).lower()
        return len(compact) <= 12 and any(
            word in compact for word in SMALL_TALK_WORDS
        )

    async def _finalize(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        bundle = self._is_bundle_question()
        refuse = False
        reason = ""

        if not self.contexts:
            if self._is_small_talk():
                step = self._record_check("证据校验", "闲聊问题，无需引用资料", result_count=0)
                yield "step", step
            else:
                refuse = True
                reason = "未检索到可引用资料"
                step = self._record_check(
                    "证据校验", f"{reason}，将明确拒答", result_count=0
                )
                yield "step", step
        else:
            coverage, missing = evidence_coverage(self.question, self.contexts)
            unknown = [] if bundle else unknown_terms(self.question)
            if unknown:
                refuse = True
                reason = f"知识库未收录：{'、'.join(unknown[:4])}"
                step = self._record_check(
                    "证据校验", f"{reason}；转为拒答", result_count=0
                )
                yield "step", step
            elif not bundle and self.mode == "demo" and coverage < EVIDENCE_THRESHOLD:
                refuse = True
                missing_text = "、".join(missing[:4]) or "关键信息"
                reason = f"资料覆盖不足（{coverage:.0%}），缺少：{missing_text}"
                step = self._record_check(
                    "证据校验", f"{reason}；转为拒答", result_count=0
                )
                yield "step", step
            else:
                note = "（总结/对比问题，按整篇资料作答）" if bundle else ""
                step = self._record_check(
                    "证据校验",
                    f"{len(self.contexts)} 条资料，问题覆盖 {coverage:.0%}{note}",
                    result_count=len(self.contexts),
                )
                yield "step", step

        if refuse:
            self.contexts = []

        yield "sources", {"sources": self.contexts}

        if refuse:
            self._answer_parts.append(REFUSAL_TEXT)
            for start in range(0, len(REFUSAL_TEXT), 10):
                yield "delta", {"content": REFUSAL_TEXT[start : start + 10]}
                await asyncio.sleep(0.01)
        else:
            try:
                if self._answerer is not None:
                    async for token in self._answerer(self.contexts):
                        self._answer_parts.append(token)
                        yield "delta", {"content": token}
                elif self.mode == "demo":
                    answer = await asyncio.to_thread(
                        llm.demo_answer, self.question, self.contexts
                    )
                    answer, _ = validate_citations(answer, len(self.contexts))
                    self._answer_parts.append(answer)
                    for start in range(0, len(answer), 8):
                        piece = answer[start : start + 8]
                        yield "delta", {"content": piece}
                        await asyncio.sleep(0.01)
                else:
                    messages = llm.build_messages(
                        self.history, self.question, self.contexts
                    )
                    async for token in llm.stream_completion(
                        messages, on_usage=self._accumulate_usage
                    ):
                        self._answer_parts.append(token)
                        yield "delta", {"content": token}
            except asyncio.CancelledError:
                raise

        raw_answer = "".join(self._answer_parts).strip()
        if not raw_answer:
            raise llm.LLMError("模型没有返回内容，请重试")

        cleaned, invalid = validate_citations(raw_answer, len(self.contexts))
        self.answer = cleaned
        if invalid:
            summary = f"移除 {len(invalid)} 个无效引用：{', '.join(f'[{n}]' for n in invalid)}"
            status = "error"
        elif self.contexts:
            summary = f"{len(self.contexts)} 条引用编号均在来源范围内"
            status = "done"
        else:
            summary = "本轮没有引用来源，已确保回答不含编号引用"
            status = "done"
        step = self._record_check(
            "引用校验",
            summary,
            status=status,
            name="citation_check",
            result_count=len(self.contexts),
        )
        yield "step", step

    def _accumulate_usage(self, usage: dict[str, Any] | None) -> None:
        if not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                self.usage[key] = int(self.usage.get(key, 0)) + int(value)
