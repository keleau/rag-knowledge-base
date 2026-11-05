from __future__ import annotations

from contextlib import closing
from typing import Any

import assessment_storage as store
import config
import llm
import memory_context
import rag
from assessment_tasks import TaskError, _code, _doc_chunks, _json, _clip


def _weak_tags(session_id: str) -> list[dict[str, Any]]:
    weak = store.list_weak_points(session_id)
    if weak:
        return weak
    # 兜底：考试最低分标签
    tags = store.list_tags(session_id)
    scores = store.exam_scores_by_tag(session_id)
    if not tags:
        return []
    lowest = min(tags, key=lambda tag: scores.get(tag["id"], 0.0))
    return [{"tag_id": lowest["id"], "tag": lowest["name"], "reason": "考试相对最低分", "severity": 0.1}]


def _covered_tag_ids(session_id: str) -> set[str]:
    return {turn["tag_id"] for turn in store.list_interview_turns(session_id)}


def next_tag(session_id: str, weak: list[dict[str, Any]]) -> dict[str, Any]:
    """优先覆盖尚未考核的 L3 能力，其次取薄弱点。"""
    caps = store.list_capabilities(session_id)
    covered = _covered_tag_ids(session_id)
    l3_uncovered = [cap for cap in caps if cap["target_level"] == "L3" and cap["tag_id"] not in covered]
    for cap in l3_uncovered:
        for point in weak:
            if point["tag_id"] == cap["tag_id"]:
                return point
        return {"tag_id": cap["tag_id"], "tag": cap["tag"], "reason": "目标 L3 能力尚未被面试覆盖", "severity": 0.2}
    for point in weak:
        if point["tag_id"] not in covered:
            return point
    return weak[0]


async def start_interview(session_id: str) -> dict[str, Any]:
    session = store.get_session(session_id)
    if session is None:
        raise TaskError("评估会话不存在")
    turns = store.list_interview_turns(session_id)
    if turns:
        return {"turn": turns[-1], "turns": turns}
    weak = _weak_tags(session_id)
    if not weak:
        raise TaskError("没有薄弱点，无法开始面试")
    point = next_tag(session_id, weak)
    await _ask(session_id, point, round_index=1, next_round=True)
    return {"turn": store.list_interview_turns(session_id)[-1], "turns": store.list_interview_turns(session_id)}


async def _ask(
    session_id: str,
    point: dict[str, Any],
    *,
    round_index: int,
    follow_up_of: str | None = None,
    missing_points: list[str] | None = None,
    last_answer: str = "",
    next_round: bool = False,
) -> dict[str, Any]:
    session = store.get_session(session_id) or {}
    chunks = _doc_chunks(session) or []
    evidence = rag.search(f"{point['tag']} {point.get('reason') or ''}", top_k=4, documents=chunks)
    code = _code(session_id)
    with closing(store.connect()) as conn:
        memory = memory_context.build_exam_memory(conn, session_id)
    caps = store.list_capabilities(session_id)
    covered = _covered_tag_ids(session_id)
    uncovered_l3 = [cap["tag"] for cap in caps if cap["target_level"] == "L3" and cap["tag_id"] not in covered]
    code_note = f"\n【代码文件】{code['file_name']}，符号：{_json([item['name'] for item in (code.get('symbols') or [])][:20])}" if code else ""

    user = (
        f"【本轮考察标签】{point['tag']}\n"
        f"【薄弱点原因】{point.get('reason') or ''}\n"
        f"【能力目标】{_json([{'tag': cap['tag'], 'target': cap['target_level']} for cap in caps])}\n"
        f"【尚未覆盖的 L3 能力】{_json(uncovered_l3)}\n"
        f"【上一轮回答】{_clip(last_answer, 800) if last_answer else '（第一轮）'}\n"
        f"【未命中的得分点】{_json(missing_points or [])}\n"
        f"【已问过的题】{_json(memory['asked_questions'][:20])}\n"
        f"【项目证据】{_json([_clip(item.get('text'), 500) for item in evidence][:4])}{code_note}\n\n"
        '输出 JSON：{"question":"问题","why":"引用上一轮缺失点或用户原话","follow_up_of":"上一问 id 或 null",'
        '"covers_capability":"本题主要考察的标签",'
        '"rubric":[{"kind":"behavior","point":"得分点","weight":3}]}\n'
        "规则：题干不超过 120 字，必须包含项目实体；不得与已问过的题重复；不得问文档/代码之外的事实；"
        "如果上一轮已答清，就换角度或换薄弱标签，不要复读。"
    )
    try:
        data = await llm.json_completion("interview_question", "你是模拟面试官，只考察用户的项目。", user, session_id=session_id, temperature=0.4, max_tokens=800)
    except Exception as exc:
        raise TaskError(f"面试出题失败：{exc}") from exc

    question = str(data.get("question") or "").strip()
    if not question:
        raise TaskError("面试出题失败：模型没有返回问题")
    rubric = data.get("rubric") or [{"kind": "behavior", "point": f"说清{point['tag']}在项目里的具体做法", "weight": 5}]
    turn = store.add_interview_turn(
        session_id,
        point["tag_id"],
        round_index,
        question,
        follow_up_of=follow_up_of,
        rubric=rubric,
        weak_point_id=point.get("id"),
    )
    store.update_session_fields(session_id, current_round=round_index)
    return turn


async def answer_interview(session_id: str, answer: str) -> dict[str, Any]:
    turns = store.list_interview_turns(session_id)
    if not turns:
        raise TaskError("还没有开始面试")
    current = turns[-1]
    if current.get("status") != "asking":
        raise TaskError("当前问题已经回答过了")
    store.save_interview_answer(current["id"], answer)

    rubric = current.get("rubric") or []
    total = sum(float(item.get("weight") or 1) for item in rubric) or 1.0
    hits: list[dict[str, Any]] = []
    needs_review = False
    if answer.strip() and rubric:
        user = (
            f"【题目】{current['question']}\n【得分点】{_json([item.get('point') for item in rubric])}\n"
            f"【回答】\n{_clip(answer, 1500)}\n\n"
            '输出 JSON：{"hits":[{"point":"得分点","hit":true,"evidence":"回答原句"}],"needs_review":false}\n'
            "规则：evidence 必须逐字出自回答；找不到原句就 hit=false。"
        )
        try:
            data = await llm.json_completion("grade_answer", "你是面试评分助手，只判断是否命中得分点。", user, session_id=session_id, max_tokens=800)
            text = "".join(str(answer).split()).lower()
            raw = {str(item.get("point") or "").strip(): item for item in data.get("hits") or []}
            for item in rubric:
                point = str(item.get("point") or "").strip()
                entry = raw.get(point) or {}
                hit = bool(entry.get("hit"))
                evidence = "".join(str(entry.get("evidence") or "").split()).lower()
                if hit and (not evidence or evidence not in text):
                    hit = False
                    needs_review = True
                hits.append({"point": point, "hit": hit, "weight": float(item.get("weight") or 1)})
        except Exception:
            needs_review = True
            hits = [{"point": str(item.get("point") or ""), "hit": False, "weight": float(item.get("weight") or 1)} for item in rubric]

    earned = sum(item["weight"] for item in hits if item["hit"])
    score = round(earned / total * 10, 2)
    store.save_interview_grade(current["id"], score, [{"point": item["point"], "hit": item["hit"]} for item in hits])

    missing = [item["point"] for item in hits if not item["hit"]]
    follow_ups = sum(1 for turn in turns if turn.get("follow_up_of") == current["id"])
    rounds_used = max(int(turn.get("round_index") or 1) for turn in turns)

    should_follow = bool(missing) and follow_ups < config.INTERVIEW_MAX_FOLLOW_UPS and score < 7
    if should_follow:
        point = {
            "id": current.get("weak_point_id"),
            "tag_id": current["tag_id"],
            "tag": current.get("tag") or "",
            "reason": f"上一轮未答清：{'、'.join(missing[:2])}",
        }
        try:
            await _ask(
                session_id,
                point,
                round_index=rounds_used,
                follow_up_of=current["id"],
                missing_points=missing,
                last_answer=answer,
            )
            finished = False
        except TaskError:
            finished = True
    elif rounds_used < config.INTERVIEW_MAX_ROUNDS:
        weak = _weak_tags(session_id)
        point = next_tag(session_id, weak)
        await _ask(session_id, point, round_index=rounds_used + 1)
        finished = False
    else:
        finished = True

    return {
        "grade": {"score": score, "hits": hits, "needs_review": needs_review},
        "finished": finished,
        "turns": store.list_interview_turns(session_id),
        "current_round": rounds_used + 1 if not finished else rounds_used,
    }
