from __future__ import annotations

from contextlib import closing
from enum import Enum
from typing import Any, Callable

import assessment_storage as store


class Stage(str, Enum):
    SETUP = "setup"
    LEARNING = "learning"
    EXAM = "exam"
    GRADING = "grading"
    INTERVIEW = "interview"
    REPORT = "report"
    PRACTICE = "practice"
    DONE = "done"


TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.SETUP: {Stage.LEARNING},
    Stage.LEARNING: {Stage.EXAM},
    Stage.EXAM: {Stage.GRADING},
    Stage.GRADING: {Stage.INTERVIEW},
    Stage.INTERVIEW: {Stage.REPORT},
    Stage.REPORT: {Stage.PRACTICE, Stage.DONE},
    Stage.PRACTICE: {Stage.REPORT},
}


class AssessmentError(RuntimeError):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(AssessmentError):
    status_code = 404


class VersionConflict(AssessmentError):
    status_code = 409


class InvalidTransition(AssessmentError):
    status_code = 409


class GuardFailed(AssessmentError):
    status_code = 400


Guard = Callable[[dict[str, Any]], bool | tuple[bool, str]]


def get_stage(session: dict[str, Any]) -> Stage:
    try:
        return Stage(session.get("stage") or "setup")
    except ValueError:
        return Stage.SETUP


def can_transition(current: Stage, target: Stage) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(
    session_id: str,
    expected_version: int,
    to_stage: Stage,
    *,
    guard: Guard | None = None,
    patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """带乐观锁的状态转换。先校验版本，再校验转换，再校验守卫，最后写库。"""
    with closing(store.connect()) as conn, conn:
        row = conn.execute("SELECT * FROM assessment_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFound("评估会话不存在")
        session = dict(row)

        if int(session["version"]) != int(expected_version):
            raise VersionConflict(
                f"会话已被修改（当前版本 {session['version']}，提交版本 {expected_version}），请刷新后重试"
            )

        current = get_stage(session)
        if not can_transition(current, to_stage):
            raise InvalidTransition(f"不能从 {current.value} 直接进入 {to_stage.value}")

        if guard is not None:
            verdict = guard(session)
            if isinstance(verdict, tuple):
                ok, reason = verdict
                if not ok:
                    raise GuardFailed(reason)
            elif not verdict:
                raise GuardFailed(f"不满足进入 {to_stage.value} 的条件")

        fields: dict[str, Any] = dict(patch or {})
        fields["stage"] = to_stage.value
        fields["version"] = int(session["version"]) + 1
        fields.setdefault("status", "idle")
        fields.setdefault("last_error", None)
        fields["updated_at"] = store.now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE assessment_sessions SET {assignments} WHERE id = ? AND version = ?",
            (*fields.values(), session_id, expected_version),
        )

    updated = store.get_session(session_id)
    if updated is None:
        raise NotFound("评估会话不存在")
    return updated


def set_status(session_id: str, status: str, *, last_error: str | None = None) -> None:
    fields: dict[str, Any] = {"status": status}
    if last_error is not None:
        fields["last_error"] = last_error
    store.update_session_fields(session_id, **fields)


def next_action(stage: str) -> str:
    return {
        "setup": "upload_resume",
        "learning": "practice",
        "exam": "submit_exam",
        "grading": "watch_grade",
        "interview": "start_interview",
        "report": "read_report",
        "practice": "repeat_practice",
        "done": "done",
    }.get(stage, "unknown")
