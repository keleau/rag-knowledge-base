from __future__ import annotations

import logging
import re
import threading
from typing import Any

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
import storage

jieba.setLogLevel(logging.WARNING)

_cache_lock = threading.RLock()
_cache: dict[str, Any] = {
    "mtime": None,
    "vectorizer": None,
    "matrix": None,
    "chunks": [],
}


def significant_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in jieba.lcut(text):
        token = token.strip().lower()
        if not token:
            continue
        if any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in token):
            tokens.append(token)
    return tokens


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[dict[str, Any]]:
    chunk_size = max(100, chunk_size or config.CHUNK_SIZE)
    overlap = max(0, min(overlap if overlap is not None else config.CHUNK_OVERLAP, chunk_size // 2))
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\u3000]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return []

    step = max(1, chunk_size - overlap)
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(normalized):
        piece = normalized[start : start + chunk_size].strip()
        if piece:
            chunks.append({"text": piece})
        start += step
    return chunks


def invalidate_index() -> None:
    with _cache_lock:
        _cache["mtime"] = None


def _documents_mtime() -> int:
    try:
        return storage.DOCUMENTS_FILE.stat().st_mtime_ns
    except OSError:
        return 0


def _get_index() -> tuple[Any, Any, list[dict[str, Any]]]:
    mtime = _documents_mtime()
    if _cache["mtime"] == mtime and _cache["chunks"]:
        return _cache["vectorizer"], _cache["matrix"], _cache["chunks"]

    with _cache_lock:
        mtime = _documents_mtime()
        if _cache["mtime"] == mtime and _cache["chunks"]:
            return _cache["vectorizer"], _cache["matrix"], _cache["chunks"]

        chunks = storage.all_chunks()
        if not chunks:
            _cache.update({"mtime": mtime, "vectorizer": None, "matrix": None, "chunks": []})
            return None, None, []

        texts = [chunk["text"] for chunk in chunks]
        vectorizer = TfidfVectorizer(
            tokenizer=significant_tokens,
            token_pattern=None,
            lowercase=False,
            sublinear_tf=True,
        )
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            # 历史数据里可能只有标点；退化为字符匹配，避免问答接口 500。
            vectorizer = None
            matrix = None
        _cache.update(
            {"mtime": mtime, "vectorizer": vectorizer, "matrix": matrix, "chunks": chunks}
        )
        return vectorizer, matrix, chunks


def _fallback_search(query: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    compact_query = re.sub(r"\s+", "", query)
    query_grams = {compact_query[i : i + 2] for i in range(max(1, len(compact_query) - 1))}
    if not query_grams:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        compact_text = re.sub(r"\s+", "", chunk["text"])
        text_grams = {compact_text[i : i + 2] for i in range(max(1, len(compact_text) - 1))}
        overlap = len(query_grams & text_grams)
        if overlap:
            score = overlap / len(query_grams)
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "document_id": chunk["document_id"],
            "document_name": chunk["document_name"],
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
            "score": round(float(score), 4),
        }
        for score, chunk in scored[:top_k]
    ]


def _rank_with_vectorizer(chunks: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
    if not chunks:
        return []
    texts = [chunk["text"] for chunk in chunks]
    try:
        vectorizer = TfidfVectorizer(
            tokenizer=significant_tokens,
            token_pattern=None,
            lowercase=False,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
        scores = cosine_similarity(vectorizer.transform([query]), matrix).ravel()
    except ValueError:
        return _fallback_search(query, chunks, top_k)

    order = np.argsort(scores)[::-1][:top_k]
    results = [
        {
            "document_id": chunks[index]["document_id"],
            "document_name": chunks[index]["document_name"],
            "chunk_id": chunks[index]["chunk_id"],
            "chunk_index": chunks[index]["chunk_index"],
            "text": chunks[index]["text"],
            "score": round(float(scores[index]), 4),
        }
        for index in order
        if float(scores[index]) > 0
    ]
    if results:
        cutoff = max(0.01, results[0]["score"] * 0.2)
        return [item for item in results if item["score"] >= cutoff]
    return _fallback_search(query, chunks, top_k)


def search(query: str, top_k: int | None = None, documents: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    top_k = max(1, min(top_k or config.TOP_K, 10))

    if documents is not None:
        # 评估模块只在自己项目的分块里检索，不碰聊天知识库索引
        return _rank_with_vectorizer(documents, query, top_k)

    vectorizer, matrix, chunks = _get_index()
    if not chunks:
        return []

    scores: np.ndarray | None = None
    if vectorizer is not None and matrix is not None:
        try:
            query_vector = vectorizer.transform([query])
            scores = cosine_similarity(query_vector, matrix).ravel()
        except ValueError:
            scores = None

    if scores is not None:
        order = np.argsort(scores)[::-1][:top_k]
        results = [
            {
                "document_id": chunks[index]["document_id"],
                "document_name": chunks[index]["document_name"],
                "chunk_id": chunks[index]["chunk_id"],
                "chunk_index": chunks[index]["chunk_index"],
                "text": chunks[index]["text"],
                "score": round(float(scores[index]), 4),
            }
            for index in order
            if float(scores[index]) > 0
        ]
        if results:
            top_score = results[0]["score"]
            cutoff = max(0.01, top_score * 0.2)
            return [item for item in results if item["score"] >= cutoff]

    return _fallback_search(query, chunks, top_k)
