from __future__ import annotations

from typing import Any

import config

LEVELS = ["L1", "L2", "L3", "L4"]


def level_for(ratio: float | None) -> str | None:
    if ratio is None:
        return None
    if ratio >= 0.85:
        return "L4"
    if ratio >= config.PASS_EXAM_RATIO:
        return "L3"
    if ratio >= 0.50:
        return "L2"
    if ratio > 0:
        return "L1"
    return None


def _index(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else -1


def aggregate_tag_scores(
    tags: list[dict[str, Any]],
    practice_scores: dict[str, float],
    exam_scores: dict[str, float],
    interview_scores: dict[str, float],
    weak_tag_ids: set[str],
    interviewed_tag_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """把三个阶段的原始分按标签聚合成得分率（0–1）。"""
    result: dict[str, dict[str, Any]] = {}
    for tag in tags:
        tag_id = tag["id"]
        result[tag_id] = {
            "name": tag["name"],
            "practice": round(practice_scores.get(tag_id, 0.0), 4),
            "exam": round(exam_scores.get(tag_id, 0.0), 4),
            "interview": round(interview_scores[tag_id], 4) if tag_id in interviewed_tag_ids else None,
            "is_weak": tag_id in weak_tag_ids,
        }
    return result


def _capability_ratio(scores: dict[str, Any] | None) -> float | None:
    if not scores:
        return None
    exam = float(scores.get("exam") or 0.0)
    interview = scores.get("interview")
    if interview is None:
        return exam
    # 面试考过但答得很差时，不能只靠考试分数抬等级
    return min(exam, float(interview))


def evaluate_pass(capabilities: list[dict[str, Any]], tag_scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """通关判定：纯函数，模型不得参与。

    capabilities: [{tag_id, tag, target_level, ...}]
    tag_scores:  aggregate_tag_scores() 的输出（按 tag_id 索引）
    """
    criteria: list[dict[str, Any]] = []
    l3_ok = True
    l2_count = 0

    for cap in capabilities:
        tag_id = cap["tag_id"]
        target = cap.get("target_level") or "L2"
        scores = tag_scores.get(tag_id) or {}
        exam = float(scores.get("exam") or 0.0)
        interview = scores.get("interview")
        is_weak = bool(scores.get("is_weak"))
        covered = interview is not None

        met = exam >= config.PASS_EXAM_RATIO and not is_weak
        interview_gap = ""
        needs_interview = _index(target) >= _index("L3")
        if needs_interview and not covered:
            met = False
            interview_gap = "面试未考到"
        elif covered and float(interview) < config.PASS_INTERVIEW_RATIO:
            met = False
            interview_gap = f"面试得分 {float(interview) * 100:.0f}%"

        ratio = _capability_ratio(scores)
        current = level_for(ratio)
        if current and _index(current) >= _index("L2"):
            l2_count += 1
        if needs_interview and not met:
            l3_ok = False

        gap_parts: list[str] = []
        if not met:
            if exam < config.PASS_EXAM_RATIO:
                gap_parts.append(f"考试得分 {exam * 100:.0f}%")
            if is_weak:
                gap_parts.append("仍是薄弱点")
            if interview_gap:
                gap_parts.append(interview_gap)
        criteria.append(
            {
                "tag_id": tag_id,
                "tag": cap.get("tag") or (scores.get("name") or ""),
                "target": target,
                "current": current,
                "met": met,
                "covered": covered,
                "gap": "；".join(gap_parts),
            }
        )

    passed = bool(l3_ok and l2_count >= config.PASS_MIN_L2_COUNT)
    current_levels = [item["current"] for item in criteria]
    overall = (
        None
        if not current_levels or any(level is None for level in current_levels)
        else min(current_levels, key=_index)
    )
    unmet = [item for item in criteria if not item["met"]]
    return {
        "passed": passed,
        "level": overall,
        "l2_count": l2_count,
        "criteria": criteria,
        "next": [f"复练 {item['tag']}" for item in unmet],
    }
