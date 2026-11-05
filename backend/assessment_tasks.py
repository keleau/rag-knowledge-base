from __future__ import annotations

import json
import re
from contextlib import closing
from typing import Any, Awaitable, Callable

import assessment_storage as store
import code_parser
import config
import entities as entity_lib
import llm
import memory_context
import pii
import question_guard
import rag

DEFAULT_TAGS = [
    {"name": "组件设计", "description": "组件拆分、复用、props/emits、插槽"},
    {"name": "状态管理", "description": "响应式、computed/watch、跨组件状态"},
    {"name": "接口与数据流", "description": "请求、loading、错误、缓存、分页"},
    {"name": "异常与边界", "description": "空态、错误态、超时、重试、兜底"},
    {"name": "性能优化", "description": "渲染、懒加载、防抖节流、分包"},
    {"name": "工程化", "description": "构建、类型、目录、环境变量、部署"},
]


class TaskError(RuntimeError):
    pass


Emitter = Callable[[str, dict[str, Any]], Awaitable[None]]


async def noop_emit(event: str, data: dict[str, Any]) -> None:  # pragma: no cover - 默认实现
    return None


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _clip(text: Any, limit: int = 1200) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[:limit] + "…"


def _doc_chunks(session: dict[str, Any]) -> list[dict[str, Any]]:
    document_id = session.get("project_document_id")
    if not document_id:
        return []
    import storage

    document = storage.get_document(document_id)
    if not document:
        return []
    return [
        {
            "document_id": document["id"],
            "document_name": document["name"],
            "chunk_id": chunk["id"],
            "chunk_index": chunk["index"],
            "text": chunk["text"],
        }
        for chunk in document.get("chunks", [])
    ]


def _code(session_id: str) -> dict[str, Any] | None:
    return store.get_code(session_id)


def _entity_names(session_id: str) -> set[str]:
    return {item["name"] for item in store.list_entities(session_id)}


def _symbol_names(session_id: str) -> set[str]:
    code = _code(session_id)
    if not code:
        return set()
    return {item.get("name") for item in code.get("symbols") or [] if item.get("name")}


def _tag_maps(session_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    tags = store.list_tags(session_id)
    return {tag["name"]: tag for tag in tags}, {tag["id"]: tag for tag in tags}


def _evidence_context(tags: list[dict[str, Any]], chunks: list[dict[str, Any]], top_k: int = 4) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        query = f"{tag['name']} {tag.get('description') or ''}"
        for item in rag.search(query, top_k=top_k, documents=chunks):
            if item.get("chunk_id") in seen:
                continue
            seen.add(item.get("chunk_id"))
            lines.append(f"【{item.get('document_name')}】{_clip(item.get('text'), 600)}")
    return "\n".join(lines[:8])


# --------------------------------------------------------------------------- #
# 1. 项目提取
# --------------------------------------------------------------------------- #
async def extract_projects(session_id: str, resume_text: str, emit: Emitter = noop_emit) -> list[dict[str, Any]]:
    masked = pii.mask(resume_text)
    user = (
        "从下面的【简历文本】中提取项目经历。不要编造简历里没有的项目。\n\n"
        f"【简历文本】\n{_clip(masked, 6000)}\n\n"
        '输出 JSON：{"projects":[{"name":"项目名","role":"担任角色或 null","period":"时间或 null",'
        '"summary":"一句话概括","source_quote":"简历中逐字出现的原句"}]}\n'
        "规则：\n1. 每个项目必须有 source_quote，且逐字出自简历。\n2. 信息缺失填 null，不要猜。\n3. 最多 6 个项目，按简历顺序。"
    )
    await emit("step", {"label": "提取项目", "summary": "已脱敏简历，正在调用模型", "status": "done"})
    try:
        data = await llm.json_completion("extract_projects", "你是简历解析助手。", user, session_id=session_id)
    except Exception as exc:
        raise TaskError(f"项目提取失败：{exc}") from exc

    projects: list[dict[str, Any]] = []
    for item in data.get("projects") or []:
        name = str(item.get("name") or "").strip()
        quote = str(item.get("source_quote") or "").strip()
        if not name or not quote:
            continue
        if question_guard.normalized_text(quote) not in question_guard.normalized_text(masked):
            continue
        projects.append(
            {
                "name": name[:80],
                "role": item.get("role"),
                "period": item.get("period"),
                "summary": str(item.get("summary") or "")[:200],
                "source_quote": quote[:300],
            }
        )
    if not projects:
        raise TaskError("没有提取到项目；请确认简历里有项目经历，或手动添加")
    saved = store.replace_projects(session_id, projects[:6])
    await emit("done", {"projects": saved})
    return saved


# --------------------------------------------------------------------------- #
# 2. 标签 + 实体 + 能力目标
# --------------------------------------------------------------------------- #
async def prepare(session_id: str, emit: Emitter = noop_emit) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    project = store.selected_project(session_id)
    if not project:
        raise TaskError("请先选择一个项目")
    chunks = _doc_chunks(session)
    if len(chunks) < 5:
        raise TaskError("项目文档至少需要 5 个分块，请补充更完整的项目介绍")

    doc_text = "\n\n".join(chunk["text"] for chunk in chunks)
    await emit("step", {"label": "抽取项目实体", "summary": "从文档中识别项目名词与数字", "status": "done"})
    doc_entities = entity_lib.extract_entities(doc_text, limit=40)
    store.save_entities(session_id, doc_entities, source_type="project_doc")

    code = _code(session_id)
    if code:
        code_symbols = code.get("symbols") or []
        code_entities = [
            {"name": item["name"], "kind": item.get("kind") if item.get("kind") in {"component", "api", "function", "metric", "term"} else "term"}
            for item in code_symbols[:30]
        ]
        store.save_entities(session_id, code_entities, source_type="code")
    else:
        # 代码被移除后，旧符号不能再当作实体用
        store.clear_entities(session_id, source_type="code")

    await emit("step", {"label": "生成知识标签", "summary": f"{len(doc_entities)} 个实体", "status": "done"})
    tags = await _generate_tags(session_id, project, chunks)
    await emit("step", {"label": "能力目标", "summary": f"{len(tags)} 条能力", "status": "done"})
    capabilities = await _generate_capabilities(session_id, project, chunks, tags)
    items = await generate_practice(session_id, emit)
    await emit("done", {"tags": tags, "capabilities": capabilities, "practice_count": len(items)})
    return {"tags": tags, "capabilities": capabilities, "practice": items}


async def _generate_tags(session_id: str, project: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context = "\n\n".join(_clip(chunk["text"], 800) for chunk in chunks[:6])
    user = (
        f"项目名称：{project['name']}\n项目简介：{project.get('summary') or ''}\n\n"
        f"【项目文档】\n{context}\n\n"
        '输出 JSON：{"tags":[{"name":"标签名","description":"这个项目里具体指什么"}]}\n'
        "规则：标签名不超过 8 个字；描述必须包含项目里的具体名词；禁止“其他/综合/技术”这类空标签；生成 5–6 个。"
    )
    try:
        data = await llm.json_completion("generate_tags", "你是项目知识梳理助手。", user, session_id=session_id, temperature=0.3)
        tags = [
            {"name": str(item["name"]).strip()[:12], "description": str(item.get("description") or "")[:120]}
            for item in data.get("tags") or []
            if str(item.get("name") or "").strip() and str(item["name"]).strip() not in {"其他", "综合", "技术"}
        ]
        tags = tags[:6]
    except Exception:
        tags = []
    if len(tags) < 4:
        tags = [dict(item) for item in DEFAULT_TAGS]
    return store.save_tags(session_id, tags)


async def _generate_capabilities(
    session_id: str, project: dict[str, Any], chunks: list[dict[str, Any]], tags: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    context = "\n\n".join(_clip(chunk["text"], 800) for chunk in chunks[:6])
    user = (
        f"项目名称：{project['name']}\n\n【标签】{_json([tag['name'] for tag in tags])}\n\n"
        f"【项目文档】\n{context}\n\n"
        '输出 JSON：{"capabilities":[{"tag":"标签名","target_level":"L1|L2|L3|L4",'
        '"acceptance":["可验证的句子1","可验证的句子2"],"evidence_quote":"项目文档原句"}]}\n'
        "规则：每个标签一条；核心标签 L3，支撑性 L2，边缘 L1，不要全部 L3；"
        "acceptance 必须具体可验证；evidence_quote 逐字出自项目文档。"
    )
    tag_lookup = {tag["name"]: tag for tag in tags}
    accepted: list[dict[str, Any]] = []
    try:
        data = await llm.json_completion("generate_capabilities", "你是面试官，正在为候选人制定项目毕业标准。", user, session_id=session_id, temperature=0.3)
        for item in data.get("capabilities") or []:
            tag = tag_lookup.get(str(item.get("tag") or "").strip())
            if not tag:
                continue
            level = str(item.get("target_level") or "L2").upper()
            acceptance = [str(value) for value in (item.get("acceptance") or []) if str(value).strip()][:3]
            if not acceptance:
                continue
            accepted.append(
                {
                    "tag_id": tag["id"],
                    "target_level": level if level in {"L1", "L2", "L3", "L4"} else "L2",
                    "acceptance": acceptance,
                    "evidence_quote": str(item.get("evidence_quote") or "")[:300],
                }
            )
    except Exception:
        accepted = []
    if len(accepted) < len(tags):
        existing = {item["tag_id"] for item in accepted}
        for index, tag in enumerate(tags):
            if tag["id"] in existing:
                continue
            accepted.append(
                {
                    "tag_id": tag["id"],
                    "target_level": "L3" if index < 2 else "L2",
                    "acceptance": [
                        f"能结合{tag['name']}说出项目里的具体做法",
                        f"能解释{tag['name']}上的取舍与边界",
                    ],
                    "evidence_quote": "",
                }
            )
    return store.save_capabilities(session_id, accepted)


# --------------------------------------------------------------------------- #
# 3. 练习生成（分批）
# --------------------------------------------------------------------------- #
async def generate_practice(session_id: str, emit: Emitter = noop_emit, *, cycle: int = 0) -> list[dict[str, Any]]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    tags = store.list_tags(session_id)
    chunks = _doc_chunks(session)
    if not tags or not chunks:
        raise TaskError("请先完成项目文档和标签生成")

    entity_names = _entity_names(session_id)
    symbol_names = _symbol_names(session_id)
    code = _code(session_id)
    code_content = code["content"] if code else None

    # 学习阶段重新生成时清空旧题（setuptag 重生成也会触发这里），避免重复累加
    existing_count = store.count_practice_items(session_id, cycle)
    if cycle == 0 and existing_count >= config.PRACTICE_MIN_TOTAL:
        await emit("step", {"label": "练习题已存在", "summary": f"已有 {existing_count} 道，跳过生成", "status": "done"})
        return store.list_practice_items(session_id, cycle)

    generated = existing_count
    guard_round = 0
    while generated < config.PRACTICE_MIN_TOTAL and guard_round < 6:
        guard_round += 1
        existing = [item["prompt"] for item in store.list_practice_items(session_id, cycle)]
        batch_tag_names = _pick_batch_tags(tags, existing)
        result = await _generate_batch(session_id, tags, batch_tag_names, chunks, existing, code, config.PRACTICE_BATCH_SIZE)
        accepted, rejected = _screen(
            result,
            chunks=chunks,
            code_content=code_content,
            entity_names=entity_names,
            symbol_names=symbol_names,
            tag_lookup=_tag_maps(session_id)[0],
            seen=existing,
            allow=("question", "code_question"),
        )
        if accepted:
            store.save_practice_items(session_id, accepted, cycle=cycle)
            generated += len(accepted)
        await emit(
            "step",
            {
                "label": f"练习题 第 {guard_round} 批",
                "summary": f"通过 {len(accepted)} 道，丢弃 {len(rejected)} 道；累计 {generated} 道",
                "status": "done",
                "rejected": rejected[:10],
            },
        )
        if not accepted and rejected:
            continue
    items = store.list_practice_items(session_id, cycle)
    if len(items) < config.PRACTICE_MIN_TOTAL:
        raise TaskError("练习题生成不足；请补充更具体的项目文档，或降低题量要求")
    await emit("done", {"count": len(items), "items": items})
    return items


def _pick_batch_tags(tags: list[dict[str, Any]], existing_prompts: list[str]) -> list[str]:
    """优先让题目少的标签出题（按标签名在已有题干里出现的次数粗略排序）。"""
    haystack = "\n".join(existing_prompts)
    ordered = sorted(tags, key=lambda tag: haystack.count(tag["name"]))
    return [tag["name"] for tag in ordered]


async def expand_practice(session_id: str, emit: Emitter = noop_emit, *, cycle: int = 0) -> list[dict[str, Any]]:
    """学习页“再来几道”：无论已有多少题，都再生成一批（6–8 道）。"""
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    tags = store.list_tags(session_id)
    chunks = _doc_chunks(session)
    if not tags or not chunks:
        raise TaskError("请先完成项目文档和标签生成")
    existing = store.list_practice_items(session_id, cycle)
    existing_count = len([item for item in existing if item["kind"] != "card"])
    if existing_count >= 60:
        raise TaskError("题目已经够多了（60 道），先完成已有的练习吧")
    remaining = config.PRACTICE_MIN_TOTAL - existing_count
    batch_size = max(3, min(config.PRACTICE_BATCH_SIZE, remaining if remaining > 0 else config.PRACTICE_BATCH_SIZE))

    result = await _generate_batch(
        session_id,
        tags,
        _pick_batch_tags(tags, [item["prompt"] for item in existing]),
        chunks,
        [item["prompt"] for item in existing],
        _code(session_id),
        batch_size,
    )
    accepted, rejected = _screen(
        result,
        chunks=chunks,
        code_content=(_code(session_id) or {}).get("content"),
        entity_names=_entity_names(session_id),
        symbol_names=_symbol_names(session_id),
        tag_lookup=_tag_maps(session_id)[0],
        seen=[item["prompt"] for item in existing],
        allow=("question", "code_question"),
    )
    if not accepted:
        reasons = "、".join(sorted({item["reason"] for item in rejected}))[:200]
        raise TaskError(f"补题全部未通过校验（{reasons or '无可用题目'}），请补充更具体的项目文档")
    store.save_practice_items(session_id, accepted, cycle=cycle)
    await emit("step", {"label": "补充练习", "summary": f"新增 {len(accepted)} 道，丢弃 {len(rejected)} 道", "status": "done"})
    items = store.list_practice_items(session_id, cycle)
    await emit("done", {"count": len(items)})
    return items


async def _generate_batch(
    session_id: str,
    tags: list[dict[str, Any]],
    tag_names: list[str],
    chunks: list[dict[str, Any]],
    existing: list[str],
    code: dict[str, Any] | None,
    batch_size: int,
) -> list[dict[str, Any]]:
    context = _evidence_context([tag for tag in tags if tag["name"] in tag_names], chunks)
    code_note = ""
    if code:
        code_note = (
            f"\n\n【代码文件】{code['file_name']}（{code['line_count']} 行）\n"
            f"【代码符号表】{_json([item['name'] for item in (code.get('symbols') or [])][:40])}\n"
            "如果标签属于组件设计/状态管理/接口与数据流，请优先出 code_question，"
            "并给出 file/line_start/line_end/quote/symbols。"
        )
    user = (
        f"本次只生成这些标签的练习题：{_json(tag_names)}\n本批总数：{batch_size}\n\n"
        f"【项目文档证据】\n{context}{code_note}\n\n"
        f"【已生成题目】（不得重复）\n{_json(existing[:40])}\n\n"
        '输出 JSON：{"items":[{"tag":"标签名","kind":"question|code_question","code_mode":"locate|explain|implement 或 null",'
        '"difficulty":"easy|medium|hard","prompt":"题目","answer":"参考答案","explanation":"考察点",'
        '"rubric":[{"kind":"symbol|behavior","point":"得分点","weight":2,"symbol":null}],'
        '"source":{"chunk_id":"...","quote":"原文","file":null,"line_start":null,"line_end":null,"symbols":[]}}]}\n'
        "规则：每个标签至少 1 道；题干必须包含项目实体；quote 必须逐字出自文档；"
        "实现题至少 1 条 symbol 类 rubric；不要出“什么是 Vue”这类通用题；同一标签换场景。"
    )
    try:
        data = await llm.json_completion("generate_practice", "你是项目学习助手，只依据用户项目出题。", user, session_id=session_id, temperature=0.3, max_tokens=3000)
    except Exception as exc:
        raise TaskError(f"出题失败：{exc}") from exc
    return [item for item in data.get("items") or [] if isinstance(item, dict)]


def _screen(
    raw_items: list[dict[str, Any]],
    *,
    chunks: list[dict[str, Any]],
    code_content: str | None,
    entity_names: set[str],
    symbol_names: set[str],
    tag_lookup: dict[str, dict[str, Any]],
    seen: list[str],
    allow: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    prompts = list(seen)
    index = 0
    for item in raw_items:
        tag = tag_lookup.get(str(item.get("tag") or "").strip())
        kind = item.get("kind") or "question"
        if not tag or kind not in allow:
            rejected.append({"prompt": item.get("prompt"), "reason": "标签不存在或题型不允许"})
            continue
        source = item.get("source") or {}
        question = {
            "type": "code" if kind == "code_question" else "short_answer",
            "code_mode": item.get("code_mode"),
            "tag": tag["name"],
            "prompt": str(item.get("prompt") or "").strip(),
            "options": item.get("options") or [],
            "entities": item.get("entities") or [],
            "rubric": item.get("rubric") or [],
            "source": source,
        }
        rubric = question["rubric"] if isinstance(question["rubric"], list) else []
        if question["type"] == "code" and question["code_mode"] == "implement":
            if not any(rule.get("kind") == "symbol" for rule in rubric):
                symbols = [str(symbol) for symbol in source.get("symbols") or [] if symbol]
                rubric = [
                    {"kind": "symbol", "point": f"提到 {symbol}", "weight": 1, "symbol": symbol}
                    for symbol in symbols
                ] + rubric
        question["rubric"] = rubric
        if not question["prompt"]:
            rejected.append({"prompt": "", "reason": "题干为空"})
            continue
        ok, reason = question_guard.run_gates(
            question,
            chunks=chunks,
            code_content=code_content,
            entity_names=entity_names,
            symbol_names=symbol_names,
            seen_prompts=prompts,
        )
        if not ok:
            rejected.append({"prompt": question["prompt"][:80], "reason": reason})
            continue
        index += 1
        accepted.append(
            {
                "tag_id": tag["id"],
                "kind": kind,
                "code_mode": question["code_mode"],
                "prompt": question["prompt"][:400],
                "answer": str(item.get("answer") or "")[:800],
                "explanation": str(item.get("explanation") or "")[:400],
                "difficulty": item.get("difficulty") if item.get("difficulty") in {"easy", "medium", "hard"} else "medium",
                "entities": question["entities"],
                "rubric": question["rubric"],
                "source": _resolve_source(source, chunks),
            }
        )
        prompts.append(question["prompt"])
    return accepted, rejected


def _resolve_source(source: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = dict(source or {})
    chunk_id = resolved.get("chunk_id")
    for chunk in chunks:
        if chunk["chunk_id"] == chunk_id:
            resolved["document_id"] = chunk["document_id"]
            break
    return resolved


# --------------------------------------------------------------------------- #
# 4. 考试出题
# --------------------------------------------------------------------------- #
async def generate_exam(session_id: str, emit: Emitter = noop_emit) -> list[dict[str, Any]]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    tags = store.list_tags(session_id)
    tag_lookup, _ = _tag_maps(session_id)
    chunks = _doc_chunks(session)
    if not tags or not chunks:
        raise TaskError("请先完成学习阶段")
    from contextlib import closing

    with closing(store.connect()) as conn:
        memory = memory_context.build_exam_memory(conn, session_id)
    capabilities = store.list_capabilities(session_id)
    code = _code(session_id)
    code_content = code["content"] if code else None
    entity_names = _entity_names(session_id)
    symbol_names = _symbol_names(session_id)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: list[str] = list(memory["seen_prompts"])
    for round_index in range(config.EXAM_MAX_REFILL_ROUNDS):
        if len(accepted) >= config.EXAM_QUESTION_COUNT:
            break
        already = {item["prompt"] for item in accepted}
        candidates = await _generate_exam_candidates(
            session_id, tags, chunks, memory, capabilities, code, avoid=rejected[-30:]
        )
        for item in candidates:
            if len(accepted) >= config.EXAM_QUESTION_COUNT:
                break
            tag = tag_lookup.get(str(item.get("tag") or "").strip())
            if not tag:
                rejected.append({"prompt": item.get("prompt"), "reason": "标签不存在"})
                continue
            question = {
                "type": item.get("type") if item.get("type") in {"single_choice", "short_answer", "code"} else "short_answer",
                "code_mode": item.get("code_mode"),
                "tag": tag["name"],
                "tag_id": tag["id"],
                "prompt": str(item.get("prompt") or "").strip(),
                "options": item.get("options") or [],
                "entities": item.get("entities") or [],
                "rubric": item.get("rubric") or [],
                "source": item.get("source") or {},
                "reference_answer": str(item.get("reference_answer") or item.get("answer") or "")[:1200],
                "difficulty": item.get("difficulty") if item.get("difficulty") in {"easy", "medium", "hard"} else "medium",
            }
            if question["prompt"] in {accepted_item["prompt"] for accepted_item in accepted}:
                continue
            ok, reason = question_guard.run_gates(
                question,
                chunks=chunks,
                code_content=code_content,
                entity_names=entity_names,
                symbol_names=symbol_names,
                seen_prompts=seen,
            )
            if not ok:
                rejected.append({"prompt": question["prompt"][:80], "reason": reason})
                continue
            if question["type"] == "single_choice":
                if len(question["options"]) != 4 or not str(item.get("answer") or "").strip().upper()[:1] in {"A", "B", "C", "D"}:
                    rejected.append({"prompt": question["prompt"][:80], "reason": "选择题缺少 4 个选项或唯一答案"})
                    continue
                question["reference_answer"] = str(item.get("answer")).strip().upper()[:1]
            elif question["type"] == "code" and question.get("code_mode") == "locate":
                # 定位题本质是选择题：没有选项或没有唯一答案就丢弃
                answer = str(item.get("answer") or "").strip().upper()[:1]
                if len(question["options"]) != 4 or answer not in {"A", "B", "C", "D"}:
                    rejected.append({"prompt": question["prompt"][:80], "reason": "定位题需要 4 个选项和唯一答案"})
                    continue
                question["reference_answer"] = answer
            else:
                question["reference_answer"] = str(item.get("reference_answer") or item.get("answer") or "").strip()[:1200]
            seen.append(question["prompt"])
            accepted.append(question)
        await emit(
            "step",
            {
                "label": f"出题 第 {round_index + 1} 轮",
                "summary": f"通过 {len(accepted)}/{config.EXAM_QUESTION_COUNT}；丢弃 {len(rejected)}",
                "status": "done",
                "rejected": rejected[-10:],
                "memory": {"practice_prompts": memory["practice_prompts"][:10], "low_tags": memory["low_tags"]},
            },
        )
        if not accepted:
            continue

    ok, reason = question_guard.check_paper(accepted, len(entity_names))
    if len(accepted) < 2:
        raise TaskError(f"试卷生成失败：{reason or '可用题目不足'}")
    if not ok:
        await emit("step", {"label": "试卷约束提示", "summary": f"题目数量或覆盖度未完全达标：{reason}", "status": "done"})
    questions = store.save_exam_questions(session_id, accepted)
    await emit("done", {"count": len(questions), "questions": store.public_exam_questions(session_id)})
    return questions


async def _generate_exam_candidates(
    session_id: str,
    tags: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    memory: dict[str, Any],
    capabilities: list[dict[str, Any]],
    code: dict[str, Any] | None,
    *,
    avoid: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    context = _evidence_context(tags, chunks)
    code_note = ""
    if code:
        code_note = (
            f"\n\n【代码文件】{code['file_name']}（{code['line_count']} 行）\n"
            f"【代码符号表】{_json([item['name'] for item in (code.get('symbols') or [])][:40])}\n"
            "代码题的三种 code_mode：locate 定位行、explain 讲解取舍、implement 讲清功能如何实现。"
        )
    caps = [{"tag": item["tag"], "target": item["target_level"], "acceptance": item["acceptance"]} for item in capabilities]
    avoid_lines = [
        f"- {item.get('prompt') or ''}（原因：{item.get('reason') or ''}）"
        for item in (avoid or [])
        if item.get("prompt")
    ]
    avoid_note = (
        "\n【上一轮被丢弃的题】（换角度重出，不要原样再来）\n" + "\n".join(avoid_lines[:20])
        if avoid_lines
        else ""
    )
    user = (
        f"【项目标签】{_json([tag['name'] for tag in tags])}\n"
        f"【能力目标】{_json(caps)}\n"
        f"【已练习题】{_json(memory['practice_prompts'][:30])}\n"
        f"【练习自评偏低的标签】{_json(memory['low_tags'])}\n"
        f"【项目实体】\n{_json(sorted(_entity_names(session_id))[:40])}\n\n"
        f"【项目文档证据】\n{context}{code_note}{avoid_note}\n\n"
        f"生成 {config.EXAM_CANDIDATE_COUNT} 道候选题（最终只取 {config.EXAM_QUESTION_COUNT} 道）。\n"
        '输出 JSON：{"questions":[{"type":"single_choice|short_answer|code","code_mode":null,'
        '"tag":"标签名","prompt":"题干","options":[],"answer":"A","reference_answer":"...",'
        '"rubric":[{"kind":"behavior|symbol","point":"得分点","weight":2,"symbol":null}],'
        '"difficulty":"easy|medium|hard","entities":[],'
        '"source":{"chunk_id":"...","quote":"...","file":null,"line_start":null,"line_end":null,"symbols":[]}}]}\n'
        "硬规则：\n"
        f"1. 目标试卷 {config.EXAM_QUESTION_COUNT} 题：约 60% 单选、40% 简答；上传代码时至少 2 道 code，且不能全是 locate。\n"
        "2. 覆盖至少 5 个标签，同一标签最多 3 题。\n"
        "3. 每题必须包含项目实体；写不进去就换题。\n"
        "4. 文档题 quote 逐字出自原文；代码题给 file/line_start/line_end/quote/symbols。\n"
        "5. 不得与已练习题重复；同一标签换场景、提难度。\n"
        "6. 自评偏低的标签优先出更难的题。\n"
        "7. 每道题至少对应 1 条能力目标的验收标准；不要为凑数出无关题。\n"
        "8. 题干要像面试官针对这个项目问的，不能是通用八股。"
    )
    data = await llm.json_completion("generate_exam", "你是项目面试出题助手，只能依据用户项目出题。", user, session_id=session_id, temperature=0.3, max_tokens=5000)
    return [item for item in data.get("questions") or [] if isinstance(item, dict)]


# --------------------------------------------------------------------------- #
# 5. 阅卷
# --------------------------------------------------------------------------- #
async def grade_exam(session_id: str, emit: Emitter = noop_emit) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    questions = store.list_exam_questions(session_id)
    answers = {item["question_id"]: item for item in store.list_exam_answers(session_id)}
    graded = 0
    for question in questions:
        answer = answers.get(question["id"])
        if not answer:
            continue
        content = answer.get("content") or ""
        if question["type"] == "single_choice":
            correct = str(question.get("reference_answer") or "").strip().upper()[:1]
            pick = str(content or "").strip().upper()[:1]
            score = 10.0 if pick == correct else 0.0
            store.save_exam_answer(question["id"], content, score, 10.0, hits=[{"point": "选项匹配", "hit": pick == correct}])
        elif question["type"] == "code" and question.get("code_mode") == "locate":
            correct = str(question.get("reference_answer") or "").strip().upper()[:1]
            pick = str(content or "").strip().upper()[:1]
            score = 10.0 if pick and pick == correct else 0.0
            store.save_exam_answer(question["id"], content, score, 10.0, hits=[{"point": "选项匹配", "hit": pick == correct}])
        else:
            result = await _grade_subjective(session_id, question, content)
            store.save_exam_answer(
                question["id"],
                content,
                result["score"],
                result["max_score"],
                hits=result["hits"],
                evidence=result.get("evidence") or [],
                needs_review=result["needs_review"],
                review_note=result.get("review_note"),
            )
        graded += 1
        await emit("step", {"label": f"阅卷 {graded}/{len(questions)}", "summary": "已完成", "status": "done"})
    weak = _diagnose(session_id)
    await emit("done", {"graded": graded, "weak_points": weak})
    return {"graded": graded, "weak_points": weak}


async def _grade_subjective(session_id: str, question: dict[str, Any], answer: str) -> dict[str, Any]:
    rubric = question.get("rubric") or []
    if not rubric:
        rubric = [{"kind": "behavior", "point": "回答了题目的核心问题", "weight": 10}]
    total_weight = sum(float(item.get("weight") or 1) for item in rubric) or 1.0
    symbols = [item for item in (question.get("symbols") or []) if item]
    symbol_checks = question_guard.symbol_mentions(answer, symbols) if symbols else []
    symbol_hits = []
    for item in rubric:
        if item.get("kind") == "symbol" and item.get("symbol"):
            mentioned = any(check["mentioned"] and check["symbol"] == item["symbol"] for check in symbol_checks)
            symbol_hits.append({"kind": "symbol", "point": item.get("point"), "hit": mentioned, "weight": float(item.get("weight") or 1)})
    behavior_rubric = [item for item in rubric if item.get("kind") != "symbol"]

    behavior_hits: list[dict[str, Any]] = []
    needs_review = False
    review_note = ""
    if behavior_rubric and answer.strip():
        user = (
            f"【题目】{question['prompt']}\n\n"
            f"【rubric 得分点】{_json([item.get('point') for item in behavior_rubric])}\n\n"
            f"【用户回答】\n{_clip(answer, 2000)}\n\n"
            '输出 JSON：{"hits":[{"point":"得分点原文","hit":true,"evidence":"用户回答中的原句"}],'
            '"needs_review":false,"review_reason":""}\n'
            "规则：hit=true 时 evidence 必须逐字出现在用户回答里；找不到原句就 hit=false；无法判断时 needs_review=true。"
        )
        try:
            data = await llm.json_completion("grade_answer", "你是阅卷助手，只判断是否命中得分点，不自由给分。", user, session_id=session_id, max_tokens=1200)
            raw_hits = {str(item.get("point") or "").strip(): item for item in data.get("hits") or []}
            text = question_guard.normalize(answer)
            for item in behavior_rubric:
                point = str(item.get("point") or "").strip()
                raw = raw_hits.get(point) or {}
                hit = bool(raw.get("hit"))
                evidence = question_guard.normalize(raw.get("evidence") or "")
                if hit and (not evidence or evidence not in text):
                    hit = False
                    needs_review = True
                    review_note = "模型声称命中但回答里找不到原句，已改判为未命中"
                behavior_hits.append(
                    {"kind": "behavior", "point": point, "hit": hit, "weight": float(item.get("weight") or 1), "evidence": raw.get("evidence")}
                )
            needs_review = needs_review or bool(data.get("needs_review"))
            review_note = review_note or str(data.get("review_reason") or "")
        except Exception:
            needs_review = True
            review_note = "阅卷模型失败，需人工复核"
            behavior_hits = [
                {"kind": "behavior", "point": str(item.get("point") or ""), "hit": False, "weight": float(item.get("weight") or 1)}
                for item in behavior_rubric
            ]

    hits = symbol_hits + behavior_hits
    earned = sum(item["weight"] for item in hits if item["hit"])
    if symbols and not any(check["mentioned"] for check in symbol_checks):
        needs_review = True
        review_note = review_note or "回答没有提到任何要求的代码符号"
    return {
        "score": round(earned / total_weight * 10, 2),
        "max_score": 10.0,
        "hits": hits,
        "evidence": [{"symbol": check["symbol"], "mentioned": check["mentioned"]} for check in symbol_checks],
        "needs_review": needs_review,
        "review_note": review_note,
    }


def _diagnose(session_id: str) -> list[dict[str, Any]]:
    tags = store.list_tags(session_id)
    exam = store.exam_scores_by_tag(session_id)
    points: list[dict[str, Any]] = []
    for tag in tags:
        ratio = exam.get(tag["id"])
        if ratio is None:
            continue
        severity = round(1 - ratio, 4)
        if severity > 0.2:
            reasons = [
                {"question": question["prompt"][:100], "score": (answer or {}).get("score")}
                for question in store.list_exam_questions(session_id)
                if question["tag_id"] == tag["id"]
                for answer in [store.get_exam_answer(question["id"])]
                if answer and (answer.get("score") or 0) < (answer.get("max_score") or 10) * 0.7
            ]
            points.append(
                {
                    "tag_id": tag["id"],
                    "severity": severity,
                    "reason": f"{tag['name']} 考试得分 {ratio * 100:.0f}%，有 {len(reasons)} 题未达 70%",
                    "evidence": reasons,
                }
            )
    points.sort(key=lambda item: item["severity"], reverse=True)
    if not points:
        lowest = min(tags, key=lambda tag: exam.get(tag["id"], 0.0)) if tags else None
        if lowest:
            points = [{"tag_id": lowest["id"], "severity": 0.1, "reason": f"{lowest['name']} 是相对最低分", "evidence": []}]
    return store.save_weak_points(session_id, points[:2])


# --------------------------------------------------------------------------- #
# 6. 能力判定 + 报告
# --------------------------------------------------------------------------- #
def compute_evaluation(session_id: str) -> dict[str, Any]:
    import capabilities as cap_lib

    tags = store.list_tags(session_id)
    caps = store.list_capabilities(session_id)
    weak = store.list_weak_points(session_id)
    interviewed = store.interview_scores_by_tag(session_id)
    exam = dict(store.exam_scores_by_tag(session_id))
    review = store.review_scores_by_tag(session_id)

    # 复练成绩是“补强证据”：只向上覆盖考试得分；复练 ≥ 80% 的标签不再算薄弱点
    for tag_id, ratio in review.items():
        exam[tag_id] = max(exam.get(tag_id, 0.0), ratio)
    weak_tag_ids = {
        item["tag_id"] for item in weak if review.get(item["tag_id"], 0.0) < 0.8
    }

    scores = cap_lib.aggregate_tag_scores(
        tags,
        store.practice_scores_by_tag(session_id),
        exam,
        interviewed,
        weak_tag_ids,
        set(interviewed.keys()),
    )
    return cap_lib.evaluate_pass(caps, scores)


async def grade_review_answers(session_id: str, pairs: list[dict[str, Any]]) -> dict[str, int]:
    """一次调用给复练作答打分（0–100），失败时退化为与参考答案的词项重叠率。"""
    if not pairs:
        return {}
    payload = [
        {"id": item["id"], "question": item["prompt"], "reference_answer": item.get("answer") or "", "user_answer": item["content"]}
        for item in pairs
    ]
    user = (
        f"【复练题与作答】{_json(payload)}\n\n"
        '输出 JSON：{"results":[{"id":"题目 id","score":0-100 的整数,"reason":"一句话"}]}\n'
        "规则：对照参考答案判断是否说清关键点；完全跑题给 0–20；部分说清 40–70；说清且提到项目细节 80–100；不要因为语言风格扣分。"
    )
    try:
        data = await llm.json_completion("grade_review", "你是复练评分助手，只按参考答案判断掌握程度。", user, session_id=session_id, max_tokens=1500)
        scores: dict[str, int] = {}
        for item in data.get("results") or []:
            try:
                value = int(round(float(item.get("score"))))
            except (TypeError, ValueError):
                continue
            scores[str(item.get("id"))] = max(0, min(value, 100))
        if scores:
            return scores
    except Exception:
        pass
    fallback: dict[str, int] = {}
    for item in pairs:
        ratio = question_guard.overlap(item["content"], item.get("answer") or "")
        fallback[item["id"]] = int(round(min(0.9, ratio) * 100))
    return fallback


def build_report(session_id: str) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    evaluation = compute_evaluation(session_id)
    store.apply_capability_results(session_id, evaluation)
    tags = store.list_tags(session_id)
    exam = store.exam_scores_by_tag(session_id)
    practice = store.practice_scores_by_tag(session_id)
    interview = store.interview_scores_by_tag(session_id)
    weak = store.list_weak_points(session_id)
    report = {
        "summary": "",
        "passed": evaluation["passed"],
        "level": evaluation["level"],
        "capabilities": evaluation["criteria"],
        "tags": [
            {
                "tag": tag["name"],
                "practice": round(practice.get(tag["id"], 0.0) * 100),
                "exam": round(exam.get(tag["id"], 0.0) * 100),
                "interview": None if tag["id"] not in interview else round(interview[tag["id"]] * 100),
            }
            for tag in tags
        ],
        "strengths": [item["tag"] for item in evaluation["criteria"] if item["met"]],
        "weaknesses": [{"tag": item["tag"], "reason": item["reason"], "evidence": item.get("evidence") or []} for item in weak],
        "actions": [],
        "next": evaluation["next"],
    }
    return report


async def generate_report_narrative(session_id: str, report: dict[str, Any], emit: Emitter = noop_emit) -> dict[str, Any]:
    user = (
        f"【标签分数】{_json(report['tags'])}\n\n"
        f"【能力判定】{_json(report['capabilities'])}\n\n"
        f"【是否达标】{report['passed']}\n\n"
        f"【薄弱点】{_json(report['weaknesses'])}\n\n"
        '输出 JSON：{"summary":"一句话总结","strengths":["..."],"weaknesses":[{"tag":"...","reason":"引用证据"}],'
        '"actions":["...","...","..."]}\n'
        "规则：数字和判定已由系统算好，不得修改；结论必须指回证据；建议要具体；不承诺保证通过面试。"
    )
    try:
        data = await llm.json_completion("report_narrative", "你是复盘助手，只写解释和建议。", user, session_id=session_id, max_tokens=1200)
    except Exception:
        data = {}
    report["summary"] = str(data.get("summary") or ("已达到本次目标" if report["passed"] else "尚未达到目标，建议按下方复练"))
    if data.get("actions"):
        report["actions"] = [str(item) for item in data["actions"]][:3]
    elif not report["actions"]:
        report["actions"] = [
            f"补练 {item['tag']}：重做项目里对应的实现细节" for item in report["capabilities"] if not item["met"]
        ][:3] or ["保持当前状态，准备下一轮复练"]
    saved = store.save_report(session_id, report)
    await emit("done", {"report": saved})
    return saved


# --------------------------------------------------------------------------- #
# 7. 复练
# --------------------------------------------------------------------------- #
async def generate_review(session_id: str, emit: Emitter = noop_emit) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    from contextlib import closing

    with closing(store.connect()) as conn:
        memory = memory_context.build_review_memory(conn, session_id)
        failed = {item["tag"] for item in memory["failed_capabilities"]}
    tags = [tag for tag in store.list_tags(session_id) if tag["name"] in failed] or store.list_tags(session_id)
    chunks = _doc_chunks(session)
    code = _code(session_id)
    cycle = int(session.get("practice_cycle") or 0) + 1
    store.update_session_fields(session_id, practice_cycle=cycle)

    accepted: list[dict[str, Any]] = []
    seen = list(memory["seen_prompts"])
    attempts = 0
    while len(accepted) < config.REVIEW_ITEMS_MIN and attempts < 4:
        attempts += 1
        items = await _generate_review_batch(session_id, tags, chunks, memory, code)
        screened, rejected = _screen(
            items,
            chunks=chunks,
            code_content=code["content"] if code else None,
            entity_names=_entity_names(session_id),
            symbol_names=_symbol_names(session_id),
            tag_lookup=_tag_maps(session_id)[0],
            seen=seen,
            allow=("question", "code_question"),
        )
        for item in screened:
            if len(accepted) >= config.REVIEW_ITEMS_MIN:
                break
            accepted.append(item)
            seen.append(item["prompt"])
        await emit("step", {"label": f"复练第 {attempts} 批", "summary": f"通过 {len(screened)} 道，丢弃 {len(rejected)} 道", "status": "done"})
    if not accepted:
        raise TaskError("复练题生成失败，请稍后重试")
    store.save_practice_items(session_id, accepted, cycle=cycle)
    await emit("done", {"cycle": cycle, "count": len(accepted)})
    return {"cycle": cycle, "count": len(accepted)}


async def _generate_review_batch(
    session_id: str,
    tags: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    memory: dict[str, Any],
    code: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    context = _evidence_context(tags, chunks)
    user = (
        f"【未达标能力】{_json(memory['failed_capabilities'])}\n"
        f"【薄弱点原因】{_json(memory['reasons'])}\n\n"
        f"【项目文档证据】\n{context}\n\n"
        f"【已完成题目】（不得重复）{_json(memory['seen_prompts'][:60])}\n\n"
        f"只出未达标标签的题，共 {config.REVIEW_ITEMS_MIN} 道，medium/hard 为主。\n"
        '输出 JSON 格式：{"items":[{"tag":"标签名","kind":"question|code_question","code_mode":null,'
        '"difficulty":"medium|hard","prompt":"...","answer":"...","explanation":"...",'
        '"source":{"chunk_id":"...","quote":"...","file":null,"line_start":null,"line_end":null,"symbols":[]}}]}\n'
        "规则：不得重复；带证据和项目实体；优先暴露上次没答清的点。"
    )
    data = await llm.json_completion("generate_review", "你是复练出题助手，只针对未达标能力出题。", user, session_id=session_id, temperature=0.3, max_tokens=4000)
    return [item for item in data.get("items") or [] if isinstance(item, dict)]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _conn():
    return store.connect()


def tag_display(session_id: str, tag_id: str) -> str:
    for tag in store.list_tags(session_id):
        if tag["id"] == tag_id:
            return tag["name"]
    return tag_id
