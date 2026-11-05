from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

DEFAULT_TITLE = "新对话"
CONVERSATIONS_FILE = config.DATA_DIR / "conversations.json"
DOCUMENTS_FILE = config.DATA_DIR / "documents.json"

_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _read(path: Path, key: str) -> dict[str, list[Any]]:
    if not path.exists():
        return {key: []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {key: []}
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        return {key: []}
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _plain(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[#>*_`~]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _preview(text: str, limit: int = 80) -> str:
    plain = _plain(text)
    return plain[:limit] + ("…" if len(plain) > limit else "")


def _title_from(text: str) -> str:
    plain = _plain(text)
    if not plain:
        return DEFAULT_TITLE
    return plain[:28] + ("…" if len(plain) > 28 else "")


# --------------------------------------------------------------------------- #
# conversations
# --------------------------------------------------------------------------- #
def list_conversations() -> list[dict[str, Any]]:
    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
    items: list[dict[str, Any]] = []
    for conversation in data["conversations"]:
        messages = conversation.get("messages", [])
        preview = ""
        for message in reversed(messages):
            if message.get("role") == "assistant" and message.get("content"):
                preview = _preview(message["content"])
                break
        if not preview and messages:
            preview = _preview(messages[-1].get("content", ""))
        items.append(
            {
                "id": conversation["id"],
                "title": conversation.get("title") or DEFAULT_TITLE,
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at"),
                "message_count": len(messages),
                "preview": preview,
            }
        )
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def create_conversation(title: str | None = None) -> dict[str, Any]:
    now = _now()
    conversation = {
        "id": _new_id(),
        "title": (title or "").strip()[:60] or DEFAULT_TITLE,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
        data["conversations"].insert(0, conversation)
        _write(CONVERSATIONS_FILE, data)
    return json.loads(json.dumps(conversation))


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
    for conversation in data["conversations"]:
        if conversation.get("id") == conversation_id:
            return json.loads(json.dumps(conversation))
    return None


def rename_conversation(conversation_id: str, title: str) -> dict[str, Any] | None:
    now = _now()
    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
        for conversation in data["conversations"]:
            if conversation.get("id") == conversation_id:
                conversation["title"] = title.strip()[:60] or DEFAULT_TITLE
                conversation["updated_at"] = now
                _write(CONVERSATIONS_FILE, data)
                return json.loads(json.dumps(conversation))
    return None


def delete_conversation(conversation_id: str) -> bool:
    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
        remaining = [c for c in data["conversations"] if c.get("id") != conversation_id]
        if len(remaining) == len(data["conversations"]):
            return False
        data["conversations"] = remaining
        _write(CONVERSATIONS_FILE, data)
    return True


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str] | None:
    now = _now()
    message: dict[str, Any] = {
        "id": _new_id(),
        "role": role,
        "content": content,
        "created_at": now,
    }
    if sources is not None:
        message["sources"] = sources
    if trace is not None:
        message["trace"] = trace

    with _lock:
        data = _read(CONVERSATIONS_FILE, "conversations")
        for conversation in data["conversations"]:
            if conversation.get("id") != conversation_id:
                continue
            if role == "user" and conversation.get("title") in (None, "", DEFAULT_TITLE):
                conversation["title"] = _title_from(content)
            conversation.setdefault("messages", []).append(message)
            conversation["updated_at"] = now
            _write(CONVERSATIONS_FILE, data)
            return json.loads(json.dumps(message)), conversation["title"]
    return None


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #
def _stored_char_count(document: dict[str, Any]) -> int:
    value = document.get("char_count")
    if isinstance(value, int):
        return value
    return sum(len(chunk.get("text", "")) for chunk in document.get("chunks", []))


def _document_summary(document: dict[str, Any]) -> dict[str, Any]:
    chunks = document.get("chunks", [])
    return {
        "id": document["id"],
        "name": document["name"],
        "stored_name": document["stored_name"],
        "size": document.get("size", 0),
        "chunk_count": len(chunks),
        "char_count": _stored_char_count(document),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def list_documents(origin: str | None = "chat") -> list[dict[str, Any]]:
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
    if origin is not None:
        data = {
            "documents": [
                document
                for document in data["documents"]
                if (document.get("origin") or "chat") == origin
            ]
        }
    documents = [_document_summary(document) for document in data["documents"]]
    documents.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return documents


def get_document(document_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
    for document in data["documents"]:
        if document.get("id") == document_id:
            return json.loads(json.dumps(document))
    return None


def add_document(
    name: str,
    stored_name: str,
    size: int,
    chunks: list[dict[str, Any]],
    char_count: int | None = None,
    origin: str = "chat",
) -> dict[str, Any]:
    now = _now()
    document_id = _new_id()
    document = {
        "id": document_id,
        "name": name,
        "stored_name": stored_name,
        "size": size,
        "origin": origin,
        "char_count": int(char_count) if char_count is not None else sum(
            len(chunk.get("text", "")) for chunk in chunks
        ),
        "created_at": now,
        "updated_at": now,
        "chunks": [
            {
                "id": f"{document_id}-{index}",
                "index": index,
                "text": chunk["text"],
            }
            for index, chunk in enumerate(chunks)
        ],
    }
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
        data["documents"].insert(0, document)
        _write(DOCUMENTS_FILE, data)
    return _document_summary(document)


def delete_document(document_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
        target = next((d for d in data["documents"] if d.get("id") == document_id), None)
        if target is None:
            return None
        data["documents"] = [d for d in data["documents"] if d.get("id") != document_id]
        _write(DOCUMENTS_FILE, data)
    return json.loads(json.dumps(target))


def all_chunks(origin: str | None = "chat") -> list[dict[str, Any]]:
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
    chunks: list[dict[str, Any]] = []
    for document in data["documents"]:
        if origin is not None and (document.get("origin") or "chat") != origin:
            continue
        for chunk in document.get("chunks", []):
            chunks.append(
                {
                    "document_id": document["id"],
                    "document_name": document["name"],
                    "chunk_id": chunk["id"],
                    "chunk_index": chunk["index"],
                    "text": chunk["text"],
                }
            )
    return chunks


def stats(origin: str | None = "chat") -> dict[str, int]:
    with _lock:
        data = _read(DOCUMENTS_FILE, "documents")
    documents = [
        document
        for document in data["documents"]
        if origin is None or (document.get("origin") or "chat") == origin
    ]
    return {
        "documents": len(documents),
        "chunks": sum(len(document.get("chunks", [])) for document in documents),
        "characters": sum(_stored_char_count(document) for document in documents),
    }
