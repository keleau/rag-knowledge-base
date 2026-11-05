from __future__ import annotations

import unittest

import question_guard


CHUNKS = [
    {"chunk_id": "c1", "document_name": "项目.md", "text": "DocumentDrawer 用 computed 汇总选中项数量，证据门槛设为 75%。"}
]

CODE = "const drawerDoc = ref(null)\nfunction openDocument(id) {\n  drawerDoc.value = id\n}\n"

ENTITIES = {"DocumentDrawer", "75%"}


class EvidenceTests(unittest.TestCase):
    def test_doc_quote_found(self) -> None:
        ok, _ = question_guard.check_evidence(
            {"type": "single_choice", "source": {"quote": "用 computed 汇总选中项数量"}}, CHUNKS, None
        )
        self.assertTrue(ok)

    def test_doc_quote_missing(self) -> None:
        ok, reason = question_guard.check_evidence(
            {"type": "short_answer", "source": {"quote": "库里根本不存在的句子"}}, CHUNKS, None
        )
        self.assertFalse(ok)
        self.assertIn("quote", reason)

    def test_code_line_range(self) -> None:
        ok, _ = question_guard.check_evidence(
            {"type": "code", "source": {"file": "a.vue", "line_start": 2, "line_end": 4, "quote": "function openDocument"}},
            CHUNKS,
            CODE,
        )
        self.assertTrue(ok)

    def test_code_line_out_of_range(self) -> None:
        ok, reason = question_guard.check_evidence(
            {"type": "code", "source": {"file": "a.vue", "line_start": 9, "line_end": 12}}, CHUNKS, CODE
        )
        self.assertFalse(ok)
        self.assertIn("越界", reason)


class EntityTests(unittest.TestCase):
    def test_generic_question_rejected(self) -> None:
        ok, reason = question_guard.check_entity({"prompt": "请求失败你怎么处理？"}, ENTITIES, set())
        self.assertFalse(ok)
        self.assertIn("实体", reason)

    def test_entity_hit(self) -> None:
        ok, _ = question_guard.check_entity({"prompt": "DocumentDrawer 为什么用 computed？"}, ENTITIES, set())
        self.assertTrue(ok)

    def test_symbol_hit(self) -> None:
        ok, _ = question_guard.check_entity({"prompt": "openDocument 里发生了什么？"}, set(), {"openDocument"})
        self.assertTrue(ok)

    def test_self_declared_entities_do_not_count(self) -> None:
        # 模型在 entities 字段里自己声明实体，不能拿来给题干“作证”
        ok, reason = question_guard.check_entity(
            {"prompt": "请求失败你怎么处理？", "entities": ["DocumentDrawer", "75%"]}, ENTITIES, set()
        )
        self.assertFalse(ok)
        self.assertIn("实体", reason)


class DedupTests(unittest.TestCase):
    def test_same_question_rejected(self) -> None:
        ok, _ = question_guard.check_dedup({"prompt": "DocumentDrawer 为什么用 computed 汇总选中项数量？"}, ["DocumentDrawer 为什么用 computed 汇总选中项数量？"])
        self.assertFalse(ok)

    def test_different_scenario_allowed(self) -> None:
        ok, _ = question_guard.check_dedup({"prompt": "如果改成 watch 维护计数，会出什么问题？"}, ["DocumentDrawer 为什么用 computed 汇总选中项数量？"])
        self.assertTrue(ok)


class CodeShapeTests(unittest.TestCase):
    def test_implement_requires_symbols(self) -> None:
        ok, reason = question_guard.check_code_shape(
            {"type": "code", "code_mode": "implement", "source": {"symbols": ["drawerDoc"]}, "rubric": [{"kind": "symbol", "point": "x", "weight": 2}]},
            CODE,
        )
        self.assertFalse(ok)
        self.assertIn("2 个", reason)

    def test_missing_symbol_rejected(self) -> None:
        ok, reason = question_guard.check_code_shape(
            {"type": "code", "code_mode": "explain", "source": {"symbols": ["notExist"]}, "rubric": []},
            CODE,
        )
        self.assertFalse(ok)
        self.assertIn("notExist", reason)

    def test_valid_implement(self) -> None:
        ok, _ = question_guard.check_code_shape(
            {
                "type": "code",
                "code_mode": "implement",
                "source": {"symbols": ["drawerDoc", "openDocument"]},
                "rubric": [{"kind": "symbol", "point": "提到 drawerDoc", "weight": 2}],
            },
            CODE,
        )
        self.assertTrue(ok)


class SymbolMentionTests(unittest.TestCase):
    def test_mentions(self) -> None:
        results = question_guard.symbol_mentions("我用了 drawerDoc 存数据", ["drawerDoc", "openDocument"])
        self.assertTrue(results[0]["mentioned"])
        self.assertFalse(results[1]["mentioned"])


if __name__ == "__main__":
    unittest.main()
