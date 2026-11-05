from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import agent
import config
import llm
import rag
import storage

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
EVAL_DIR = PROJECT_DIR / "eval"
TASKS_FILE = BASE_DIR / "eval_tasks.json"

REFUSAL_MARKERS = ("未找到", "没有找到", "无法回答", "不做推测")


def load_tasks() -> list[dict[str, Any]]:
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def context_text(contexts: list[dict[str, Any]]) -> str:
    return "\n".join(str(item.get("text") or "") for item in contexts)


def term_groups(text: str, terms: list[list[str]]) -> float:
    if not terms:
        return 1.0
    haystack = text.lower()
    hits = sum(
        1
        for group in terms
        if any(variant.lower() in haystack for variant in group)
    )
    return hits / len(terms)


def document_recall(contexts: list[dict[str, Any]], prefixes: list[str]) -> float | None:
    if not prefixes:
        return None
    names = [str(item.get("document_name") or "") for item in contexts]
    hits = sum(1 for prefix in prefixes if any(prefix in name for name in names))
    return hits / len(prefixes)


def citation_stats(answer: str, source_count: int) -> tuple[int, int, bool]:
    references = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    invalid = sum(1 for value in references if value < 1 or value > source_count)
    return len(references), invalid, bool(references)


def is_refusal(answer: str, contexts: list[dict[str, Any]]) -> bool:
    if contexts:
        return False
    return any(marker in answer for marker in REFUSAL_MARKERS)


def evaluate_task(
    task: dict[str, Any],
    contexts: list[dict[str, Any]],
    answer: str,
    *,
    steps: int,
    tool_steps: int,
    latency_ms: int,
) -> dict[str, Any]:
    answerable = bool(task.get("answerable"))
    terms = task.get("terms") or []
    sources_text = context_text(contexts)
    refusals = is_refusal(answer, contexts)
    references, invalid, cited = citation_stats(answer, len(contexts))
    coverage = term_groups(answer, terms) if answerable else None

    result: dict[str, Any] = {
        "id": task["id"],
        "type": task["type"],
        "question": task["question"],
        "answerable": answerable,
        "answer": answer,
        "source_count": len(contexts),
        "source_documents": sorted(
            {str(item.get("document_name") or "") for item in contexts}
        ),
        "steps": steps,
        "tool_steps": tool_steps,
        "latency_ms": latency_ms,
        "refused": refusals,
        "citations": references,
        "invalid_citations": invalid,
        "has_citation": cited,
    }
    if answerable:
        result["answer_term_coverage"] = round(coverage or 0.0, 4)
        result["full_answer"] = (coverage or 0.0) >= 0.999
        result["evidence_coverage"] = round(term_groups(sources_text, terms), 4)
        result["document_recall"] = document_recall(contexts, task.get("documents") or [])
    return result


async def run_agent(
    question: str, top_k: int
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], int, int]:
    started = time.perf_counter()
    runner = agent.AgentRunner(question, mode="demo", top_k=top_k)
    async for _event, _data in runner.run():
        pass
    latency = int((time.perf_counter() - started) * 1000)
    tool_steps = sum(1 for step in runner.trace if step.get("kind") == "tool")
    return runner.contexts, runner.answer, runner.trace, latency, tool_steps


def run_baseline(question: str, top_k: int) -> tuple[list[dict[str, Any]], str, int]:
    started = time.perf_counter()
    contexts = rag.search(question, top_k)
    answer = llm.demo_answer(question, contexts)
    answer, _ = agent.validate_citations(answer, len(contexts))
    latency = int((time.perf_counter() - started) * 1000)
    return contexts, answer, latency


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize(results: list[dict[str, Any]], label: str) -> dict[str, Any]:
    answerable = [item for item in results if item["answerable"]]
    unanswerable = [item for item in results if not item["answerable"]]
    citations = sum(item["citations"] for item in results)
    invalid = sum(item["invalid_citations"] for item in results)
    return {
        "label": label,
        "answerable_count": len(answerable),
        "unanswerable_count": len(unanswerable),
        "answer_term_coverage": mean([item["answer_term_coverage"] for item in answerable]),
        "full_answer_rate": mean([1.0 if item["full_answer"] else 0.0 for item in answerable]),
        "evidence_coverage": mean([item["evidence_coverage"] for item in answerable]),
        "document_recall": mean(
            [item["document_recall"] for item in answerable if item["document_recall"] is not None]
        ),
        "refusal_rate_unanswerable": mean(
            [1.0 if item["refused"] else 0.0 for item in unanswerable]
        ),
        "false_refusal_rate": mean(
            [1.0 if item["refused"] else 0.0 for item in answerable]
        ),
        "citation_invalid_rate": round(invalid / citations, 4) if citations else 0.0,
        "citation_coverage": mean(
            [1.0 if item["has_citation"] else 0.0 for item in answerable]
        ),
        "avg_steps": mean([item["steps"] for item in results]),
        "avg_tool_steps": mean([item["tool_steps"] for item in results]),
        "avg_latency_ms": round(mean([item["latency_ms"] for item in results]), 1),
    }


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


def classify_failures(task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for task in task_results:
        if task["answerable"]:
            if not task["full_answer"]:
                failures.append(task)
        elif not task["refused"]:
            failures.append(task)
    return failures


def build_report(
    tasks: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    agent_results: list[dict[str, Any]],
    baseline_summary: dict[str, Any],
    agent_summary: dict[str, Any],
) -> str:
    stats = storage.stats()
    documents = sorted({name for task in tasks for name in (task.get("documents") or [])})
    failure_rows = []
    for task in classify_failures(agent_results):
        preview = re.sub(r"\s+", " ", task["answer"])[:110]
        failure_rows.append(
            f"| {task['id']} | {task['question'][:28]} | {task['source_count']} | {preview} |"
        )
    failure_table = "\n".join(failure_rows) if failure_rows else "| — | 全部通过 | — | — |"

    def row(metric: str, key: str, formatter=pct) -> str:
        return f"| {metric} | {formatter(baseline_summary[key])} | {formatter(agent_summary[key])} |"

    lines = [
        "# 知问 Agent 评测报告",
        "",
        f"- 运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 任务数：{len(tasks)}（单跳 12 · 多跳/总结 8 · 无答案 10）",
        "- 运行模式：demo（规则规划 + 抽取式回答，零 API 调用，可复现）",
        f"- 知识库：{stats['documents']} 篇文档 · {stats['chunks']} 个分块 · {stats['characters']} 字",
        f"- 评测文档：{'、'.join(documents)}",
        f"- 配置：TOP_K={config.TOP_K} · AGENT_MAX_STEPS={config.AGENT_MAX_STEPS} · "
        f"证据阈值={agent.EVIDENCE_THRESHOLD:.0%}",
        "",
        "## 总览",
        "",
        "| 指标 | 单次 RAG | Agent 循环 |",
        "| --- | ---: | ---: |",
        row("回答词项覆盖率（可答）", "answer_term_coverage"),
        row("完整命中率（可答）", "full_answer_rate"),
        row("证据命中率（可答）", "evidence_coverage"),
        row("期望文档召回（可答）", "document_recall"),
        row("无答案拒答率", "refusal_rate_unanswerable"),
        row("误拒答率（可答）", "false_refusal_rate"),
        row("引用覆盖率（可答）", "citation_coverage"),
        row("引用越界率", "citation_invalid_rate"),
        f"| 平均步骤 | {baseline_summary['avg_steps']:.2f} | {agent_summary['avg_steps']:.2f} |",
        f"| 平均工具调用 | {baseline_summary['avg_tool_steps']:.2f} | {agent_summary['avg_tool_steps']:.2f} |",
        f"| 平均延迟 | {baseline_summary['avg_latency_ms']:.0f} ms | {agent_summary['avg_latency_ms']:.0f} ms |",
        "",
        "## 分类结果",
        "",
        "| 类型 | 任务 | 单次 RAG 完整命中 | Agent 完整命中 | 单次 RAG 拒答 | Agent 拒答 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for type_name, label in (
        ("single", "单跳事实"),
        ("multi", "多跳/总结"),
        ("unanswerable", "无答案"),
    ):
        base_group = [item for item in baseline if item["type"] == type_name]
        agent_group = [item for item in agent_results if item["type"] == type_name]
        if type_name == "unanswerable":
            base_hit = base_refuse = mean([1.0 if item["refused"] else 0.0 for item in base_group])
            agent_hit = agent_refuse = mean(
                [1.0 if item["refused"] else 0.0 for item in agent_group]
            )
        else:
            base_hit = mean([1.0 if item["full_answer"] else 0.0 for item in base_group])
            agent_hit = mean([1.0 if item["full_answer"] else 0.0 for item in agent_group])
            base_refuse = mean([1.0 if item["refused"] else 0.0 for item in base_group])
            agent_refuse = mean([1.0 if item["refused"] else 0.0 for item in agent_group])
        lines.append(
            f"| {label} | {len(agent_group)} | {pct(base_hit)} | {pct(agent_hit)} | "
            f"{pct(base_refuse)} | {pct(agent_refuse)} |"
        )

    lines += [
        "",
        "## Agent 未通过任务",
        "",
        "| ID | 问题 | 来源数 | 回答摘录 |",
        "| --- | --- | ---: | --- |",
        failure_table,
        "",
        "## 结论与边界",
        "",
        "- Agent 的主要收益来自检索失败后的工具降级（读取文档分块）和无依据拒答；"
        "在 demo 模式下，回答由抽取式规则生成，词项覆盖率并不代表大模型的真实回答质量。",
        "- 单次 RAG 只执行一次向量检索，没有证据门槛；遇到知识库没有的信息时，"
        "仍可能把不相关片段拼成回答，因此无答案拒答率明显低于 Agent。",
        "- 本评测固定使用规则规划，结果可复现、零 API 成本；它验证的是编排、降级、"
        "引用校验与拒答逻辑，而不是 DeepSeek 的生成质量。",
        "- demo 流式输出包含 10ms/片的人为节流，延迟主要反映交互节奏，不作为性能基准。",
        "- 若接入真实模型，应另行记录 token 成本、规划耗时与工具调用准确率，再与单次 RAG 对比。",
        "",
    ]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="对比单次 RAG 与 Agent 循环")
    parser.add_argument("--top-k", type=int, default=config.TOP_K)
    parser.add_argument("--json", action="store_true", help="只输出 JSON 汇总")
    args = parser.parse_args()

    tasks = load_tasks()
    if len(tasks) != 30:
        print(f"评测任务应为 30 条，当前 {len(tasks)} 条", file=sys.stderr)
        return 1
    if not storage.list_documents():
        print(
            "知识库为空。请先上传 samples 下的两份文档，再运行评测。",
            file=sys.stderr,
        )
        return 1

    baseline_results: list[dict[str, Any]] = []
    agent_results: list[dict[str, Any]] = []

    for task in tasks:
        contexts, answer, latency = run_baseline(task["question"], args.top_k)
        baseline_results.append(
            evaluate_task(
                task,
                contexts,
                answer,
                steps=1,
                tool_steps=1,
                latency_ms=latency,
            )
        )

        contexts, answer, trace, latency, tool_steps = await run_agent(
            task["question"], args.top_k
        )
        agent_results.append(
            evaluate_task(
                task,
                contexts,
                answer,
                steps=len(trace),
                tool_steps=tool_steps,
                latency_ms=latency,
            )
        )

    baseline_summary = summarize(baseline_results, "single-rag")
    agent_summary = summarize(agent_results, "agent-loop")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "demo",
        "config": {
            "top_k": args.top_k,
            "agent_max_steps": config.AGENT_MAX_STEPS,
            "evidence_threshold": agent.EVIDENCE_THRESHOLD,
            "documents": storage.stats(),
        },
        "summary": {"single_rag": baseline_summary, "agent_loop": agent_summary},
        "tasks": [
            {"baseline": baseline, "agent": agent_item}
            for baseline, agent_item in zip(baseline_results, agent_results)
        ],
    }
    (EVAL_DIR / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EVAL_DIR / "report.md").write_text(
        build_report(
            tasks, baseline_results, agent_results, baseline_summary, agent_summary
        ),
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    else:
        print(f"完成 {len(tasks)} 条任务，报告：{EVAL_DIR / 'report.md'}")
        for name, summary in (("单次 RAG", baseline_summary), ("Agent", agent_summary)):
            print(
                f"{name}: 完整命中 {pct(summary['full_answer_rate'])} · "
                f"无答案拒答 {pct(summary['refusal_rate_unanswerable'])} · "
                f"平均步骤 {summary['avg_steps']:.2f} · "
                f"引用越界 {pct(summary['citation_invalid_rate'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
