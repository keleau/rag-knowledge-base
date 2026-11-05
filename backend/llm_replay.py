from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import config


class ReplayMiss(RuntimeError):
    def __init__(self, task: str, key: str) -> None:
        super().__init__(f"replay 缺少录制数据：task={task} key={key}")
        self.task = task
        self.key = key


def fixture_key(task_name: str, model: str, messages: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        {"task": task_name, "model": model, "messages": messages},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def fixture_path(task_name: str, key: str) -> Path:
    return config.FIXTURE_DIR / task_name / f"{key}.json"


def load(task_name: str, key: str) -> dict[str, Any] | None:
    path = fixture_path(task_name, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(task_name: str, key: str, payload: dict[str, Any]) -> None:
    path = fixture_path(task_name, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
