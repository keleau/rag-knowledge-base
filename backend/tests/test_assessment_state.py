from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import assessment
import assessment_storage as store
import config


class StorageAndStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "assessment.db"
        self.patch = patch.object(config, "ASSESSMENT_DB", self.db)
        self.patch.start()
        store.init_db()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_create_and_get_session(self) -> None:
        session = store.create_session("测试")
        self.assertEqual(session["stage"], "setup")
        self.assertEqual(session["version"], 0)
        self.assertEqual(store.get_session(session["id"])["title"], "测试")

    def test_legal_transitions(self) -> None:
        session = store.create_session()
        updated = assessment.transition(session["id"], 0, assessment.Stage.LEARNING)
        self.assertEqual(updated["stage"], "learning")
        self.assertEqual(updated["version"], 1)
        updated = assessment.transition(session["id"], 1, assessment.Stage.EXAM, guard=lambda _: True)
        self.assertEqual(updated["stage"], "exam")

    def test_illegal_transition(self) -> None:
        session = store.create_session()
        with self.assertRaises(assessment.InvalidTransition):
            assessment.transition(session["id"], 0, assessment.Stage.EXAM)

    def test_version_conflict(self) -> None:
        session = store.create_session()
        assessment.transition(session["id"], 0, assessment.Stage.LEARNING)
        with self.assertRaises(assessment.VersionConflict):
            assessment.transition(session["id"], 0, assessment.Stage.EXAM)

    def test_guard_failure_keeps_state(self) -> None:
        session = store.create_session()

        def guard(_):
            return False, "没有项目"

        with self.assertRaises(assessment.GuardFailed):
            assessment.transition(session["id"], 0, assessment.Stage.LEARNING, guard=guard)
        self.assertEqual(store.get_session(session["id"])["stage"], "setup")

    def test_report_cycle(self) -> None:
        session = store.create_session()
        for index, stage in enumerate(
            [assessment.Stage.LEARNING, assessment.Stage.EXAM, assessment.Stage.GRADING,
             assessment.Stage.INTERVIEW, assessment.Stage.REPORT]
        ):
            assessment.transition(session["id"], index, stage)
        updated = assessment.transition(session["id"], 5, assessment.Stage.PRACTICE)
        self.assertEqual(updated["stage"], "practice")
        updated = assessment.transition(session["id"], 6, assessment.Stage.REPORT)
        self.assertEqual(updated["stage"], "report")

    def test_delete_cascades(self) -> None:
        session = store.create_session()
        tags = store.save_tags(session["id"], [{"name": "状态管理", "description": "x"}])
        store.save_capabilities(session["id"], [{"tag_id": tags[0]["id"], "target_level": "L3", "acceptance": ["a"], "evidence_quote": "q"}])
        store.delete_session(session["id"])
        self.assertIsNone(store.get_session(session["id"]))
        self.assertEqual(store.list_tags(session["id"]), [])
        self.assertEqual(store.list_capabilities(session["id"]), [])

    def test_practice_answer_upsert(self) -> None:
        session = store.create_session()
        tags = store.save_tags(session["id"], [{"name": "状态管理", "description": "x"}])
        items = store.save_practice_items(
            session["id"],
            [{"tag_id": tags[0]["id"], "kind": "question", "prompt": "题目", "answer": "答案", "source": {"quote": "q"}}],
        )
        store.save_practice_answer(items[0]["id"], "第一次", 40)
        store.save_practice_answer(items[0]["id"], "第二次", 90)
        listed = store.list_practice_items(session["id"])
        self.assertEqual(listed[0]["user_answer"], "第二次")
        self.assertEqual(listed[0]["self_score"], 90)

    def test_submission_idempotency(self) -> None:
        session = store.create_session()
        self.assertTrue(store.create_submission(session["id"], "k1", "h"))
        self.assertFalse(store.create_submission(session["id"], "k1", "h"))

    def test_regenerate_tags_clears_dependents(self) -> None:
        session = store.create_session()
        tags = store.save_tags(session["id"], [{"name": "状态管理", "description": "x"}])
        store.save_capabilities(session["id"], [{"tag_id": tags[0]["id"], "target_level": "L3", "acceptance": ["a"], "evidence_quote": "q"}])
        store.save_practice_items(
            session["id"],
            [{"tag_id": tags[0]["id"], "kind": "question", "prompt": "题目", "answer": "答案", "source": {"quote": "q"}}],
        )
        # 再次生成不同名字的标签，不应该因为外键失败
        store.save_tags(session["id"], [{"name": "异常与边界", "description": "y"}])
        self.assertEqual([tag["name"] for tag in store.list_tags(session["id"])], ["异常与边界"])
        self.assertEqual(store.list_practice_items(session["id"]), [])
        self.assertEqual(store.list_capabilities(session["id"]), [])

    def test_report_roundtrip_keeps_next(self) -> None:
        session = store.create_session()
        saved = store.save_report(
            session["id"],
            {
                "summary": "s",
                "passed": False,
                "level": "L2",
                "capabilities": [],
                "tags": [],
                "strengths": [],
                "weaknesses": [],
                "actions": ["a"],
                "next": ["复练 状态管理"],
            },
        )
        self.assertEqual(saved["next"], ["复练 状态管理"])
        self.assertFalse(saved["passed"])


if __name__ == "__main__":
    unittest.main()
