from __future__ import annotations

import sqlite3
from typing import Any


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def practice_prompts(conn: sqlite3.Connection, session_id: str) -> list[str]:
    rows = _rows(
        conn,
        "SELECT prompt FROM practice_items WHERE session_id = ? AND kind IN ('question','code_question') "
        "ORDER BY cycle, order_index",
        (session_id,),
    )
    return [row["prompt"] for row in rows]


def exam_prompts(conn: sqlite3.Connection, session_id: str) -> list[str]:
    rows = _rows(conn, "SELECT prompt FROM exam_questions WHERE session_id = ? ORDER BY order_index", (session_id,))
    return [row["prompt"] for row in rows]


def interview_prompts(conn: sqlite3.Connection, session_id: str) -> list[str]:
    rows = _rows(conn, "SELECT question FROM interview_turns WHERE session_id = ?", (session_id,))
    return [row["question"] for row in rows]


def low_tags(conn: sqlite3.Connection, session_id: str, threshold: int = 60) -> list[str]:
    rows = _rows(
        conn,
        "SELECT t.name AS name, AVG(a.self_score) AS avg_score "
        "FROM practice_answers a "
        "JOIN practice_items p ON p.id = a.practice_item_id "
        "JOIN knowledge_tags t ON t.id = p.tag_id "
        "WHERE p.session_id = ? GROUP BY t.id HAVING avg_score < ?",
        (session_id, threshold),
    )
    return [row["name"] for row in rows]


def build_exam_memory(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    practice = practice_prompts(conn, session_id)
    return {
        "practice_prompts": practice,
        "low_tags": low_tags(conn, session_id),
        "asked_questions": interview_prompts(conn, session_id),
        "seen_prompts": practice + exam_prompts(conn, session_id) + interview_prompts(conn, session_id),
    }


def build_review_memory(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    failed = _rows(
        conn,
        "SELECT t.name AS name, c.target_level AS target FROM capabilities c "
        "JOIN knowledge_tags t ON t.id = c.tag_id WHERE c.session_id = ? AND c.met = 0",
        (session_id,),
    )
    seen = practice_prompts(conn, session_id) + exam_prompts(conn, session_id) + interview_prompts(conn, session_id)
    reasons = _rows(
        conn,
        "SELECT t.name AS tag, w.reason AS reason FROM weak_points w "
        "JOIN knowledge_tags t ON t.id = w.tag_id WHERE w.session_id = ?",
        (session_id,),
    )
    return {
        "failed_capabilities": [{"tag": row["name"], "target": row["target"]} for row in failed],
        "reasons": [{"tag": row["tag"], "reason": row["reason"]} for row in reasons],
        "seen_prompts": seen,
    }
