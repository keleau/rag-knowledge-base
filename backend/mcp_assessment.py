"""把「项目定向测评」封装成 MCP 工具。

设计目标：在 Claude Desktop / Claude Code 里，模型可以自己串联完整流程：

    create_assessment → register_resume → select_project → add_project_document
    → upload_code（可选）→ prepare_assessment
    → get_practice_questions / answer_practice
    → start_exam → get_exam（续答）→ submit_exam
    → start_interview → answer_interview（get_interview 查看进度）
    → generate_report → get_report →（未达标）start_review → submit_review
    → get_assessment_status（任何阶段断点续做）

所有工具都是薄封装，底层复用 assessment_tasks / interview / assessment_storage，
保证 Web API 与 MCP 两条入口行为一致。

约定：
- 工具返回结构化 dict，不返回 Markdown，让客户端模型自己组织语言。
- 会调用 DeepSeek 的工具在描述里写明，避免用户意外产生费用。
- 不暴露删除类操作，避免模型误删用户数据。
"""

from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import assessment as state
import assessment_storage as store
import assessment_tasks as tasks
import code_parser
import interview
import pii
import rag
import storage

# 工具行为标注：让客户端知道哪些只读、哪些幂等、哪些会访问外部模型服务
READ_ONLY_LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
LOCAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
LOCAL_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
CALLS_MODEL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


def _normalize_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("﻿", "")
    value = re.sub(r"[ \t　]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _transition(session: dict[str, Any], target: state.Stage, **kwargs: Any) -> dict[str, Any]:
    return state.transition(session["id"], int(session["version"]), target, **kwargs)


def register(mcp: FastMCP) -> None:
    """把测评相关的 MCP 工具注册到传入的 FastMCP 实例上。"""

    @mcp.tool(annotations=LOCAL_WRITE)
    async def create_assessment(title: str = "项目答辩练习") -> dict[str, Any]:
        """新建一次评估会话，返回 assessment_id，后续所有工具都需要它。

        不会调用模型，不会产生费用。数据存在本地 SQLite（backend/data/assessment.db）。
        """
        session = store.create_session(title)
        return {
            "assessment_id": session["id"],
            "stage": session["stage"],
            "next_action": "register_resume",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def register_resume(assessment_id: str, resume_text: str, file_name: str = "resume.md") -> dict[str, Any]:
        """登记简历正文，并自动提取项目列表。

        - resume_text：简历纯文本（由调用方把 pdf/docx 转成文本）
        - 写入知识库前会遮罩手机号、邮箱、身份证
        - 会调用一次 DeepSeek 提取项目
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        text = _normalize_text(resume_text)
        chunks = rag.chunk_text(text)
        if not chunks:
            return {"error": "简历没有可用文本"}
        document = storage.add_document(
            file_name, f"{assessment_id}-resume.md", len(text), chunks, len(text), origin="assessment"
        )
        store.update_session_fields(assessment_id, resume_document_id=document["id"])
        rag.invalidate_index()
        try:
            projects = await tasks.extract_projects(assessment_id, text)
        except tasks.TaskError as exc:
            return {"error": str(exc), "document_id": document["id"]}
        return {
            "document_id": document["id"],
            "projects": [
                {
                    "project_id": item["id"],
                    "name": item["name"],
                    "summary": item.get("summary"),
                    "source_quote": item.get("source_quote"),
                }
                for item in projects
            ],
            "next_action": "select_project",
        }

    @mcp.tool(annotations=LOCAL_IDEMPOTENT)
    async def select_project(assessment_id: str, project_id: str) -> dict[str, Any]:
        """选定要练习的项目。之后才能添加项目文档。"""
        project = store.get_project(project_id)
        if project is None or project["session_id"] != assessment_id:
            return {"error": "项目不存在或不属于这个评估"}
        store.select_project(assessment_id, project_id)
        return {"selected": project["name"], "next_action": "add_project_document"}

    @mcp.tool(annotations=LOCAL_WRITE)
    async def add_project_document(assessment_id: str, document_text: str, file_name: str = "project.md") -> dict[str, Any]:
        """登记项目介绍文档（背景、技术栈、难点、取舍）。

        至少需要切出 5 个分块；内容越具体，出的题越像“照着你的项目问”。不会调用模型。
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        if not session.get("project_id"):
            return {"error": "请先调用 select_project"}
        text = _normalize_text(document_text)
        chunks = rag.chunk_text(text)
        if len(chunks) < 5:
            return {"error": f"项目文档太短（{len(chunks)} 个分块，至少 5 个），请补充更多背景、技术栈、难点和取舍"}
        document = storage.add_document(
            file_name, f"{assessment_id}-project.md", len(text), chunks, len(text), origin="assessment"
        )
        store.update_session_fields(assessment_id, project_document_id=document["id"])
        rag.invalidate_index()
        return {
            "document_id": document["id"],
            "chunk_count": document["chunk_count"],
            "next_action": "upload_code（可选）或 prepare_assessment",
        }

    @mcp.tool(annotations=LOCAL_IDEMPOTENT)
    async def upload_code(assessment_id: str, file_name: str, content: str) -> dict[str, Any]:
        """上传一个页面代码文件（.vue / .ts / .js，≤200 KB），用于生成“这个功能怎么实现”的代码题。

        只解析不执行；会扫描 sk-、密码、私钥等敏感串，命中则拒绝。
        返回识别到的符号（函数、状态、API 调用、行号），并替换该评估之前的代码。不会调用模型。
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        if not session.get("project_id"):
            return {"error": "请先调用 select_project"}
        if not any(file_name.lower().endswith(ext) for ext in (".vue", ".ts", ".js")):
            return {"error": "只支持 .vue / .ts / .js 单文件"}
        if len(content.encode("utf-8")) > 200 * 1024:
            return {"error": "代码文件不能超过 200 KB"}
        hits = pii.scan_secrets(content)
        if hits:
            return {"error": f"代码里检测到敏感信息（{', '.join(hits)}），请删除后再上传"}
        try:
            parsed = code_parser.parse_code(file_name, content)
        except code_parser.CodeParseError as exc:
            return {"error": str(exc)}
        store.save_code(assessment_id, file_name, parsed["language"], content, parsed)
        store.save_entities(
            assessment_id,
            [
                {
                    "name": item["name"],
                    "kind": item["kind"] if item["kind"] in {"component", "api", "function", "metric", "term"} else "term",
                }
                for item in parsed["symbols"][:30]
            ],
            source_type="code",
        )
        return {
            "file_name": file_name,
            "line_count": parsed["line_count"],
            "symbol_count": len(parsed["symbols"]),
            "symbols": parsed["symbols"][:40],
            "next_action": "prepare_assessment",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def prepare_assessment(assessment_id: str) -> dict[str, Any]:
        """生成知识标签、能力目标（L1–L4）和 ≥20 道练习题（含代码题）。

        会调用多次 DeepSeek，耗时约 30–90 秒，产生少量费用。重复调用会覆盖旧的标签与练习。
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        try:
            result = await tasks.prepare(assessment_id)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        return {
            "tags": [{"tag_id": tag["id"], "name": tag["name"], "description": tag["description"]} for tag in result["tags"]],
            "capabilities": [
                {
                    "capability_id": item["id"],
                    "tag": item["tag"],
                    "target_level": item["target_level"],
                    "acceptance": item["acceptance"],
                }
                for item in result["capabilities"]
            ],
            "practice_count": len(result["practice"]),
            "next_action": "get_practice_questions",
        }

    @mcp.tool(annotations=LOCAL_IDEMPOTENT)
    async def set_capability_target(assessment_id: str, tag_name: str, target_level: str) -> dict[str, Any]:
        """调整某个能力的目标等级：L1 知道 / L2 解释 / L3 迁移 / L4 讲清。"""
        level = target_level.upper()
        if level not in {"L1", "L2", "L3", "L4"}:
            return {"error": "target_level 必须是 L1–L4"}
        capability = next((item for item in store.list_capabilities(assessment_id) if item["tag"] == tag_name), None)
        if capability is None:
            return {"error": f"没有找到能力：{tag_name}"}
        updated = store.update_capability_target(capability["id"], level)
        return {"tag": tag_name, "target_level": level, "saved": updated is not None}

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_practice_questions(assessment_id: str, limit: int = 20) -> dict[str, Any]:
        """获取练习题，包含题干、难度、证据和代码符号（不含参考答案，避免直接抄）。"""
        items = [item for item in store.list_practice_items(assessment_id, 0) if item["kind"] != "card"]
        questions = items[: max(1, int(limit))]
        return {
            "count": len(questions),
            "total": len(items),
            "questions": [
                {
                    "practice_id": item["id"],
                    "tag": item["tag"],
                    "kind": item["kind"],
                    "code_mode": item["code_mode"],
                    "difficulty": item["difficulty"],
                    "prompt": item["prompt"],
                    "source_quote": item["source_quote"],
                    "source_file": item["source_file"],
                    "line_range": [item["line_start"], item["line_end"]] if item["line_start"] else None,
                    "symbols": item["symbols"],
                    "answered": bool(item["user_answer"]),
                }
                for item in questions
            ],
        }

    @mcp.tool(annotations=LOCAL_IDEMPOTENT)
    async def answer_practice(assessment_id: str, practice_id: str, answer: str, self_score: int = 70) -> dict[str, Any]:
        """提交一道练习题的作答和自评（0–100）。自评偏低的标签会被优先考察。重复提交会覆盖。"""
        item = store.get_practice_item(practice_id)
        if item is None or item["session_id"] != assessment_id:
            return {"error": "练习题不存在"}
        store.save_practice_answer(practice_id, answer, self_score)
        return {"practice_id": practice_id, "self_score": max(0, min(int(self_score), 100))}

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_exam(assessment_id: str) -> dict[str, Any]:
        """重新获取当前试卷（不含参考答案），用于在同一轮对话里续答。

        如果试卷还没生成，返回提示；如果已经生成过，返回同样的题目，不会重新出题、不产生费用。
        """
        questions = store.public_exam_questions(assessment_id)
        if not questions:
            return {"error": "还没有生成试卷，请先调用 start_exam"}
        return {
            "questions": [
                {
                    "question_id": item["id"],
                    "tag": item["tag"],
                    "type": item["type"],
                    "code_mode": item["code_mode"],
                    "prompt": item["prompt"],
                    "options": item["options"],
                    "symbols": item["symbols"],
                }
                for item in questions
            ]
        }

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_interview(assessment_id: str) -> dict[str, Any]:
        """查看面试进行到哪一轮、当前待回答的问题和历史评分（不含模型调用）。"""
        turns = store.list_interview_turns(assessment_id)
        pending = next((item for item in turns if item["status"] == "asking"), None)
        return {
            "turns": [
                {
                    "turn_id": item["id"],
                    "round": item["round_index"],
                    "weak_tag": item.get("tag"),
                    "question": item["question"],
                    "answer": item.get("answer"),
                    "score": item.get("score"),
                    "status": item["status"],
                    "is_follow_up": bool(item.get("follow_up_of")),
                }
                for item in turns
            ],
            "pending_question": None
            if pending is None
            else {
                "turn_id": pending["id"],
                "round": pending["round_index"],
                "weak_tag": pending.get("tag"),
                "question": pending["question"],
            },
            "next_action": "answer_interview" if pending else "generate_report",
        }

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_report(assessment_id: str) -> dict[str, Any]:
        """读取已经生成的报告（不调用模型）；未生成时提示先调用 generate_report。"""
        report = store.get_report(assessment_id)
        if report is None:
            return {"error": "还没有生成报告，请先调用 generate_report"}
        return {
            "passed": report["passed"],
            "level": report["level"],
            "summary": report["summary"],
            "capabilities": report["capabilities"],
            "weaknesses": report["weaknesses"],
            "actions": report["actions"],
            "next": report["next"],
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def start_exam(assessment_id: str) -> dict[str, Any]:
        """生成考试试卷（默认 10 题，含代码题），并把阶段推进到 exam。

        后端会强制校验：每题必须有证据、必须命中项目实体、且与练习题不重复。
        会调用 DeepSeek 2–6 次（含补位）。
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        if session["stage"] == "setup":
            try:
                session = _transition(session, state.Stage.LEARNING)
            except state.AssessmentError as exc:
                return {"error": exc.message}
        try:
            questions = await tasks.generate_exam(assessment_id)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        if session["stage"] == "learning":
            try:
                _transition(session, state.Stage.EXAM)
            except state.AssessmentError as exc:
                return {"error": f"试卷已生成，但阶段推进失败：{exc.message}"}
        return {
            "question_count": len(questions),
            "questions": [
                {
                    "question_id": item["id"],
                    "tag": item["tag"],
                    "type": item["type"],
                    "code_mode": item["code_mode"],
                    "prompt": item["prompt"],
                    "options": item["options"],
                    "symbols": item["symbols"],
                    "source_quote": item["source_quote"],
                    "line_range": [item["line_start"], item["line_end"]] if item["line_start"] else None,
                }
                for item in store.public_exam_questions(assessment_id)
            ],
            "next_action": "submit_exam",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def submit_exam(assessment_id: str, answers: list[dict[str, str]], idempotency_key: str = "") -> dict[str, Any]:
        """提交考试答案并自动阅卷。

        answers 格式：[{"question_id": "eq_xxx", "content": "A"}]（选择题填 A–D，简答填文本）
        同一 idempotency_key 重复提交不会重复判分。会调用 DeepSeek 给主观题和实现题阅卷。
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        questions = store.list_exam_questions(assessment_id)
        if not questions:
            return {"error": "还没有生成试卷，请先调用 start_exam"}
        answer_map = {str(item.get("question_id")): str(item.get("content") or "") for item in answers}
        missing = [item["id"] for item in questions if not answer_map.get(item["id"], "").strip()]
        if missing:
            return {"error": f"还有 {len(missing)} 道题没有作答", "missing_question_ids": missing}
        key = idempotency_key or f"mcp_{assessment_id}_{len(questions)}"
        if not store.create_submission(assessment_id, key, "mcp"):
            latest = store.get_session(assessment_id) or session
            return {"duplicated": True, "stage": latest["stage"]}
        for item in questions:
            store.save_exam_answer(item["id"], answer_map[item["id"]], None, 10.0)
        if session["stage"] == "exam":
            try:
                _transition(session, state.Stage.GRADING, patch={"status": "running"})
            except state.AssessmentError as exc:
                return {"error": f"答案已保存，但阶段推进失败：{exc.message}"}
        try:
            graded = await tasks.grade_exam(assessment_id)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        graded_answers = store.list_exam_answers(assessment_id)
        total = sum(item["score"] or 0 for item in graded_answers)
        return {
            "graded": graded["graded"],
            "score": round(total, 1),
            "max_score": len(graded_answers) * 10,
            "needs_review_question_ids": [item["question_id"] for item in graded_answers if item["needs_review"]],
            "weak_points": [{"tag": item["tag"], "reason": item["reason"]} for item in graded["weak_points"]],
            "next_action": "start_interview",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def start_interview(assessment_id: str) -> dict[str, Any]:
        """根据薄弱点开始模拟面试，返回第一问。会调用一次 DeepSeek。已开始过则返回当前这一问。"""
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        if session["stage"] == "grading":
            try:
                _transition(session, state.Stage.INTERVIEW)
            except state.AssessmentError as exc:
                return {"error": exc.message}
        try:
            result = await interview.start_interview(assessment_id)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        turn = result["turn"]
        return {
            "turn_id": turn["id"],
            "round": turn["round_index"],
            "weak_tag": turn.get("tag"),
            "question": turn["question"],
            "rubric": turn.get("rubric"),
            "next_action": "answer_interview",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def answer_interview(assessment_id: str, answer: str) -> dict[str, Any]:
        """回答当前面试问题，返回评分、命中的得分点和下一问（或结束）。会调用一次 DeepSeek。"""
        try:
            result = await interview.answer_interview(assessment_id, answer)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        latest = result["turns"][-1] if result["turns"] else {}
        return {
            "grade": result["grade"],
            "finished": result["finished"],
            "current_round": result["current_round"],
            "next_question": None
            if latest.get("status") != "asking"
            else {
                "turn_id": latest["id"],
                "round": latest["round_index"],
                "weak_tag": latest.get("tag"),
                "question": latest["question"],
            },
            "next_action": "generate_report" if result["finished"] else "answer_interview",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def generate_report(assessment_id: str) -> dict[str, Any]:
        """生成复盘报告与通关判定，并推进到 report 阶段。会调用一次 DeepSeek 写总结。"""
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        report = tasks.build_report(assessment_id)
        report = await tasks.generate_report_narrative(assessment_id, report)
        if session["stage"] == "interview":
            try:
                _transition(session, state.Stage.REPORT)
            except state.AssessmentError:
                pass
        return {
            "passed": report["passed"],
            "level": report["level"],
            "summary": report["summary"],
            "capabilities": report["capabilities"],
            "actions": report["actions"],
            "next": report["next"],
            "next_action": "start_review" if not report["passed"] else "done",
        }

    @mcp.tool(annotations=CALLS_MODEL)
    async def start_review(assessment_id: str) -> dict[str, Any]:
        """开始复练：只针对未达标能力再出 ≥10 题。会调用一次 DeepSeek。"""
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        if session["stage"] != "report":
            return {"error": "只有报告阶段可以开始复练"}
        try:
            result = await tasks.generate_review(assessment_id)
            _transition(session, state.Stage.PRACTICE)
        except tasks.TaskError as exc:
            return {"error": str(exc)}
        except state.AssessmentError as exc:
            return {"error": exc.message}
        return {"cycle": result["cycle"], "count": result["count"], "next_action": "submit_review"}

    @mcp.tool(annotations=CALLS_MODEL)
    async def submit_review(assessment_id: str, answers: list[dict[str, str]]) -> dict[str, Any]:
        """提交复练作答，自动评分并重新判定是否达标。会调用一次 DeepSeek 评分。

        answers 格式：[{"question_id": "pi_xxx", "content": "回答"}]
        """
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        cycle = int(session.get("practice_cycle") or 0)
        items = [item for item in store.list_practice_items(assessment_id, cycle) if item["kind"] != "card"]
        answer_map = {str(item.get("question_id")): str(item.get("content") or "") for item in answers}
        to_grade = [
            {"id": item["id"], "prompt": item["prompt"], "answer": item.get("answer"), "content": answer_map[item["id"]]}
            for item in items
            if answer_map.get(item["id"])
        ]
        if not to_grade:
            return {"error": "至少作答 1 道复练题", "practice_ids": [item["id"] for item in items]}
        scores = await tasks.grade_review_answers(assessment_id, to_grade)
        for item in to_grade:
            store.save_practice_answer(item["id"], item["content"], scores.get(item["id"], 0))
        evaluation = tasks.compute_evaluation(assessment_id)
        store.apply_capability_results(assessment_id, evaluation)
        previous = store.get_report(assessment_id) or {}
        report = tasks.build_report(assessment_id)
        report["summary"] = previous.get("summary") or ""
        report["actions"] = previous.get("actions") or report["actions"]
        store.save_report(assessment_id, report)
        if session["stage"] == "practice":
            try:
                _transition(session, state.Stage.REPORT)
            except state.AssessmentError:
                pass
        return {
            "answered": len(to_grade),
            "passed": evaluation["passed"],
            "level": evaluation["level"],
            "capabilities": evaluation["criteria"],
            "next_action": "done" if evaluation["passed"] else "start_review",
        }

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_assessment_status(assessment_id: str) -> dict[str, Any]:
        """查看一次评估的当前阶段、能力等级、最近一次判定和模型调用量，用于断点续做。"""
        session = store.get_session(assessment_id)
        if session is None:
            return {"error": "评估会话不存在"}
        report = store.get_report(assessment_id)
        return {
            "title": session["title"],
            "stage": session["stage"],
            "version": session["version"],
            "practice_cycle": session["practice_cycle"],
            "passed": bool(session.get("passed")),
            "capabilities": [
                {
                    "tag": item["tag"],
                    "target": item["target_level"],
                    "current": item["current_level"],
                    "met": bool(item["met"]),
                }
                for item in store.list_capabilities(assessment_id)
            ],
            "has_code": bool(store.get_code(assessment_id)),
            "last_report": None
            if report is None
            else {"passed": report["passed"], "level": report["level"], "next": report["next"]},
            "llm_cost": store.session_cost(assessment_id),
        }


__all__ = ["register", "register_resources"]


# --------------------------------------------------------------------------- #
# MCP Resources 与 Prompts：让客户端可以直接读取固定的参考材料 / 调用预设流程
# --------------------------------------------------------------------------- #
CAPABILITY_LEVELS = """# 能力等级定义

| 等级 | 含义 | 判定依据 |
| --- | --- | --- |
| L1 知道 | 能说出概念和项目里的用词 | 考试相关题 ≥ 50% |
| L2 解释 | 能解释“为什么这么做”，有证据、有取舍 | 考试 ≥ 70%，主观题至少命中 1 个得分点 |
| L3 迁移 | 能把能力用到新场景/追问下 | 考试 ≥ 70% 且面试相关轮次 ≥ 70% |
| L4 讲清 | 能像面试官一样讲清边界、失败、如果重做 | 考试 ≥ 85%，面试 ≥ 85%，且不再是薄弱点 |

通关条件（由后端代码计算，模型不得修改）：
- 所有目标为 L3 的能力都达成；
- 6 个能力中至少 5 个达到 L2；
- 目标为 L3 的能力必须在面试中被覆盖过，未覆盖一律算未达标。
"""

WORKFLOW_GUIDE = """# 项目定向测评：MCP 调用顺序

1. `create_assessment` → 拿到 assessment_id
2. `register_resume(resume_text)` → 提取项目
3. `select_project(project_id)`
4. `add_project_document(document_text)`（≥5 个分块）
5. `upload_code(file_name, content)`（可选，只支持单个 .vue/.ts/.js）
6. `prepare_assessment` → 标签 + 能力目标 + ≥20 道练习（调用模型，花钱）
7. `get_practice_questions` / `answer_practice`
8. `start_exam` → `get_exam`（续答）→ `submit_exam`（自动阅卷）
9. `start_interview` → `answer_interview` × 最多 3 轮，`get_interview` 查看进度
10. `generate_report` → `get_report` 查看 passed 与每项能力差距
11. 未达标：`start_review` → `submit_review`（重新判定）
12. 任何阶段都可以用 `get_assessment_status` 断点续做

注意：
- 第 2、6、8 中的 start_exam/submit_exam、9、10、11 会调用 DeepSeek 并产生费用。
- 题目由后端校验：必须有证据、必须命中项目实体、且与练习/之前阶段不重复；不合格的题会被丢弃而不是凑数。
- 所有工具返回值都是结构化 JSON，请据此向用户解释，不要编造分数。
- 不要在用户没回答之前替他作答；选择题让用户自己选。
"""


def register_resources(mcp: FastMCP) -> None:
    """注册只读资源与预设提示模板。"""

    @mcp.resource("zhiwen://guide/capability-levels", name="能力等级定义", mime_type="text/markdown")
    def capability_levels() -> str:
        """解释 L1–L4 各等级的含义与通关条件。"""
        return CAPABILITY_LEVELS

    @mcp.resource("zhiwen://guide/workflow", name="测评流程说明", mime_type="text/markdown")
    def workflow() -> str:
        """说明 MCP 工具的调用顺序，以及哪些步骤会调用模型。"""
        return WORKFLOW_GUIDE

    @mcp.prompt(name="project-interview-practice", description="用 MCP 工具为当前项目做一轮答辩训练")
    def project_interview_practice(project_name: str, focus: str = "整体") -> str:
        """生成一段可以交给模型执行的提示词。"""
        return (
            f"请使用知问的测评工具，为项目「{project_name}」做一次答辩训练，重点关注：{focus}。\n"
            "步骤：\n"
            "1. 先用 get_assessment_status 查看进度；没有现有评估再调用 create_assessment。\n"
            "2. 还没有简历/项目文档时，请让我提供，再调用 register_resume 和 add_project_document。\n"
            "3. 调用 prepare_assessment，然后用 get_practice_questions 逐道问我，我回答后调用 answer_practice 记录自评。\n"
            "4. 调用 start_exam 出试卷，逐题问我，全部答完后用 submit_exam 提交。\n"
            "5. 调用 start_interview，一次只问一个问题，每轮用 answer_interview 记录；超时用 get_interview 查进度。\n"
            "6. 调用 generate_report，用中文解释每项能力的差距；未达标时询问我是否要 start_review。\n"
            "要求：每道题单独问我，等我回答再继续；选择题让我自己选；不要编造分数，所有分数以工具返回为准。"
        )
