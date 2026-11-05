from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import assessment as state
import assessment_storage as store
import assessment_tasks as tasks
import code_parser
import config
import interview
import parsers
import pii
import rag
import storage

router = APIRouter(prefix="/api/assessments", tags=["assessments"])
misc_router = APIRouter(prefix="/api", tags=["assessments"])


class AssessmentCreate(BaseModel):
    title: str | None = Field(default=None, max_length=60)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    role: str | None = None
    period: str | None = None
    summary: str | None = Field(default=None, max_length=300)


class SelectProject(BaseModel):
    project_id: str


class CapabilityPatch(BaseModel):
    target_level: str


class CodeIn(BaseModel):
    file_name: str = Field(..., max_length=120)
    content: str


class PracticeAnswer(BaseModel):
    content: str = Field(..., max_length=8000)
    self_score: int | None = Field(default=None, ge=0, le=100)


class ExamAnswerItem(BaseModel):
    question_id: str
    content: str = Field(default="", max_length=8000)


class ExamSubmit(BaseModel):
    idempotency_key: str = Field(..., min_length=4, max_length=120)
    answers: list[ExamAnswerItem]
    skip_exam: bool = False


class InterviewAnswer(BaseModel):
    content: str = Field(..., max_length=8000)


class RepeatSubmit(BaseModel):
    answers: list[ExamAnswerItem]


class AdvanceStage(BaseModel):
    to_stage: str
    version: int | None = None


class CapabilityPatchAll(BaseModel):
    """批量调整能力目标（例如把一整组支撑性能力降为 L2）。"""

    targets: list[dict[str, str]]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get(session_id: str) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="评估会话不存在")
    return session


def _check_version(session: dict[str, Any], version: int | None) -> None:
    if version is None:
        return
    if int(session["version"]) != int(version):
        raise HTTPException(
            status_code=409,
            detail=f"会话已被修改（当前版本 {session['version']}），请刷新后重试",
        )


def _transition(session: dict[str, Any], to_stage: state.Stage, *, version: int | None, guard=None, patch=None) -> dict[str, Any]:
    expected = int(session["version"]) if version is None else int(version)
    try:
        return state.transition(session["id"], expected, to_stage, guard=guard, patch=patch)
    except state.VersionConflict as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except state.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except state.GuardFailed as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except state.NotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


def _detail(session: dict[str, Any]) -> dict[str, Any]:
    session_id = session["id"]
    tags = store.list_tags(session_id)
    capabilities = store.list_capabilities(session_id)
    practice = store.list_practice_items(session_id, int(session.get("practice_cycle") or 0))
    returning = int(session.get("practice_cycle") or 0) > 0 and session.get("stage") == "practice"
    return {
        "session": session,
        "projects": store.list_projects(session_id),
        "selected_project": store.selected_project(session_id),
        "tags": tags,
        "capabilities": capabilities,
        "entities": store.list_entities(session_id),
        "code": {key: value for key, value in (store.get_code(session_id) or {}).items() if key != "content"} or None,
        "practice": {
            "cycle": int(session.get("practice_cycle") or 0),
            "items": practice,
            "count": len([item for item in practice if item["kind"] != "card"]),
            "is_review": returning,
        },
        "exam": {
            "started": bool(store.list_exam_questions(session_id)),
            "questions": store.public_exam_questions(session_id),
            "answers": store.list_exam_answers(session_id),
        },
        "weak_points": store.list_weak_points(session_id),
        "interview": {
            "turns": store.list_interview_turns(session_id),
            "current_round": int(session.get("current_round") or 0),
        },
        "report": store.get_report(session_id),
        "next_action": state.next_action(session.get("stage") or "setup"),
        "llm_mode": config.LLM_MODE,
    }


def _stream(work) -> StreamingResponse:
    """把 async 任务包成 SSE：stage → step* → done / error。"""

    async def generator():
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def emit(event: str, data: dict[str, Any]) -> None:
            await queue.put((event, data))

        async def runner() -> None:
            try:
                result = await work(emit)
                await queue.put(("finished", {"result": result}))
            except HTTPException as exc:
                await queue.put(("error", {"message": str(exc.detail), "code": f"http_{exc.status_code}"}))
            except tasks.TaskError as exc:
                await queue.put(("error", {"message": str(exc), "code": "task_error"}))
            except Exception as exc:  # pragma: no cover - 兜底
                await queue.put(("error", {"message": str(exc) or "处理失败", "code": "unexpected"}))
            finally:
                await queue.put(None)

        asyncio.create_task(runner())
        while True:
            item = await queue.get()
            if item is None:
                break
            event, data = item
            if event == "finished":
                payload = data["result"] if isinstance(data.get("result"), dict) else {}
                yield _sse("done", payload)
                break
            yield _sse(event, data)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #
@router.post("", status_code=201)
def create_assessment(payload: AssessmentCreate | None = None) -> dict[str, Any]:
    return store.create_session(payload.title if payload else None)


@router.get("")
def list_assessments() -> dict[str, Any]:
    return {"assessments": store.list_sessions()}


@router.get("/{session_id}")
def get_assessment(session_id: str) -> dict[str, Any]:
    return _detail(_get(session_id))


@router.delete("/{session_id}")
def delete_assessment(session_id: str) -> dict[str, bool]:
    session = _get(session_id)
    for document_id in {session.get("resume_document_id"), session.get("project_document_id")}:
        if not document_id:
            continue
        document = storage.get_document(document_id)
        if document:
            path = (config.UPLOAD_DIR / document["stored_name"]).resolve()
            if path.parent == config.UPLOAD_DIR.resolve() and path.exists():
                path.unlink(missing_ok=True)
            storage.delete_document(document_id)
    store.delete_session(session_id)
    rag.invalidate_index()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/resume")
async def upload_resume(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    session = _get(session_id)
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 限制")
    raw_name = (file.filename or "resume.md").replace("\\", "/").split("/")[-1]
    extension = Path(raw_name).suffix.lower() or ".md"
    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored_path = config.UPLOAD_DIR / stored_name
    await run_in_threadpool(stored_path.write_bytes, data)
    try:
        text = await run_in_threadpool(parsers.extract_text, stored_path)
        document = storage.add_document(raw_name, stored_name, len(data), rag.chunk_text(text), len(text), origin="assessment")
    except parsers.ParseError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 替换上一份简历
    if session.get("resume_document_id"):
        old = storage.get_document(session["resume_document_id"])
        if old:
            old_path = (config.UPLOAD_DIR / old["stored_name"]).resolve()
            if old_path.parent == config.UPLOAD_DIR.resolve():
                old_path.unlink(missing_ok=True)
            storage.delete_document(old["id"])
    store.update_session_fields(session_id, resume_document_id=document["id"])
    rag.invalidate_index()
    return {"document": document}


@router.post("/{session_id}/extract-projects")
def extract_projects(session_id: str, version: int | None = Query(default=None)):
    session = _get(session_id)
    _check_version(session, version)
    document = storage.get_document(session.get("resume_document_id") or "")
    if document is None:
        raise HTTPException(status_code=400, detail="请先上传简历")
    resume_text = "\n\n".join(chunk["text"] for chunk in document.get("chunks", []))

    async def work(emit):
        projects = await tasks.extract_projects(session_id, resume_text, emit)
        return {"projects": projects, "stage": session["stage"], "version": session["version"]}

    return _stream(work)


@router.get("/{session_id}/projects")
def list_projects(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"projects": store.list_projects(session_id)}


@misc_router.patch("/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatch) -> dict[str, Any]:
    updated = store.update_project(project_id, **payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return updated


@router.post("/{session_id}/project")
def select_project(session_id: str, payload: SelectProject) -> dict[str, Any]:
    _get(session_id)
    if store.get_project(payload.project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    store.select_project(session_id, payload.project_id)
    return {"ok": True, "project": store.selected_project(session_id)}


@router.post("/{session_id}/project-document")
async def upload_project_document(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    session = _get(session_id)
    if not session.get("project_id"):
        raise HTTPException(status_code=400, detail="请先选择一个项目")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 限制")
    raw_name = (file.filename or "project.md").replace("\\", "/").split("/")[-1]
    extension = Path(raw_name).suffix.lower() or ".md"
    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored_path = config.UPLOAD_DIR / stored_name
    await run_in_threadpool(stored_path.write_bytes, data)
    try:
        text = await run_in_threadpool(parsers.extract_text, stored_path)
        chunks = rag.chunk_text(text)
        if len(chunks) < 5:
            raise HTTPException(
                status_code=400,
                detail=f"项目文档太短（只有 {len(chunks)} 个分块，至少需要 5 个），请补充背景、技术栈、难点和取舍",
            )
        document = storage.add_document(raw_name, stored_name, len(data), chunks, len(text), origin="assessment")
    except parsers.ParseError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session.get("project_document_id"):
        old = storage.get_document(session["project_document_id"])
        if old:
            old_path = (config.UPLOAD_DIR / old["stored_name"]).resolve()
            if old_path.parent == config.UPLOAD_DIR.resolve():
                old_path.unlink(missing_ok=True)
            storage.delete_document(old["id"])
    store.update_session_fields(session_id, project_document_id=document["id"])
    rag.invalidate_index()
    return {"document": document}


@router.post("/{session_id}/code")
def upload_code(session_id: str, payload: CodeIn) -> dict[str, Any]:
    session = _get(session_id)
    if not session.get("project_id"):
        raise HTTPException(status_code=400, detail="请先选择一个项目")
    extension = Path(payload.file_name).suffix.lower()
    if extension not in config.CODE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="只支持 .vue / .ts / .js 单文件")
    content = payload.content.replace("\r\n", "\n").replace("\r", "\n")
    if len(content.encode("utf-8")) > config.CODE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="代码文件不能超过 200 KB")
    if not content.strip():
        raise HTTPException(status_code=400, detail="代码内容为空")
    hits = pii.scan_secrets(content)
    if hits:
        raise HTTPException(status_code=400, detail=f"代码里检测到敏感信息（{', '.join(hits)}），请删除后再上传")
    try:
        parsed = code_parser.parse_code(payload.file_name, content)
    except code_parser.CodeParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    code = store.save_code(session_id, payload.file_name, parsed["language"], content, parsed)
    code_entities = [
        {"name": item["name"], "kind": item["kind"] if item["kind"] in {"component", "api", "function", "metric", "term"} else "term"}
        for item in parsed["symbols"][:30]
    ]
    store.save_entities(session_id, code_entities, source_type="code")
    return {
        "code": {key: value for key, value in code.items() if key != "content"},
        "symbol_count": len(parsed["symbols"]),
        "symbols": parsed["symbols"][:60],
    }


@router.get("/{session_id}/code")
def get_code(session_id: str) -> dict[str, Any]:
    _get(session_id)
    code = store.get_code(session_id)
    if code is None:
        return {"code": None}
    return {"code": {key: value for key, value in code.items() if key != "content"}}


@router.get("/{session_id}/code/content")
def get_code_content(session_id: str) -> dict[str, Any]:
    _get(session_id)
    code = store.get_code(session_id)
    if code is None:
        return {"content": None, "file_name": None}
    return {"content": code["content"], "file_name": code["file_name"]}


@router.delete("/{session_id}/code")
def delete_code(session_id: str) -> dict[str, bool]:
    _get(session_id)
    store.delete_code(session_id)
    return {"ok": True}


@router.get("/{session_id}/entities")
def list_entities(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"entities": store.list_entities(session_id)}


@router.post("/{session_id}/prepare")
def prepare(session_id: str, version: int | None = Query(default=None)):
    session = _get(session_id)
    _check_version(session, version)

    async def work(emit):
        result = await tasks.prepare(session_id, emit)
        return {
            "tags": result["tags"],
            "capabilities": result["capabilities"],
            "practice_count": len(result.get("practice") or []),
        }

    return _stream(work)


@router.get("/{session_id}/capabilities")
def list_capabilities(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"capabilities": store.list_capabilities(session_id)}


@router.post("/{session_id}/capabilities/batch")
def patch_capabilities_batch(session_id: str, payload: CapabilityPatchAll) -> dict[str, Any]:
    """一次调整多条能力目标：{"targets": [{"capability_id": "...", "target_level": "L2"}]}"""
    _get(session_id)
    updated = []
    for item in payload.targets:
        capability_id = item.get("capability_id") or item.get("tag_id") or ""
        level = str(item.get("target_level") or "").upper()
        if not capability_id or level not in {"L1", "L2", "L3", "L4"}:
            continue
        result = store.update_capability_target(capability_id, level)
        if result:
            updated.append({"capability_id": capability_id, "target_level": level})
    return {"updated": updated, "count": len(updated)}


@misc_router.patch("/capabilities/{capability_id}")
def patch_capability(capability_id: str, payload: CapabilityPatch) -> dict[str, Any]:
    try:
        updated = store.update_capability_target(capability_id, payload.target_level.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="能力目标不存在")
    return updated


# --------------------------------------------------------------------------- #
# learning
# --------------------------------------------------------------------------- #
@router.get("/{session_id}/practice")
def list_practice(session_id: str, cycle: int = Query(default=0, ge=0)) -> dict[str, Any]:
    _get(session_id)
    items = store.list_practice_items(session_id, cycle)
    return {"cycle": cycle, "items": items}


@misc_router.post("/practice-items/{item_id}/answer")
def answer_practice(item_id: str, payload: PracticeAnswer) -> dict[str, Any]:
    item = store.get_practice_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="练习题不存在")
    store.save_practice_answer(item_id, payload.content, payload.self_score)
    return {"ok": True}


@router.post("/{session_id}/practice/more")
def more_practice(session_id: str):
    _get(session_id)

    async def work(emit):
        items = await tasks.expand_practice(session_id, emit)
        return {"count": len([item for item in items if item["kind"] != "card"])}

    return _stream(work)


# --------------------------------------------------------------------------- #
# exam
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/exam/start")
def start_exam(session_id: str, version: int | None = Query(default=None)):
    session = _get(session_id)

    def guard(current):
        if current["stage"] not in {"learning", "exam"}:
            return False, "当前阶段不能生成试卷"
        return True, ""

    async def work(emit):
        questions = await tasks.generate_exam(session_id, emit)
        updated = session
        if session["stage"] == "learning":
            try:
                updated = _transition(session, state.Stage.EXAM, version=version)
            except HTTPException as exc:
                if exc.status_code == 409:
                    # 试卷已经生成，阶段转换失败不让前端误以为失败；返回阶段冲突但带结果
                    return {
                        "count": len(questions),
                        "questions": store.public_exam_questions(session_id),
                        "version": session["version"],
                        "stage": session["stage"],
                        "transition": f"skipped: {exc.detail}",
                    }
                raise
        return {"count": len(questions), "questions": store.public_exam_questions(session_id), "version": updated["version"], "stage": updated["stage"]}

    if session["stage"] == "learning":
        if not store.list_practice_items(session_id, int(session.get("practice_cycle") or 0)):
            raise HTTPException(status_code=400, detail="请先完成至少 1 道练习题，或选择跳过")
    return _stream(work)


@router.get("/{session_id}/exam")
def get_exam(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"questions": store.public_exam_questions(session_id)}


@router.post("/{session_id}/exam/submit")
def submit_exam(session_id: str, payload: ExamSubmit, version: int | None = Query(default=None)) -> dict[str, Any]:
    session = _get(session_id)
    _check_version(session, version)
    if payload.skip_exam:
        if session["stage"] == "grading":
            return {"stage": session["stage"], "status": session["status"], "version": session["version"], "next_action": "watch_grade_stream"}
        if session["stage"] == "learning":
            # 跳过考试：learning → exam → grading，两步都走状态机
            session = _transition(session, state.Stage.EXAM, version=version)
            version = session["version"]
        updated = _transition(session, state.Stage.GRADING, version=version, patch={"status": "running"})
        return {"stage": updated["stage"], "status": updated["status"], "version": updated["version"], "next_action": "watch_grade_stream"}

    questions = store.list_exam_questions(session_id)
    if not questions:
        raise HTTPException(status_code=400, detail="还没有生成试卷")
    answer_map = {item.question_id: item.content for item in payload.answers}
    missing = [question["id"] for question in questions if not str(answer_map.get(question["id"]) or "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"还有 {len(missing)} 道题没有作答")

    payload_hash = json.dumps(
        sorted([(item.question_id, item.content) for item in payload.answers]), ensure_ascii=False
    )
    if not store.create_submission(session_id, payload.idempotency_key, payload_hash):
        latest = store.get_session(session_id) or {}
        return {"stage": latest.get("stage"), "status": latest.get("status"), "version": latest.get("version"), "next_action": "watch_grade_stream", "duplicated": True}

    for question in questions:
        store.save_exam_answer(question["id"], answer_map[question["id"]], None, 10.0)
    if session["stage"] == "grading":
        # 已经提交过（重复提交但换了幂等键）：答案已更新，不需要再转阶段
        latest = store.get_session(session_id) or session
        return {"stage": latest["stage"], "status": latest["status"], "version": latest["version"], "next_action": "watch_grade_stream"}
    updated = _transition(session, state.Stage.GRADING, version=version, patch={"status": "running"})
    return {"stage": updated["stage"], "status": updated["status"], "version": updated["version"], "next_action": "watch_grade_stream"}


@router.post("/{session_id}/exam/grade")
def grade_exam(session_id: str):
    _get(session_id)

    async def work(emit):
        result = await tasks.grade_exam(session_id, emit)
        return {"graded": result["graded"], "weak_points": result["weak_points"]}

    return _stream(work)


@router.get("/{session_id}/weak-points")
def weak_points(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"weak_points": store.list_weak_points(session_id)}


# --------------------------------------------------------------------------- #
# interview
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/interview/start")
async def start_interview(session_id: str, version: int | None = Query(default=None)) -> dict[str, Any]:
    session = _get(session_id)
    _check_version(session, version)
    if session["stage"] == "grading":
        _transition(session, state.Stage.INTERVIEW, version=version)
    try:
        return await interview.start_interview(session_id)
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/interview/answer")
async def answer_interview(session_id: str, payload: InterviewAnswer, version: int | None = Query(default=None)) -> dict[str, Any]:
    _get(session_id)
    try:
        result = await interview.answer_interview(session_id, payload.content)
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = store.get_session(session_id) or {}
    return {**result, "version": session.get("version")}


@router.get("/{session_id}/interview")
def get_interview(session_id: str) -> dict[str, Any]:
    _get(session_id)
    return {"turns": store.list_interview_turns(session_id)}


# --------------------------------------------------------------------------- #
# report / repeat
# --------------------------------------------------------------------------- #
@router.post("/{session_id}/report")
def make_report(session_id: str, version: int | None = Query(default=None)):
    session = _get(session_id)
    _check_version(session, version)

    async def work(emit):
        report = tasks.build_report(session_id)
        saved = await tasks.generate_report_narrative(session_id, report, emit)
        current = store.get_session(session_id) or session
        if current.get("stage") == "interview":
            try:
                _transition(current, state.Stage.REPORT, version=None)
            except HTTPException:
                # 报告已经落库，阶段转换失败不影响前端读取报告
                pass
        return {"report": saved}

    return _stream(work)


@router.get("/{session_id}/report")
def get_report(session_id: str) -> dict[str, Any]:
    _get(session_id)
    report = store.get_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="还没有生成报告")
    return {"report": report}


@router.post("/{session_id}/repeat/start")
def start_repeat(session_id: str, version: int | None = Query(default=None)):
    session = _get(session_id)
    _check_version(session, version)
    if session["stage"] != "report":
        raise HTTPException(status_code=409, detail="只有报告阶段可以开始复练")

    async def work(emit):
        result = await tasks.generate_review(session_id, emit)
        updated = _transition(session, state.Stage.PRACTICE, version=version)
        return {**result, "stage": updated["stage"], "version": updated["version"]}

    return _stream(work)


@router.post("/{session_id}/repeat/submit")
async def submit_repeat(session_id: str, payload: RepeatSubmit, version: int | None = Query(default=None)) -> dict[str, Any]:
    session = _get(session_id)
    _check_version(session, version)
    cycle = int(session.get("practice_cycle") or 0)
    items = store.list_practice_items(session_id, cycle)
    answer_map = {item.question_id: item.content for item in payload.answers}
    to_grade = [
        {"id": item["id"], "prompt": item["prompt"], "answer": item.get("answer"), "content": answer_map[item["id"]]}
        for item in items
        if item["kind"] != "card" and answer_map.get(item["id"])
    ]
    if not to_grade:
        raise HTTPException(status_code=400, detail="至少作答 1 道复练题")
    scores = await tasks.grade_review_answers(session_id, to_grade)
    for item in to_grade:
        store.save_practice_answer(item["id"], item["content"], scores.get(item["id"], 0))
    evaluation = tasks.compute_evaluation(session_id)
    store.apply_capability_results(session_id, evaluation)

    # 复练后重新生成确定性报告，保留原来的总结与建议，只更新判定和差距
    previous = store.get_report(session_id) or {}
    report = tasks.build_report(session_id)
    report["summary"] = previous.get("summary") or ""
    report["actions"] = previous.get("actions") or report["actions"]
    store.save_report(session_id, report)

    if session["stage"] == "practice":
        updated = _transition(session, state.Stage.REPORT, version=version)
    else:
        updated = store.get_session(session_id) or session
    return {
        "answered": len(to_grade),
        "evaluation": evaluation,
        "report": report,
        "stage": updated["stage"],
        "version": updated["version"],
    }


@router.get("/{session_id}/repeat")
def get_repeat(session_id: str) -> dict[str, Any]:
    session = _get(session_id)
    cycle = int(session.get("practice_cycle") or 0)
    return {
        "cycle": cycle,
        "items": store.list_practice_items(session_id, cycle),
        "evaluation": tasks.compute_evaluation(session_id),
    }


@router.post("/{session_id}/advance")
def advance_stage(session_id: str, payload: AdvanceStage) -> dict[str, Any]:
    """从前端显式推进阶段（例如：练习完成 → 考试；面试完成 → 报告）。"""
    session = _get(session_id)
    try:
        target = state.Stage(payload.to_stage)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"未知阶段：{payload.to_stage}") from exc
    version = payload.version if payload.version is not None else int(session["version"])
    updated = _transition(session, target, version=version)
    return {"stage": updated["stage"], "version": updated["version"]}


@router.get("/{session_id}/export")
def export_assessment(session_id: str) -> dict[str, Any]:
    session = _get(session_id)
    return {
        "session": session,
        "detail": _detail(session),
        "llm_cost": store.session_cost(session_id),
    }
