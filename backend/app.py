from __future__ import annotations

import asyncio
import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import config
import agent
import assessment_app
import llm
import parsers
import rag
import storage

app = FastAPI(
    title="知问 · 检索 Agent 知识库问答",
    version="1.0.0",
    description="上传文档，建立本地向量索引，基于 DeepSeek 的流式知识库问答。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessment_app.router)
app.include_router(assessment_app.misc_router)


class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    top_k: int | None = Field(default=None, ge=1, le=10)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=60)


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=60)


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    data = {key: value for key, value in document.items() if key != "stored_name"}
    if "chunks" in data:
        data["chunk_count"] = len(data["chunks"])
        data.setdefault(
            "char_count",
            sum(len(chunk.get("text", "")) for chunk in data["chunks"]),
        )
    return data


def _normalize_filename(raw: str) -> str:
    name = raw.replace("\\", "/").split("/")[-1].strip()
    # Starlette 按 latin-1 解码 multipart 头部，浏览器实际发送的是 UTF-8 字节。
    try:
        repaired = name.encode("latin-1").decode("utf-8")
        if repaired:
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return name


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": "知问 · 检索 Agent 知识库问答",
        "demo_mode": config.DEMO_MODE,
        "llm_mode": config.LLM_MODE,
        "model": config.DEEPSEEK_MODEL,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "top_k": config.TOP_K,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "agent_max_steps": config.AGENT_MAX_STEPS,
        "agent_max_contexts": config.AGENT_MAX_CONTEXTS,
        **storage.stats(),
    }


# --------------------------------------------------------------------------- #
# conversations
# --------------------------------------------------------------------------- #
@app.get("/api/conversations")
def list_conversations() -> dict[str, Any]:
    return {"conversations": storage.list_conversations()}


@app.post("/api/conversations", status_code=201)
def create_conversation(payload: ConversationCreate | None = None) -> dict[str, Any]:
    return storage.create_conversation(payload.title if payload else None)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRename) -> dict[str, Any]:
    conversation = storage.rename_conversation(conversation_id, payload.title)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"id": conversation["id"], "title": conversation["title"], "updated_at": conversation["updated_at"]}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    if not storage.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #
@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    return {"documents": [_public_document(item) for item in storage.list_documents()]}


@app.get("/api/documents/{document_id}")
def get_document(document_id: str) -> dict[str, Any]:
    document = storage.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _public_document(document)


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    raw_name = _normalize_filename(file.filename or "")
    if not raw_name:
        raise HTTPException(status_code=400, detail="缺少文件名")
    extension = Path(raw_name).suffix.lower()
    if extension not in parsers.SUPPORTED_EXTENSIONS:
        supported = " / ".join(sorted(parsers.SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"暂不支持 {extension or '该'} 格式，请上传 {supported}")

    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 限制",
        )
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")

    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored_path = config.UPLOAD_DIR / stored_name
    await run_in_threadpool(stored_path.write_bytes, data)

    try:
        text = await run_in_threadpool(parsers.extract_text, stored_path)
        if not rag.significant_tokens(text):
            raise parsers.ParseError("文档中没有可检索的文字内容")
        chunks = rag.chunk_text(text)
        if not chunks:
            raise parsers.ParseError("文档没有可入库的文本")
        document = storage.add_document(
            name=raw_name,
            stored_name=stored_name,
            size=len(data),
            chunks=chunks,
            char_count=len(text),
        )
    except parsers.ParseError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        rag.invalidate_index()

    return _public_document(document)


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, bool]:
    document = storage.delete_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    path = (config.UPLOAD_DIR / document["stored_name"]).resolve()
    if path.parent == config.UPLOAD_DIR.resolve() and path.exists():
        path.unlink(missing_ok=True)
    rag.invalidate_index()
    return {"ok": True}


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: str) -> FileResponse:
    document = storage.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    path = (config.UPLOAD_DIR / document["stored_name"]).resolve()
    if path.parent != config.UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="文档文件已丢失")
    media_type = mimetypes.guess_type(document["name"])[0] or "application/octet-stream"
    return FileResponse(path, filename=document["name"], media_type=media_type)


# --------------------------------------------------------------------------- #
# chat (SSE)
# --------------------------------------------------------------------------- #
@app.post("/api/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: ChatRequest,
) -> StreamingResponse:
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    history = [
        {"role": message["role"], "content": message["content"]}
        for message in conversation.get("messages", [])[-10:]
        if message.get("role") in {"user", "assistant"} and message.get("content")
    ]

    if storage.add_message(conversation_id, "user", content) is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    runner = agent.AgentRunner(content, history, top_k=payload.top_k)

    async def event_stream():
        answer_parts: list[str] = []
        completed = False
        try:
            async for event, data in runner.run():
                if event == "step":
                    yield _sse("step", data)
                elif event == "sources":
                    yield _sse("sources", data)
                elif event == "delta":
                    piece = str(data.get("content") or "")
                    if piece:
                        answer_parts.append(piece)
                        yield _sse("delta", {"content": piece})

            answer = runner.answer.strip()
            if not answer:
                raise llm.LLMError("模型没有返回内容，请重试")

            saved = storage.add_message(
                conversation_id,
                "assistant",
                answer,
                runner.contexts,
                runner.trace,
            )
            if saved is None:
                raise llm.LLMError("会话已被删除，回答未能保存")
            message, title = saved
            completed = True
            yield _sse(
                "done",
                {
                    "conversation_id": conversation_id,
                    "message_id": message["id"],
                    "title": title,
                    "content": answer,
                    "trace": runner.trace,
                    "usage": runner.usage,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield _sse("error", {"message": str(exc) or "生成失败，请重试"})
        finally:
            if not completed:
                partial = "".join(answer_parts).strip()
                if partial:
                    storage.add_message(
                        conversation_id,
                        "assistant",
                        f"{partial}\n\n（生成中断，以上为已生成内容）",
                        runner.contexts,
                        runner.trace,
                    )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# --------------------------------------------------------------------------- #
# frontend build (production)
# --------------------------------------------------------------------------- #
dist = config.FRONTEND_DIST
if (dist / "index.html").exists() and (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            return FileResponse(dist / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")

else:

    @app.get("/", include_in_schema=False)
    def dev_root() -> JSONResponse:
        return JSONResponse(
            {
                "message": "后端已启动。前端请运行 npm run dev（端口 5173），或先执行 npm run build。",
                "docs": "/docs",
                "demo_mode": config.DEMO_MODE,
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
