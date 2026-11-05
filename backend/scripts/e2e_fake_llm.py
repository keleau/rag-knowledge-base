"""端到端骨架验证（mock 掉模型调用，不花钱、不需要 Key）。

覆盖：会话 → 项目提取 → 标签/能力目标 → 代码上传解析 → 练习 → 试卷 →
提交 → 阅卷 → 面试 → 报告 → 复练，验证数据库、状态机、闸门和判定能串起来。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/e2e_fake_llm.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import assessment as state  # noqa: E402
import assessment_app  # noqa: E402
import assessment_storage as store  # noqa: E402
import config  # noqa: E402
import interview  # noqa: E402
import llm  # noqa: E402
import rag  # noqa: E402
import storage  # noqa: E402
import parsers  # noqa: E402
from assessment_app import CodeIn  # noqa: E402

CALLS: list[str] = []

RESUME = """# 张同学

## 项目经历
- 知问 · 检索 Agent 知识库问答（2026）
  负责知问项目的前后端与 Agent 编排，实现规划-工具-观察循环和 30 条评测。
"""

PROJECT_DOC = """# 知问项目技术说明

## 背景
知问是一个可本地运行的检索 Agent 知识库问答，用户上传 txt、md、docx、pdf 文档后，Agent 自己决定检索、改写查询还是读取整篇文档。

## 技术栈
后端使用 FastAPI 与 Uvicorn，检索使用 jieba 分词与 TF-IDF 余弦相似度，前端使用 Vue 3、TypeScript 和 Vite。存储使用本地 JSON 文件与原子写。

## Agent 循环
Agent 循环最多 4 步，每一步调用 search_knowledge、list_documents 或 get_document_chunks 三个工具之一。达到 4 步上限后强制停止，并使用已收集的资料作答。

## 证据门槛
证据门槛为 75%，低于阈值时不调用模型，直接拒答，避免用不相干片段拼答案。无依据时回答固定文案，不编造。

## 前端组件
streamTrace 记录每一步的工具调用轨迹，DocumentDrawer 展示文档分块，DocumentPanel 负责上传与删除文档。

## 评测
项目附带 30 条评测任务，对比单次 RAG 与 Agent 循环的无答案拒答率与引用越界率。
"""

VUE_SAMPLE = """<script setup lang="ts">
import { ref } from 'vue'

const drawerDoc = ref(null)

async function openDocument(id) {
  drawerDoc.value = await api.getDocument(id)
}
</script>

<template>
  <button @click="openDocument(docId)">打开</button>
</template>
"""

PRACTICE_ITEMS = [
    {
        "tag": "状态管理", "kind": "question", "difficulty": "easy",
        "prompt": "知问前端的 streamTrace 用来做什么？", "answer": "记录工具轨迹", "explanation": "状态",
        "source": {"chunk_id": "x", "quote": "streamTrace"},
    },
    {
        "tag": "异常与边界", "kind": "question", "difficulty": "medium",
        "prompt": "证据门槛 75% 低于阈值时会怎样？", "answer": "直接拒答", "explanation": "边界",
        "source": {"chunk_id": "x", "quote": "拒答"},
    },
    {
        "tag": "组件设计", "kind": "question", "difficulty": "easy",
        "prompt": "DocumentDrawer 为什么单独成组件？", "answer": "展示文档分块", "explanation": "拆分",
        "source": {"chunk_id": "x", "quote": "DocumentDrawer"},
    },
    {
        "tag": "接口与数据流", "kind": "question", "difficulty": "medium",
        "prompt": "Agent 循环最多 4 步，达到上限后怎么处理？", "answer": "用已有资料作答", "explanation": "边界",
        "source": {"chunk_id": "x", "quote": "最多 4 步"},
    },
    {
        "tag": "状态管理", "kind": "code_question", "code_mode": "implement", "difficulty": "hard",
        "prompt": "openDocument 是怎么把数据写进 drawerDoc 的？", "answer": "await 后赋值",
        "explanation": "数据流",
        "rubric": [{"kind": "symbol", "point": "提到 drawerDoc", "weight": 2, "symbol": "drawerDoc"}],
        "source": {"file": "App.vue", "line_start": 4, "line_end": 8, "quote": "drawerDoc.value", "symbols": ["drawerDoc", "openDocument"]},
    },
]

REVIEW_ITEMS = [
    {
        "tag": "状态管理", "kind": "question", "difficulty": "hard",
        "prompt": "streamTrace 在流式回答过程中是怎么逐步更新的？", "answer": "每收到一个 step 就追加",
        "explanation": "复练", "source": {"chunk_id": "x", "quote": "streamTrace"},
    },
    {
        "tag": "异常与边界", "kind": "question", "difficulty": "hard",
        "prompt": "如果知识库为空，知问的证据门槛会怎么触发？", "answer": "直接拒答",
        "explanation": "复练", "source": {"chunk_id": "x", "quote": "拒答"},
    },
]

EXAM_QUESTIONS = [
    {
        "type": "single_choice", "tag": "组件设计",
        "prompt": "知问前端里负责上传与删除文档的是哪个组件？",
        "options": ["A DocumentPanel", "B DocumentDrawer", "C Sidebar", "D ChatView"], "answer": "A",
        "reference_answer": "A", "rubric": [], "source": {"chunk_id": "x", "quote": "DocumentPanel"},
    },
    {
        "type": "short_answer", "tag": "异常与边界",
        "prompt": "如果用户问题里包含知识库完全没有的实体，知问会走哪条路径？",
        "reference_answer": "直接拒答", "rubric": [{"kind": "behavior", "point": "说明拒答路径", "weight": 10}],
        "source": {"chunk_id": "x", "quote": "拒答"},
    },
    {
        "type": "code", "code_mode": "implement", "tag": "状态管理",
        "prompt": "drawerDoc 在请求返回前就被赋值，会带来什么界面问题？", "reference_answer": "可能展示旧数据或空数据",
        "rubric": [
            {"kind": "symbol", "point": "提到 drawerDoc", "weight": 2, "symbol": "drawerDoc"},
            {"kind": "behavior", "point": "说明 await 顺序", "weight": 8},
        ],
        "source": {"file": "App.vue", "line_start": 4, "line_end": 8, "quote": "drawerDoc.value", "symbols": ["drawerDoc", "openDocument"]},
    },
]


async def fake_completion(task, system, user, *, session_id=None, temperature=0.0, max_tokens=2000):
    CALLS.append(task)
    if task == "extract_projects":
        return {"projects": [{"name": "知问", "role": "全栈", "period": "2026", "summary": "检索 Agent 知识库", "source_quote": "负责知问项目的前后端与 Agent 编排"}]}
    if task == "generate_tags":
        return {"tags": [
            {"name": "状态管理", "description": "App.vue 的 streamTrace"},
            {"name": "异常与边界", "description": "证据门槛 75% 与拒答"},
            {"name": "组件设计", "description": "DocumentDrawer 抽屉"},
            {"name": "接口与数据流", "description": "Agent 循环 4 步"},
        ]}
    if task == "generate_capabilities":
        return {"capabilities": [
            {"tag": "状态管理", "target_level": "L3", "acceptance": ["能说明 streamTrace 的更新时机"], "evidence_quote": "streamTrace"},
            {"tag": "异常与边界", "target_level": "L3", "acceptance": ["能解释 75% 门槛"], "evidence_quote": "75%"},
            {"tag": "组件设计", "target_level": "L2", "acceptance": ["能说清组件边界"], "evidence_quote": "DocumentDrawer"},
            {"tag": "接口与数据流", "target_level": "L2", "acceptance": ["能说清 4 步上限"], "evidence_quote": "4 步"},
        ]}
    if task in {"generate_practice"}:
        return {"items": PRACTICE_ITEMS}
    if task == "generate_review":
        return {"items": REVIEW_ITEMS}
    if task == "generate_exam":
        return {"questions": EXAM_QUESTIONS}
    if task == "grade_answer":
        return {"hits": [{"point": "说明门槛作用", "hit": True, "evidence": "避免用不相干片段拼答案"}], "needs_review": False}
    if task == "interview_question":
        return {"question": "证据门槛 75% 在什么情况下会误拒？", "why": "你只说了门槛作用", "rubric": [{"kind": "behavior", "point": "说明误拒情况", "weight": 10}]}
    if task == "report_narrative":
        return {"summary": "整体还行", "strengths": ["状态管理"], "weaknesses": [], "actions": ["补练异常边界"]}
    return {}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        patchers = [
            patch.object(config, "ASSESSMENT_DB", tmp_path / "assessment.db"),
            patch.object(config, "UPLOAD_DIR", uploads),
            patch.object(config, "CHUNK_SIZE", 150),
            patch.object(config, "CHUNK_OVERLAP", 30),
            patch.object(config, "PRACTICE_BATCH_SIZE", 5),
            patch.object(config, "PRACTICE_MIN_TOTAL", 5),
            patch.object(config, "EXAM_QUESTION_COUNT", 3),
            patch.object(config, "EXAM_CANDIDATE_COUNT", 3),
            patch.object(config, "REVIEW_ITEMS_MIN", 2),
            patch.object(config, "PASS_MIN_L2_COUNT", 2),
            patch.object(storage, "DOCUMENTS_FILE", tmp_path / "documents.json"),
            patch.object(storage, "CONVERSATIONS_FILE", tmp_path / "conversations.json"),
            patch.object(llm, "json_completion", AsyncMock(side_effect=fake_completion)),
        ]
        for patcher in patchers:
            patcher.start()
        try:
            rag.invalidate_index()
            store.init_db()
            session = store.create_session("端到端")
            session_id = session["id"]

            resume_doc = storage.add_document("resume.md", "resume.md", len(RESUME), rag.chunk_text(RESUME), len(RESUME), origin="assessment")
            project_doc = storage.add_document("project.md", "project.md", len(PROJECT_DOC), rag.chunk_text(PROJECT_DOC), len(PROJECT_DOC), origin="assessment")
            store.update_session_fields(session_id, resume_document_id=resume_doc["id"], project_document_id=project_doc["id"])
            print(f"1. 文档：简历 {resume_doc['chunk_count']} 块，项目 {project_doc['chunk_count']} 块")

            asyncio.run(assessment_app.tasks.extract_projects(session_id, RESUME))
            project = store.list_projects(session_id)[0]
            store.select_project(session_id, project["id"])
            print(f"2. 项目：{project['name']}")

            code_result = assessment_app.upload_code(session_id, CodeIn(file_name="App.vue", content=VUE_SAMPLE))
            print(f"3. 代码：{code_result['code']['file_name']} · {code_result['symbol_count']} 个符号")

            asyncio.run(assessment_app.tasks.prepare(session_id))
            print(f"4. 标签 {len(store.list_tags(session_id))} 个，能力 {len(store.list_capabilities(session_id))} 条")

            items = asyncio.run(assessment_app.tasks.generate_practice(session_id))
            print(f"5. 练习 {len(items)} 道（代码题 {sum(1 for item in items if item['kind'] == 'code_question')} 道）")

            state.transition(session_id, 0, state.Stage.LEARNING)
            questions = asyncio.run(assessment_app.tasks.generate_exam(session_id))
            print(f"6. 试卷 {len(questions)} 道（代码题 {sum(1 for q in questions if q['type'] == 'code')} 道）")

            current = store.get_session(session_id)
            state.transition(session_id, current["version"], state.Stage.EXAM)
            for question in questions:
                content = "A" if question["type"] == "single_choice" else "drawerDoc 在 await 之后更新，用来避免不相干片段拼答案"
                store.save_exam_answer(question["id"], content, None, 10.0)
            current = store.get_session(session_id)
            state.transition(session_id, current["version"], state.Stage.GRADING, patch={"status": "running"})
            asyncio.run(assessment_app.tasks.grade_exam(session_id))
            graded = store.list_exam_answers(session_id)
            print(f"7. 阅卷 {len(graded)} 道，得分 {sum(item['score'] or 0 for item in graded):.1f}/{len(graded) * 10}")

            current = store.get_session(session_id)
            state.transition(session_id, current["version"], state.Stage.INTERVIEW)
            asyncio.run(interview.start_interview(session_id))
            asyncio.run(interview.answer_interview(session_id, "接口返回空时证据不足，会误拒用户；drawerDoc 不会更新"))
            report = assessment_app.tasks.build_report(session_id)
            asyncio.run(assessment_app.tasks.generate_report_narrative(session_id, report))
            print(f"8. 面试 {len(store.list_interview_turns(session_id))} 轮，判定 passed={report['passed']} level={report['level']}")
            for cap in report["capabilities"]:
                print(f"   - {cap['tag']}: {cap['target']} → {cap['current']} · met={cap['met']} · {cap['gap'] or '达标'}")

            current = store.get_session(session_id)
            current = state.transition(session_id, current["version"], state.Stage.REPORT)
            current = state.transition(session_id, current["version"], state.Stage.PRACTICE)
            review = asyncio.run(assessment_app.tasks.generate_review(session_id))
            print(f"9. 复练第 {review['cycle']} 轮，生成 {review['count']} 道")

            print("\n模型调用链：" + " → ".join(dict.fromkeys(CALLS)))
            print("端到端骨架跑通")
            return 0
        finally:
            for patcher in reversed(patchers):
                patcher.stop()


if __name__ == "__main__":
    raise SystemExit(main())
