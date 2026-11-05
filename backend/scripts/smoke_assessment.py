"""项目定向测评的离线验证脚本。

在没有 DeepSeek Key 的情况下，用样例项目文档验证：
1. 实体抽取是否抽到项目名词；
2. 代码解析是否给出正确的符号和行号；
3. 三道闸门（证据 / 实体 / 去重）是否按预期拦下不合格题；
4. 能力通关判定是否稳定。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/smoke_assessment.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import assessment_storage as store  # noqa: E402
import capabilities  # noqa: E402
import code_parser  # noqa: E402
import config  # noqa: E402
import entities as entity_lib  # noqa: E402
import question_guard  # noqa: E402
import storage  # noqa: E402


def main() -> int:
    doc_path = BACKEND.parent / "samples" / "知问项目技术说明.md"
    code_path = BACKEND.parent / "frontend" / "src" / "App.vue"
    doc_text = doc_path.read_text(encoding="utf-8")
    code_text = code_path.read_text(encoding="utf-8")

    print("== 1. 实体抽取 ==")
    doc_entities = entity_lib.extract_entities(doc_text, limit=30)
    names = [item["name"] for item in doc_entities]
    print("文档实体：", "、".join(names[:15]))
    required = ["TF-IDF", "SSE"]
    missing = [word for word in required if word not in names]
    print("关键实体缺失：", missing or "无")

    print("\n== 2. 代码解析 ==")
    parsed = code_parser.parse_code("App.vue", code_text)
    print(f"文件：{parsed['file_name']} · {parsed['line_count']} 行 · {len(parsed['symbols'])} 个符号")
    for item in parsed["symbols"][:12]:
        print(f"  {item['kind']:<10} {item['name']:<24} L{item['line']}–{item['end_line']}")

    print("\n== 3. 三道闸门 ==")
    chunks = [{"chunk_id": "c1", "document_name": doc_path.name, "text": doc_text}]
    entity_names = set(names)
    symbol_names = set(parsed["symbol_names"])
    cases = [
        ("通用题", {"type": "short_answer", "prompt": "请求失败你怎么处理？", "source": {"quote": "请求失败"}}, False),
        (
            "合格文档题",
            {
                "type": "single_choice",
                "prompt": "知问默认每个分块多少字，相邻块重叠多少字？",
                "options": ["A 500 / 80", "B 300 / 50", "C 800 / 100", "D 1000 / 200"],
                "source": {"quote": "默认每块 500 字，相邻块重叠 80 字"},
            },
            True,
        ),
        (
            "代码实现题",
            {
                "type": "code",
                "code_mode": "implement",
                "prompt": "App.vue 里 handleSend 是怎么把用户输入变成流式回答的？",
                "rubric": [{"kind": "symbol", "point": "提到 streamContent", "weight": 2}],
                "source": {"file": "App.vue", "line_start": 160, "line_end": 220, "quote": "", "symbols": ["streamContent", "streamChat"]},
            },
            True,
        ),
        (
            "引用不存在",
            {"type": "short_answer", "prompt": "SSE 是什么？", "source": {"quote": "库里没有的句子"}},
            False,
        ),
    ]
    ok_count = 0
    for label, question, expected in cases:
        ok, reason = question_guard.run_gates(
            question,
            chunks=chunks,
            code_content=code_text,
            entity_names=entity_names,
            symbol_names=symbol_names,
            seen_prompts=["App.vue 里 streamContent 是怎么渲染出来的？"] if label == "代码实现题" else [],
        )
        mark = "[PASS]" if ok == expected else "[FAIL]"
        if ok == expected:
            ok_count += 1
        print(f"  {mark} {label}: {'通过' if ok else f'丢弃（{reason}）'}")
    print(f"闸门用例 {ok_count}/{len(cases)} 符合预期")

    print("\n== 4. 能力判定 ==")
    caps = [
        {"tag_id": "t1", "tag": "状态管理", "target_level": "L3"},
        {"tag_id": "t2", "tag": "异常与边界", "target_level": "L3"},
        {"tag_id": "t3", "tag": "组件设计", "target_level": "L2"},
        {"tag_id": "t4", "tag": "工程化", "target_level": "L1"},
        {"tag_id": "t5", "tag": "接口与数据流", "target_level": "L2"},
        {"tag_id": "t6", "tag": "性能优化", "target_level": "L2"},
    ]
    base = {"practice": 0.0, "exam": 0.0, "interview": None, "is_weak": False}
    good = capabilities.evaluate_pass(
        caps,
        {
            "t1": {**base, "exam": 0.9, "interview": 0.9},
            "t2": {**base, "exam": 0.85, "interview": 0.8},
            "t3": {**base, "exam": 0.75},
            "t4": {**base, "exam": 0.75},
            "t5": {**base, "exam": 0.8},
            "t6": {**base, "exam": 0.8},
        },
    )
    print(f"  全部达标场景 passed={good['passed']} level={good['level']}")
    bad = capabilities.evaluate_pass(
        caps,
        {
            "t1": {**base, "exam": 0.9, "interview": 0.9},
            "t2": {**base, "exam": 0.9},
            "t3": {**base, "exam": 0.8},
            "t4": {**base, "exam": 0.6},
            "t5": {**base, "exam": 0.8},
            "t6": {**base, "exam": 0.8},
        },
    )
    print(f"  面试未覆盖 L3 场景 passed={bad['passed']}")
    gap = next(item for item in bad["criteria"] if item["tag_id"] == "t2")["gap"]
    print(f"  未达标原因：{gap}")

    print("\n== 5. 存储与状态机（临时库）==")
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(config, "ASSESSMENT_DB", Path(tmp) / "a.db"), \
         patch.object(storage, "DOCUMENTS_FILE", Path(tmp) / "documents.json"):
        store.init_db()
        session = store.create_session("冒烟测试")
        tags = store.save_tags(session["id"], [{"name": "状态管理", "description": "ref/computed"}])
        store.save_capabilities(session["id"], [{"tag_id": tags[0]["id"], "target_level": "L3", "acceptance": ["a"], "evidence_quote": "q"}])
        print(f"  会话 {session['id']} · 标签 {len(tags)} · 能力 {len(store.list_capabilities(session['id']))}")

        # 重新生成标签（依赖标签的练习/能力/试卷应被清掉，不应触发外键错误）
        new_tags = store.save_tags(session["id"], [{"name": "异常与边界", "description": "75% 门槛"}])
        print(f"  重新生成标签后：{new_tags[0]['name']} · 能力 {len(store.list_capabilities(session['id']))}")

        # 报告往返：next 字段必须落库
        report = store.save_report(
            session["id"],
            {"summary": "s", "passed": False, "level": "L2", "capabilities": [], "tags": [],
             "strengths": [], "weaknesses": [], "actions": ["a"], "next": ["复练 状态管理"]},
        )
        print(f"  报告往返：next={report['next']}")
        remaining_capabilities = len(store.list_capabilities(session["id"]))

    success = (
        not missing
        and ok_count == len(cases)
        and good["passed"]
        and not bad["passed"]
        and report["next"] == ["复练 状态管理"]
        and remaining_capabilities == 0
    )
    print("\n结果：", "全部通过" if success else "有不符合预期的项，请查看上面输出")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
