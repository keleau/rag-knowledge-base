from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assessment_sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'setup'
    CHECK (stage IN ('setup','learning','exam','grading','interview','report','practice','done')),
  status TEXT NOT NULL DEFAULT 'idle'
    CHECK (status IN ('idle','running','awaiting_user','completed','failed')),
  version INTEGER NOT NULL DEFAULT 0,
  resume_document_id TEXT,
  project_id TEXT,
  project_document_id TEXT,
  project_code_id TEXT,
  current_round INTEGER NOT NULL DEFAULT 0,
  practice_cycle INTEGER NOT NULL DEFAULT 0,
  passed INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT,
  period TEXT,
  summary TEXT,
  source_quote TEXT NOT NULL,
  selected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_tags (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_entities (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('component','api','function','metric','term')),
  source_type TEXT NOT NULL CHECK (source_type IN ('project_doc','code')),
  source_ref TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_codes (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL UNIQUE,
  file_name TEXT NOT NULL,
  language TEXT NOT NULL,
  content TEXT NOT NULL,
  line_count INTEGER NOT NULL,
  symbols_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  target_level TEXT NOT NULL CHECK (target_level IN ('L1','L2','L3','L4')),
  current_level TEXT CHECK (current_level IN ('L1','L2','L3','L4')),
  acceptance_json TEXT NOT NULL,
  evidence_quote TEXT NOT NULL,
  met INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  UNIQUE (session_id, tag_id),
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id)
);

CREATE TABLE IF NOT EXISTS practice_items (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('card','question','code_question')),
  cycle INTEGER NOT NULL DEFAULT 0,
  prompt TEXT NOT NULL,
  answer TEXT,
  explanation TEXT,
  source_document_id TEXT,
  source_chunk_id TEXT,
  source_quote TEXT,
  source_file TEXT,
  line_start INTEGER,
  line_end INTEGER,
  source_symbols_json TEXT,
  code_mode TEXT CHECK (code_mode IS NULL OR code_mode IN ('locate','explain','implement')),
  entities_json TEXT,
  difficulty TEXT NOT NULL DEFAULT 'medium',
  order_index INTEGER NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id)
);

CREATE TABLE IF NOT EXISTS practice_answers (
  id TEXT PRIMARY KEY,
  practice_item_id TEXT NOT NULL UNIQUE,
  content TEXT NOT NULL,
  self_score INTEGER CHECK (self_score BETWEEN 0 AND 100),
  created_at TEXT NOT NULL,
  FOREIGN KEY (practice_item_id) REFERENCES practice_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_questions (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('single_choice','short_answer','code')),
  code_mode TEXT CHECK (code_mode IS NULL OR code_mode IN ('locate','explain','implement')),
  prompt TEXT NOT NULL,
  options_json TEXT,
  reference_answer TEXT NOT NULL,
  rubric_json TEXT NOT NULL,
  source_document_id TEXT,
  source_chunk_id TEXT,
  source_quote TEXT,
  source_file TEXT,
  line_start INTEGER,
  line_end INTEGER,
  source_symbols_json TEXT,
  entities_json TEXT,
  difficulty TEXT NOT NULL DEFAULT 'medium',
  order_index INTEGER NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id)
);

CREATE TABLE IF NOT EXISTS exam_answers (
  id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL UNIQUE,
  content TEXT NOT NULL,
  score REAL,
  max_score REAL,
  hits_json TEXT,
  evidence_json TEXT,
  needs_review INTEGER NOT NULL DEFAULT 0,
  review_note TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_submissions (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (session_id, idempotency_key),
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weak_points (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  severity REAL NOT NULL,
  reason TEXT NOT NULL,
  evidence_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id)
);

CREATE TABLE IF NOT EXISTS interview_turns (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  weak_point_id TEXT,
  tag_id TEXT NOT NULL,
  round_index INTEGER NOT NULL,
  question TEXT NOT NULL,
  answer TEXT,
  rubric_json TEXT,
  score REAL,
  evidence_json TEXT,
  follow_up_of TEXT,
  status TEXT NOT NULL DEFAULT 'asking' CHECK (status IN ('asking','answered','graded')),
  created_at TEXT NOT NULL,
  answered_at TEXT,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES knowledge_tags(id)
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL UNIQUE,
  summary TEXT NOT NULL,
  passed INTEGER NOT NULL DEFAULT 0,
  level TEXT,
  capabilities_json TEXT,
  tag_scores_json TEXT NOT NULL,
  strengths_json TEXT,
  weaknesses_json TEXT,
  actions_json TEXT,
  next_json TEXT,
  evidence_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  task TEXT NOT NULL,
  mode TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  input_hash TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON assessment_sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_session ON projects(session_id);
CREATE INDEX IF NOT EXISTS idx_tags_session ON knowledge_tags(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_entities_session ON project_entities(session_id);
CREATE INDEX IF NOT EXISTS idx_practice_session ON practice_items(session_id, cycle, order_index);
CREATE INDEX IF NOT EXISTS idx_questions_session ON exam_questions(session_id, order_index);
CREATE INDEX IF NOT EXISTS idx_weak_session ON weak_points(session_id, severity);
CREATE INDEX IF NOT EXISTS idx_turns_session ON interview_turns(session_id, round_index);
CREATE INDEX IF NOT EXISTS idx_llm_session ON llm_calls(session_id, created_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex[:12]
    return f"{prefix}{value}" if prefix else value


def connect() -> sqlite3.Connection:
    Path(config.ASSESSMENT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.ASSESSMENT_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """建表 + 轻量迁移。缺表才跑建表脚本，已有库只做补列检查。"""
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'assessment_sessions'"
        ).fetchone()
        if row is None:
            with conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA_SQL)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """给旧库补列；SQLite 没有 ADD COLUMN IF NOT EXISTS，只能先查再补。"""
    def columns(table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    targets = {
        "reports": [("next_json", "TEXT")],
        "exam_questions": [("code_mode", "TEXT"), ("source_symbols_json", "TEXT")],
        "practice_items": [
            ("cycle", "INTEGER NOT NULL DEFAULT 0"),
            ("code_mode", "TEXT"),
            ("source_symbols_json", "TEXT"),
            ("difficulty", "TEXT NOT NULL DEFAULT 'medium'"),
        ],
        "assessment_sessions": [
            ("practice_cycle", "INTEGER NOT NULL DEFAULT 0"),
            ("passed", "INTEGER NOT NULL DEFAULT 0"),
            ("project_code_id", "TEXT"),
        ],
    }
    with conn:
        for table, extra in targets.items():
            existing = columns(table)
            if not existing:
                continue
            for name, ddl in extra:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def reset_init_cache() -> None:
    """保留给测试与脚本使用；当前实现不再缓存初始化结果。"""
    return None


def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def decode_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def encode_json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
def create_session(title: str | None = None) -> dict[str, Any]:
    init_db()
    session_id = new_id("as_")
    stamp = now()
    clean_title = (title or "").strip()[:60] or "新建评估"
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO assessment_sessions (id, title, stage, status, version, created_at, updated_at) "
            "VALUES (?, ?, 'setup', 'idle', 0, ?, ?)",
            (session_id, clean_title, stamp, stamp),
        )
    return get_session(session_id) or {}


def get_session(session_id: str) -> dict[str, Any] | None:
    init_db()
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM assessment_sessions WHERE id = ?", (session_id,)).fetchone()
    return _dict(row)


def list_sessions() -> list[dict[str, Any]]:
    init_db()
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM assessment_sessions ORDER BY updated_at DESC"
        ).fetchall()
    return _dicts(rows)


def update_session_fields(session_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_session(session_id)
    fields["updated_at"] = now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with closing(connect()) as conn, conn:
        conn.execute(
            f"UPDATE assessment_sessions SET {assignments} WHERE id = ?",
            (*fields.values(), session_id),
        )
    return get_session(session_id)


def delete_session(session_id: str) -> bool:
    init_db()
    with closing(connect()) as conn, conn:
        cursor = conn.execute("DELETE FROM assessment_sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0


# --------------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------------- #
def replace_projects(session_id: str, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """重新提取项目：保留之前按名字选中的项目，否则回调 selected_project 会丢失。"""
    stamp = now()
    previous = selected_project(session_id)
    previous_name = previous["name"] if previous else None
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM projects WHERE session_id = ?", (session_id,))
        for item in projects:
            conn.execute(
                "INSERT INTO projects (id, session_id, name, role, period, summary, source_quote, selected, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    new_id("pj_"),
                    session_id,
                    item["name"],
                    item.get("role"),
                    item.get("period"),
                    item.get("summary"),
                    item.get("source_quote") or "",
                    stamp,
                ),
            )
    saved = list_projects(session_id)
    if previous_name:
        match = next((item for item in saved if item["name"] == previous_name), None)
        if match:
            select_project(session_id, match["id"])
    return list_projects(session_id)


def list_projects(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE session_id = ? ORDER BY created_at, name", (session_id,)
        ).fetchall()
    return _dicts(rows)


def get_project(project_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _dict(row)


def update_project(project_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {key: value for key, value in fields.items() if key in {"name", "role", "period", "summary"}}
    if allowed:
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        with closing(connect()) as conn, conn:
            conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", (*allowed.values(), project_id))
    return get_project(project_id)


def select_project(session_id: str, project_id: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE projects SET selected = 0 WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE projects SET selected = 1 WHERE session_id = ? AND id = ?", (session_id, project_id)
        )
    update_session_fields(session_id, project_id=project_id)


def selected_project(session_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE session_id = ? AND selected = 1 LIMIT 1", (session_id,)
        ).fetchone()
    return _dict(row)


# --------------------------------------------------------------------------- #
# tags / entities / code
# --------------------------------------------------------------------------- #
def save_tags(session_id: str, tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """重新生成标签时，先清掉依赖旧标签的产物，避免知识标签的外键冲突。

    只清理“重新生成”的上下文（setup / learning）；一旦进入考试之后就不再替换标签。
    """
    with closing(connect()) as conn, conn:
        session = conn.execute(
            "SELECT stage FROM assessment_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is not None and session["stage"] in {"learning", "setup"}:
            conn.execute("DELETE FROM practice_items WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM exam_questions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM capabilities WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM knowledge_tags WHERE session_id = ?", (session_id,))
        for index, item in enumerate(tags):
            conn.execute(
                "INSERT INTO knowledge_tags (id, session_id, name, description, order_index) VALUES (?, ?, ?, ?, ?)",
                (item.get("id") or new_id("tg_"), session_id, item["name"], item.get("description") or "", index),
            )
    return list_tags(session_id)


def list_tags(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_tags WHERE session_id = ? ORDER BY order_index", (session_id,)
        ).fetchall()
    return _dicts(rows)


def save_entities(session_id: str, entities: list[dict[str, Any]], source_type: str = "project_doc") -> None:
    stamp = now()
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM project_entities WHERE session_id = ? AND source_type = ?", (session_id, source_type))
        seen: set[str] = set()
        for item in entities:
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            kind = item.get("kind") if item.get("kind") in {"component", "api", "function", "metric", "term"} else "term"
            conn.execute(
                "INSERT INTO project_entities (id, session_id, name, kind, source_type, source_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id("en_"), session_id, name, kind, source_type, item.get("source_ref"), stamp),
            )


def list_entities(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM project_entities WHERE session_id = ? ORDER BY kind, name", (session_id,)
        ).fetchall()
    return _dicts(rows)


def clear_entities(session_id: str, source_type: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "DELETE FROM project_entities WHERE session_id = ? AND source_type = ?",
            (session_id, source_type),
        )


def save_code(session_id: str, file_name: str, language: str, content: str, parsed: dict[str, Any]) -> dict[str, Any]:
    code_id = new_id("cd_")
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM project_codes WHERE session_id = ?", (session_id,))
        conn.execute(
            "INSERT INTO project_codes (id, session_id, file_name, language, content, line_count, symbols_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code_id,
                session_id,
                file_name,
                language,
                content,
                int(parsed.get("line_count") or 0),
                encode_json(parsed.get("symbols") or []),
                now(),
            ),
        )
    update_session_fields(session_id, project_code_id=code_id)
    return get_code(session_id) or {}


def get_code(session_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM project_codes WHERE session_id = ?", (session_id,)).fetchone()
    item = _dict(row)
    if item:
        item["symbols"] = decode_json(item.pop("symbols_json", "[]"), [])
    return item


def delete_code(session_id: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM project_codes WHERE session_id = ?", (session_id,))
    update_session_fields(session_id, project_code_id=None)


# --------------------------------------------------------------------------- #
# capabilities
# --------------------------------------------------------------------------- #
def save_capabilities(session_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stamp = now()
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM capabilities WHERE session_id = ?", (session_id,))
        for item in items:
            level = item.get("target_level") if item.get("target_level") in {"L1", "L2", "L3", "L4"} else "L2"
            conn.execute(
                "INSERT INTO capabilities (id, session_id, tag_id, target_level, current_level, acceptance_json, "
                "evidence_quote, met, updated_at) VALUES (?, ?, ?, ?, NULL, ?, ?, 0, ?)",
                (
                    new_id("cp_"),
                    session_id,
                    item["tag_id"],
                    level,
                    encode_json(item.get("acceptance") or []),
                    item.get("evidence_quote") or "",
                    stamp,
                ),
            )
    return list_capabilities(session_id)


def list_capabilities(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT c.*, t.name AS tag, t.order_index AS tag_order FROM capabilities c "
            "JOIN knowledge_tags t ON t.id = c.tag_id WHERE c.session_id = ? ORDER BY t.order_index",
            (session_id,),
        ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["acceptance"] = decode_json(item.pop("acceptance_json", "[]"), [])
    return items


def update_capability_target(capability_id: str, target_level: str) -> dict[str, Any] | None:
    if target_level not in {"L1", "L2", "L3", "L4"}:
        raise ValueError("目标等级必须是 L1–L4")
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE capabilities SET target_level = ?, updated_at = ? WHERE id = ?",
            (target_level, now(), capability_id),
        )
        row = conn.execute("SELECT * FROM capabilities WHERE id = ?", (capability_id,)).fetchone()
    return _dict(row)


def apply_capability_results(session_id: str, evaluation: dict[str, Any]) -> None:
    stamp = now()
    with closing(connect()) as conn, conn:
        for item in evaluation.get("criteria") or []:
            conn.execute(
                "UPDATE capabilities SET current_level = ?, met = ?, updated_at = ? "
                "WHERE session_id = ? AND tag_id = ?",
                (item.get("current"), 1 if item.get("met") else 0, stamp, session_id, item["tag_id"]),
            )
        conn.execute(
            "UPDATE assessment_sessions SET passed = ? WHERE id = ?",
            (1 if evaluation.get("passed") else 0, session_id),
        )


# --------------------------------------------------------------------------- #
# practice
# --------------------------------------------------------------------------- #
def save_practice_items(session_id: str, items: list[dict[str, Any]], cycle: int = 0) -> list[dict[str, Any]]:
    with closing(connect()) as conn, conn:
        start = conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) FROM practice_items WHERE session_id = ? AND cycle = ?",
            (session_id, cycle),
        ).fetchone()[0]
        base = (start or 0) + 1
        for offset, item in enumerate(items):
            source = item.get("source") or {}
            conn.execute(
                "INSERT INTO practice_items (id, session_id, tag_id, kind, cycle, prompt, answer, explanation, "
                "source_document_id, source_chunk_id, source_quote, source_file, line_start, line_end, "
                "source_symbols_json, code_mode, entities_json, difficulty, order_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("pi_"),
                    session_id,
                    item["tag_id"],
                    item.get("kind") or "question",
                    cycle,
                    item["prompt"],
                    item.get("answer"),
                    item.get("explanation"),
                    source.get("document_id"),
                    source.get("chunk_id"),
                    source.get("quote"),
                    source.get("file"),
                    source.get("line_start"),
                    source.get("line_end"),
                    encode_json(source.get("symbols") or []),
                    item.get("code_mode"),
                    encode_json(item.get("entities") or []),
                    item.get("difficulty") or "medium",
                    base + offset,
                ),
            )
    return list_practice_items(session_id, cycle)


def list_practice_items(session_id: str, cycle: int = 0) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT p.*, t.name AS tag, a.content AS user_answer, a.self_score AS self_score "
            "FROM practice_items p "
            "JOIN knowledge_tags t ON t.id = p.tag_id "
            "LEFT JOIN practice_answers a ON a.practice_item_id = p.id "
            "WHERE p.session_id = ? AND p.cycle = ? ORDER BY p.order_index",
            (session_id, cycle),
        ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["entities"] = decode_json(item.pop("entities_json", "[]"), [])
        item["symbols"] = decode_json(item.pop("source_symbols_json", "[]"), [])
    return items


def get_practice_item(item_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM practice_items WHERE id = ?", (item_id,)).fetchone()
    return _dict(row)


def save_practice_answer(item_id: str, content: str, self_score: int | None) -> None:
    score = None if self_score is None else max(0, min(int(self_score), 100))
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO practice_answers (id, practice_item_id, content, self_score, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(practice_item_id) DO UPDATE SET content = excluded.content, "
            "self_score = excluded.self_score, created_at = excluded.created_at",
            (new_id("pa_"), item_id, content, score, now()),
        )


def count_practice_items(session_id: str, cycle: int = 0, kind: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM practice_items WHERE session_id = ? AND cycle = ?"
    params: list[Any] = [session_id, cycle]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    with closing(connect()) as conn:
        return int(conn.execute(sql, tuple(params)).fetchone()[0])


def practice_scores_by_tag(session_id: str) -> dict[str, float]:
    """每个标签取最近一次自评（0–1），没有自评记为 0。"""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT p.tag_id AS tag_id, AVG(a.self_score) AS avg_score FROM practice_answers a "
            "JOIN practice_items p ON p.id = a.practice_item_id WHERE p.session_id = ? GROUP BY p.tag_id",
            (session_id,),
        ).fetchall()
    return {row["tag_id"]: float(row["avg_score"] or 0) / 100.0 for row in rows}


def review_scores_by_tag(session_id: str) -> dict[str, float]:
    """复练（cycle>0）的评分，按标签聚合，用于补强判定。"""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT p.tag_id AS tag_id, AVG(a.self_score) AS avg_score "
            "FROM practice_answers a JOIN practice_items p ON p.id = a.practice_item_id "
            "WHERE p.session_id = ? AND p.cycle > 0 AND a.self_score IS NOT NULL GROUP BY p.tag_id",
            (session_id,),
        ).fetchall()
    return {row["tag_id"]: float(row["avg_score"] or 0) / 100.0 for row in rows}


# --------------------------------------------------------------------------- #
# exam
# --------------------------------------------------------------------------- #
def save_exam_questions(session_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM exam_questions WHERE session_id = ?", (session_id,))
        for index, item in enumerate(items):
            source = item.get("source") or {}
            conn.execute(
                "INSERT INTO exam_questions (id, session_id, tag_id, type, code_mode, prompt, options_json, "
                "reference_answer, rubric_json, source_document_id, source_chunk_id, source_quote, source_file, "
                "line_start, line_end, source_symbols_json, entities_json, difficulty, order_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("eq_"),
                    session_id,
                    item["tag_id"],
                    item.get("type") or "short_answer",
                    item.get("code_mode"),
                    item["prompt"],
                    encode_json(item.get("options") or []) if item.get("options") else None,
                    item.get("reference_answer") or item.get("answer") or "",
                    encode_json(item.get("rubric") or []),
                    source.get("document_id"),
                    source.get("chunk_id"),
                    source.get("quote"),
                    source.get("file"),
                    source.get("line_start"),
                    source.get("line_end"),
                    encode_json(source.get("symbols") or []),
                    encode_json(item.get("entities") or []),
                    item.get("difficulty") or "medium",
                    index,
                ),
            )
    return list_exam_questions(session_id)


def _exam_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["options"] = decode_json(item.pop("options_json", None), [])
    item["rubric"] = decode_json(item.pop("rubric_json", "[]"), [])
    item["entities"] = decode_json(item.pop("entities_json", "[]"), [])
    item["symbols"] = decode_json(item.pop("source_symbols_json", "[]"), [])
    return item


def list_exam_questions(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT q.*, t.name AS tag FROM exam_questions q JOIN knowledge_tags t ON t.id = q.tag_id "
            "WHERE q.session_id = ? ORDER BY q.order_index",
            (session_id,),
        ).fetchall()
    return [_exam_row_to_dict(row) for row in rows]


def public_exam_questions(session_id: str) -> list[dict[str, Any]]:
    """给前端的试卷：不包含参考答案和阅卷 rubric。"""
    items = list_exam_questions(session_id)
    for item in items:
        item.pop("reference_answer", None)
        item.pop("rubric", None)
    return items


def get_question(question_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM exam_questions WHERE id = ?", (question_id,)).fetchone()
    return _exam_row_to_dict(row) if row else None


def save_exam_answer(question_id: str, content: str, score: float | None, max_score: float | None,
                     hits: list[dict[str, Any]] | None = None, evidence: list[dict[str, Any]] | None = None,
                     needs_review: bool = False, review_note: str | None = None) -> dict[str, Any]:
    answer_id = new_id("ea_")
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO exam_answers (id, question_id, content, score, max_score, hits_json, evidence_json, "
            "needs_review, review_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(question_id) DO UPDATE SET content = excluded.content, score = excluded.score, "
            "max_score = excluded.max_score, hits_json = excluded.hits_json, evidence_json = excluded.evidence_json, "
            "needs_review = excluded.needs_review, review_note = excluded.review_note, created_at = excluded.created_at",
            (
                answer_id,
                question_id,
                content,
                score,
                max_score,
                encode_json(hits or []),
                encode_json(evidence or []),
                1 if needs_review else 0,
                review_note,
                now(),
            ),
        )
    return get_exam_answer(question_id) or {}


def get_exam_answer(question_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM exam_answers WHERE question_id = ?", (question_id,)).fetchone()
    item = _dict(row)
    if item:
        item["hits"] = decode_json(item.pop("hits_json", "[]"), [])
        item["evidence"] = decode_json(item.pop("evidence_json", "[]"), [])
        item["needs_review"] = bool(item.get("needs_review"))
    return item


def list_exam_answers(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT a.* FROM exam_answers a JOIN exam_questions q ON q.id = a.question_id "
            "WHERE q.session_id = ? ORDER BY q.order_index",
            (session_id,),
        ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["hits"] = decode_json(item.pop("hits_json", "[]"), [])
        item["evidence"] = decode_json(item.pop("evidence_json", "[]"), [])
        item["needs_review"] = bool(item.get("needs_review"))
    return items


def exam_scores_by_tag(session_id: str) -> dict[str, float]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT q.tag_id AS tag_id, SUM(COALESCE(a.score, 0)) AS got, SUM(COALESCE(a.max_score, 10)) AS total "
            "FROM exam_questions q LEFT JOIN exam_answers a ON a.question_id = q.id "
            "WHERE q.session_id = ? GROUP BY q.tag_id",
            (session_id,),
        ).fetchall()
    return {row["tag_id"]: (float(row["got"]) / float(row["total"])) if row["total"] else 0.0 for row in rows}


def create_submission(session_id: str, key: str, payload_hash: str) -> bool:
    """首次提交返回 True；重复提交返回 False（命中唯一约束）。"""
    try:
        with closing(connect()) as conn, conn:
            conn.execute(
                "INSERT INTO exam_submissions (id, session_id, idempotency_key, payload_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_id("sb_"), session_id, key, payload_hash, now()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_submission(session_id: str, key: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM exam_submissions WHERE session_id = ? AND idempotency_key = ?", (session_id, key)
        ).fetchone()
    return _dict(row)


# --------------------------------------------------------------------------- #
# weak points / interview
# --------------------------------------------------------------------------- #
def save_weak_points(session_id: str, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM weak_points WHERE session_id = ?", (session_id,))
        for item in points:
            conn.execute(
                "INSERT INTO weak_points (id, session_id, tag_id, severity, reason, evidence_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("wp_"),
                    session_id,
                    item["tag_id"],
                    float(item.get("severity") or 0.0),
                    item.get("reason") or "",
                    encode_json(item.get("evidence") or []),
                    now(),
                ),
            )
    return list_weak_points(session_id)


def list_weak_points(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT w.*, t.name AS tag FROM weak_points w JOIN knowledge_tags t ON t.id = w.tag_id "
            "WHERE w.session_id = ? ORDER BY w.severity DESC",
            (session_id,),
        ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["evidence"] = decode_json(item.pop("evidence_json", "[]"), [])
    return items


def add_interview_turn(
    session_id: str,
    tag_id: str,
    round_index: int,
    question: str,
    *,
    weak_point_id: str | None = None,
    follow_up_of: str | None = None,
    rubric: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    turn_id = new_id("it_")
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO interview_turns (id, session_id, weak_point_id, tag_id, round_index, question, rubric_json, "
            "follow_up_of, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'asking', ?)",
            (turn_id, session_id, weak_point_id, tag_id, round_index, question, encode_json(rubric or []), follow_up_of, now()),
        )
    return get_interview_turn(turn_id) or {}


def get_interview_turn(turn_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM interview_turns WHERE id = ?", (turn_id,)).fetchone()
    item = _dict(row)
    if item:
        item["rubric"] = decode_json(item.pop("rubric_json", "[]"), [])
    return item


def latest_interview_turn(session_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM interview_turns WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    item = _dict(row)
    if item:
        item["rubric"] = decode_json(item.pop("rubric_json", "[]"), [])
    return item


def save_interview_answer(turn_id: str, answer: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE interview_turns SET answer = ?, status = 'answered', answered_at = ? WHERE id = ?",
            (answer, now(), turn_id),
        )


def save_interview_grade(turn_id: str, score: float, evidence: list[dict[str, Any]]) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE interview_turns SET score = ?, evidence_json = ?, status = 'graded' WHERE id = ?",
            (score, encode_json(evidence), turn_id),
        )


def list_interview_turns(session_id: str) -> list[dict[str, Any]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT t.*, k.name AS tag FROM interview_turns t JOIN knowledge_tags k ON k.id = t.tag_id "
            "WHERE t.session_id = ? ORDER BY t.round_index, t.created_at",
            (session_id,),
        ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["rubric"] = decode_json(item.pop("rubric_json", "[]"), [])
        item["evidence"] = decode_json(item.pop("evidence_json", "[]"), [])
    return items


def interview_scores_by_tag(session_id: str) -> dict[str, float]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT tag_id, AVG(score) AS avg_score FROM interview_turns "
            "WHERE session_id = ? AND score IS NOT NULL GROUP BY tag_id",
            (session_id,),
        ).fetchall()
    return {row["tag_id"]: float(row["avg_score"] or 0) / 10.0 for row in rows}


# --------------------------------------------------------------------------- #
# reports / llm_calls
# --------------------------------------------------------------------------- #
def save_report(session_id: str, report: dict[str, Any]) -> dict[str, Any]:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO reports (id, session_id, summary, passed, level, capabilities_json, tag_scores_json, "
            "strengths_json, weaknesses_json, actions_json, next_json, evidence_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET summary = excluded.summary, passed = excluded.passed, "
            "level = excluded.level, capabilities_json = excluded.capabilities_json, "
            "tag_scores_json = excluded.tag_scores_json, strengths_json = excluded.strengths_json, "
            "weaknesses_json = excluded.weaknesses_json, actions_json = excluded.actions_json, "
            "next_json = excluded.next_json, evidence_json = excluded.evidence_json, created_at = excluded.created_at",
            (
                new_id("rp_"),
                session_id,
                report.get("summary") or "",
                1 if report.get("passed") else 0,
                report.get("level"),
                encode_json(report.get("capabilities") or []),
                encode_json(report.get("tags") or []),
                encode_json(report.get("strengths") or []),
                encode_json(report.get("weaknesses") or []),
                encode_json(report.get("actions") or []),
                encode_json(report.get("next") or []),
                encode_json(report.get("evidence") or []),
                now(),
            ),
        )
    return get_report(session_id) or {}


def get_report(session_id: str) -> dict[str, Any] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM reports WHERE session_id = ?", (session_id,)).fetchone()
    item = _dict(row)
    if not item:
        return None
    item["passed"] = bool(item.get("passed"))
    item["capabilities"] = decode_json(item.pop("capabilities_json", "[]"), [])
    item["tags"] = decode_json(item.pop("tag_scores_json", "[]"), [])
    item["strengths"] = decode_json(item.pop("strengths_json", "[]"), [])
    item["weaknesses"] = decode_json(item.pop("weaknesses_json", "[]"), [])
    item["actions"] = decode_json(item.pop("actions_json", "[]"), [])
    item["next"] = decode_json(item.pop("next_json", "[]"), [])
    item["evidence"] = decode_json(item.pop("evidence_json", "[]"), [])
    return item


def log_llm_call(
    session_id: str | None,
    task: str,
    mode: str,
    *,
    provider: str = "deepseek",
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "ok",
    input_hash: str | None = None,
) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO llm_calls (id, session_id, task, mode, provider, model, prompt_tokens, completion_tokens, "
            "latency_ms, status, input_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("lc_"),
                session_id,
                task,
                mode,
                provider,
                model,
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                int(latency_ms or 0),
                status,
                input_hash,
                now(),
            ),
        )


def session_cost(session_id: str) -> dict[str, int]:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens), 0) AS prompt, "
            "COALESCE(SUM(completion_tokens), 0) AS completion, COALESCE(SUM(latency_ms), 0) AS latency "
            "FROM llm_calls WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return {
        "calls": int(row["calls"]),
        "prompt_tokens": int(row["prompt"]),
        "completion_tokens": int(row["completion"]),
        "latency_ms": int(row["latency"]),
    }
