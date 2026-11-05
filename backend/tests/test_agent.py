from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import agent
import config
from textmatch import STOPWORDS


def fake_document() -> dict:
    return {
        "id": "doc-1",
        "name": "智能健康手表产品手册.docx",
        "chunk_count": 1,
        "char_count": 30,
    }


def fake_context() -> dict:
    return {
        "document_id": "doc-1",
        "document_name": "智能健康手表产品手册.docx",
        "chunk_id": "chunk-1",
        "chunk_index": 0,
        "text": "手表整机重量约 32 克。官方提供 12 个月质保，表带等易耗件不在质保范围内。",
        "score": 0.8,
    }


class CitationTests(unittest.TestCase):
    def test_removes_out_of_range_citations(self) -> None:
        cleaned, invalid = agent.validate_citations("结论 [1]，补充 [3]。", 2)
        self.assertEqual(invalid, [3])
        self.assertIn("[1]", cleaned)
        self.assertNotIn("[3]", cleaned)

    def test_keeps_valid_citations(self) -> None:
        cleaned, invalid = agent.validate_citations("结论 [1][2]。", 2)
        self.assertEqual(invalid, [])
        self.assertEqual(cleaned, "结论 [1][2]。")

    def test_small_talk_detection(self) -> None:
        runner = agent.AgentRunner("你好")
        self.assertTrue(runner._is_small_talk())
        self.assertFalse(agent.AgentRunner("手表续航多久？")._is_small_talk())


class EvidenceTests(unittest.TestCase):
    def test_coverage_uses_aliases(self) -> None:
        coverage, missing = agent.evidence_coverage(
            "质保多久？", [{"text": "官方提供 12 个月质保"}]
        )
        self.assertEqual(coverage, 1.0)
        self.assertEqual(missing, [])

    def test_missing_evidence(self) -> None:
        coverage, missing = agent.evidence_coverage(
            "支持太阳能充电吗？", [{"text": "磁吸充电底座可在 90 分钟内充满"}]
        )
        self.assertLess(coverage, agent.EVIDENCE_THRESHOLD)
        self.assertIn("太阳能", missing)

    def test_stopwords_are_ignored(self) -> None:
        self.assertIn("什么", STOPWORDS)
        coverage, _ = agent.evidence_coverage("质保多久？", [{"text": "12 个月质保"}])
        self.assertEqual(coverage, 1.0)


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, runner: agent.AgentRunner) -> list[tuple[str, dict]]:
        return [event async for event in runner.run()]

    async def test_max_steps_is_enforced(self) -> None:
        calls = {"planner": 0, "tool": 0}

        async def planner(messages, specs):
            calls["planner"] += 1
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call-{calls['planner']}",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": json.dumps({"query": "质保"}),
                        },
                    }
                ],
                "usage": {},
            }

        async def execute(name, arguments):
            calls["tool"] += 1
            return {
                "ok": True,
                "name": name,
                "result": [fake_context()],
                "duration_ms": 1,
            }

        async def answerer(contexts):
            yield "官方提供 12 个月质保 [1]"

        with (
            patch.object(agent.storage, "list_documents", return_value=[fake_document()]),
            patch.object(agent.storage, "all_chunks", return_value=[{"text": fake_context()["text"]}]),
            patch.object(agent.tools, "execute", side_effect=execute),
            patch.object(config, "AGENT_MAX_STEPS", 3),
        ):
            runner = agent.AgentRunner(
                "质保多久？", mode="llm", planner=planner, answerer=answerer
            )
            await self.collect(runner)

        self.assertEqual(calls["tool"], 3)
        self.assertIn("12 个月质保", runner.answer)
        labels = [step["label"] for step in runner.trace]
        self.assertIn("达到步数上限", labels)
        self.assertEqual(runner.usage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    async def test_refuses_without_evidence(self) -> None:
        async def planner(messages, specs):
            return {"content": "", "tool_calls": [], "usage": {}}

        async def answerer(contexts):
            raise AssertionError("无证据时不应调用回答模型")
            yield ""  # pragma: no cover

        runner = agent.AgentRunner(
            "支持太阳能充电吗？", mode="llm", planner=planner, answerer=answerer
        )
        await self.collect(runner)

        self.assertEqual(runner.contexts, [])
        self.assertEqual(runner.answer, agent.REFUSAL_TEXT)
        self.assertTrue(any(step["label"] == "证据校验" for step in runner.trace))

    async def test_planner_failure_falls_back_to_search(self) -> None:
        async def planner(messages, specs):
            raise RuntimeError("planning down")

        async def execute(name, arguments):
            return {"ok": True, "name": name, "result": [fake_context()], "duration_ms": 1}

        async def answerer(contexts):
            yield "官方提供 12 个月质保 [1]"

        with (
            patch.object(agent.storage, "list_documents", return_value=[fake_document()]),
            patch.object(agent.storage, "all_chunks", return_value=[{"text": fake_context()["text"]}]),
            patch.object(agent.tools, "execute", side_effect=execute),
        ):
            runner = agent.AgentRunner(
                "质保多久？", mode="llm", planner=planner, answerer=answerer
            )
            await self.collect(runner)

        labels = [step["label"] for step in runner.trace]
        self.assertIn("规划降级", labels)
        self.assertIn("12 个月质保", runner.answer)

    async def test_invalid_citations_are_stripped(self) -> None:
        calls = {"planner": 0}

        async def planner(messages, specs):
            calls["planner"] += 1
            if calls["planner"] > 1:
                return {"content": "", "tool_calls": [], "usage": {}}
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": json.dumps({"query": "质保"}),
                        },
                    }
                ],
                "usage": {},
            }

        async def execute(name, arguments):
            return {"ok": True, "name": name, "result": [fake_context()], "duration_ms": 1}

        async def answerer(contexts):
            yield "官方提供 12 个月质保 [1][9]"

        with (
            patch.object(agent.storage, "list_documents", return_value=[fake_document()]),
            patch.object(agent.storage, "all_chunks", return_value=[{"text": fake_context()["text"]}]),
            patch.object(agent.tools, "execute", side_effect=execute),
        ):
            runner = agent.AgentRunner(
                "质保多久？", mode="llm", planner=planner, answerer=answerer
            )
            await self.collect(runner)

        self.assertIn("[1]", runner.answer)
        self.assertNotIn("[9]", runner.answer)
        citation_step = next(
            step for step in runner.trace if step["name"] == "citation_check"
        )
        self.assertEqual(citation_step["status"], "error")

    async def test_small_talk_skips_tools(self) -> None:
        async def planner(messages, specs):
            raise AssertionError("闲聊不应规划工具")

        async def answerer(contexts):
            yield "你好，我是知问。"

        runner = agent.AgentRunner(
            "你好", mode="llm", planner=planner, answerer=answerer
        )
        await self.collect(runner)

        self.assertEqual(runner.answer, "你好，我是知问。")
        self.assertEqual(runner.trace[0]["summary"], "闲聊问题，无需引用资料")

    async def test_demo_agent_returns_sources_and_answer(self) -> None:
        async def execute(name, arguments):
            return {"ok": True, "name": name, "result": [fake_context()], "duration_ms": 1}

        with (
            patch.object(agent.storage, "list_documents", return_value=[fake_document()]),
            patch.object(agent.storage, "all_chunks", return_value=[{"text": fake_context()["text"]}]),
            patch.object(agent.tools, "execute", side_effect=execute),
        ):
            runner = agent.AgentRunner("质保多久？", mode="demo")
            events = await self.collect(runner)

        self.assertEqual(len(runner.contexts), 1)
        self.assertIn("12 个月质保", runner.answer)
        self.assertEqual(
            [payload["sources"] for kind, payload in events if kind == "sources"][0],
            runner.contexts,
        )


if __name__ == "__main__":
    unittest.main()
