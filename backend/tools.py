from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import config
import rag
import storage

TOOL_LABELS = {
    "search_knowledge": "检索知识库",
    "list_documents": "查看文档列表",
    "get_document_chunks": "读取文档分块",
}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "在本地知识库中检索与问题相关的片段，返回命中的文档、分块和相似度。"
                "适合事实性问题。结果为空或不相关时，可以改写 query 再检索一次；不要重复完全相同的调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于检索的简短查询，保留关键名词，不要带寒暄。",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回片段数，默认 4，最多 6。",
                        "minimum": 1,
                        "maximum": 6,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": (
                "列出知识库中的文档及分块数。需要知道有哪些文档、做跨文档对比，"
                "或检索结果不足时使用。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_chunks",
            "description": (
                "按 document_id 读取一篇文档的全部分块。适合总结整篇文档、对比两份文档，"
                "或在检索结果不足时补充上下文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "list_documents 返回的文档 id。",
                    }
                },
                "required": ["document_id"],
            },
        },
    },
]

TOOL_NAMES = {spec["function"]["name"] for spec in TOOL_SPECS}
MAX_CHUNK_CHARS = 600
MAX_DOC_CHUNKS = 8


def _clip(text: Any, limit: int = MAX_CHUNK_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def search_knowledge(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    chunks = storage.all_chunks(origin="chat")
    if not chunks:
        return []
    return rag.search(query, max(1, min(int(top_k), 6)), documents=chunks)


def list_documents() -> list[dict[str, Any]]:
    # 只列聊天知识库的文档；评估用的简历/项目文档通过测评工具访问，不暴露给问答 Agent
    return [
        {
            "id": document["id"],
            "name": document["name"],
            "chunk_count": document["chunk_count"],
            "char_count": document["char_count"],
        }
        for document in storage.list_documents(origin="chat")
    ]


def get_document_chunks(document_id: str) -> dict[str, Any]:
    document = storage.get_document(document_id)
    if document is None:
        raise ValueError(f"没有找到文档：{document_id}")
    chunks = document.get("chunks", [])
    return {
        "document_id": document["id"],
        "document_name": document["name"],
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": chunk["id"],
                "chunk_index": chunk["index"],
                "text": chunk["text"],
            }
            for chunk in chunks
        ],
    }


def _run_sync(name: str, arguments: dict[str, Any]) -> Any:
    if name == "search_knowledge":
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query 不能为空")
        raw_top_k = arguments.get("top_k", config.TOP_K)
        try:
            top_k = int(raw_top_k)
        except (TypeError, ValueError):
            top_k = config.TOP_K
        return search_knowledge(query, top_k)
    if name == "list_documents":
        return list_documents()
    if name == "get_document_chunks":
        document_id = str(arguments.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id 不能为空")
        return get_document_chunks(document_id)
    raise ValueError(f"未知工具：{name}")


async def execute(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    name = (name or "").strip()
    arguments = arguments if isinstance(arguments, dict) else {}
    started = time.perf_counter()
    if name not in TOOL_NAMES:
        return {
            "ok": False,
            "name": name,
            "error": f"未知工具：{name}",
            "duration_ms": 0,
        }
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_sync, name, arguments),
            timeout=float(config.AGENT_TOOL_TIMEOUT),
        )
        return {
            "ok": True,
            "name": name,
            "result": result,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "name": name,
            "error": f"工具执行超过 {config.AGENT_TOOL_TIMEOUT} 秒",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "error": str(exc)[:240] or "工具执行失败",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }


def observation(name: str, arguments: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    if not execution.get("ok"):
        return {
            "tool": name,
            "ok": False,
            "error": execution.get("error") or "工具执行失败",
        }

    result = execution.get("result")
    if name == "search_knowledge":
        items = result if isinstance(result, list) else []
        return {
            "tool": name,
            "ok": True,
            "query": arguments.get("query"),
            "count": len(items),
            "results": [
                {
                    "document": item.get("document_name"),
                    "chunk_index": item.get("chunk_index"),
                    "score": item.get("score"),
                    "text": _clip(item.get("text")),
                }
                for item in items[:6]
            ],
        }
    if name == "list_documents":
        items = result if isinstance(result, list) else []
        return {
            "tool": name,
            "ok": True,
            "count": len(items),
            "documents": items[:12],
        }
    if name == "get_document_chunks":
        payload = result if isinstance(result, dict) else {}
        chunks = payload.get("chunks") or []
        return {
            "tool": name,
            "ok": True,
            "document_id": payload.get("document_id"),
            "document": payload.get("document_name"),
            "chunk_count": payload.get("chunk_count", len(chunks)),
            "chunks": [
                {
                    "chunk_index": chunk.get("chunk_index"),
                    "text": _clip(chunk.get("text")),
                }
                for chunk in chunks[:MAX_DOC_CHUNKS]
            ],
        }
    return {"tool": name, "ok": True, "result": result}


def observation_text(name: str, arguments: dict[str, Any], execution: dict[str, Any]) -> str:
    payload = observation(name, arguments, execution)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= 6000:
        return text
    return text[:6000] + "…"
