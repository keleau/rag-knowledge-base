from __future__ import annotations

import unittest

import capabilities


def scores(**values):
    base = {"practice": 0.0, "exam": 0.0, "interview": None, "is_weak": False}
    base.update(values)
    return base


CAPS = [
    {"tag_id": "t1", "tag": "状态管理", "target_level": "L3"},
    {"tag_id": "t2", "tag": "异常与边界", "target_level": "L3"},
    {"tag_id": "t3", "tag": "组件设计", "target_level": "L2"},
    {"tag_id": "t4", "tag": "工程化", "target_level": "L1"},
    {"tag_id": "t5", "tag": "接口与数据流", "target_level": "L2"},
    {"tag_id": "t6", "tag": "性能优化", "target_level": "L2"},
]


class LevelTests(unittest.TestCase):
    def test_level_for(self) -> None:
        self.assertEqual(capabilities.level_for(0.9), "L4")
        self.assertEqual(capabilities.level_for(0.7), "L3")
        self.assertEqual(capabilities.level_for(0.5), "L2")
        self.assertEqual(capabilities.level_for(0.1), "L1")
        self.assertIsNone(capabilities.level_for(0.0))
        self.assertIsNone(capabilities.level_for(None))


class EvaluateTests(unittest.TestCase):
    def test_all_good_passes(self) -> None:
        tag_scores = {
            "t1": scores(exam=0.9, interview=0.85),
            "t2": scores(exam=0.9, interview=0.9),
            "t3": scores(exam=0.7),
            "t4": scores(exam=0.4),
            "t5": scores(exam=0.8),
            "t6": scores(exam=0.8),
        }
        result = capabilities.evaluate_pass(CAPS, tag_scores)
        self.assertTrue(result["passed"])

    def test_uncovered_l3_fails(self) -> None:
        tag_scores = {
            "t1": scores(exam=0.9, interview=0.9),
            "t2": scores(exam=0.9),  # 目标 L3 但面试没考到
            "t3": scores(exam=0.8),
            "t4": scores(exam=0.6),
        }
        result = capabilities.evaluate_pass(CAPS, tag_scores)
        self.assertFalse(result["passed"])
        t2 = next(item for item in result["criteria"] if item["tag_id"] == "t2")
        self.assertIn("面试未考到", t2["gap"])

    def test_weak_tag_blocks_pass(self) -> None:
        tag_scores = {
            "t1": scores(exam=0.9, interview=0.9),
            "t2": scores(exam=0.9, interview=0.9, is_weak=True),
            "t3": scores(exam=0.9),
            "t4": scores(exam=0.7),
        }
        result = capabilities.evaluate_pass(CAPS, tag_scores)
        self.assertFalse(result["passed"])

    def test_missing_scores_have_no_overall_level(self) -> None:
        result = capabilities.evaluate_pass(CAPS, {"t1": scores(exam=0.9)})
        self.assertIsNone(result["level"])
        self.assertFalse(result["passed"])

    def test_deterministic(self) -> None:
        tag_scores = {
            "t1": scores(exam=0.72, interview=0.71),
            "t2": scores(exam=0.68, interview=0.66),
            "t3": scores(exam=0.8),
            "t4": scores(exam=0.55),
        }
        first = capabilities.evaluate_pass(CAPS, tag_scores)
        second = capabilities.evaluate_pass(CAPS, tag_scores)
        self.assertEqual(first, second)

    def test_monotonic(self) -> None:
        low = capabilities.evaluate_pass(
            CAPS,
            {
                "t1": scores(exam=0.55, interview=0.55),
                "t2": scores(exam=0.55, interview=0.55),
                "t3": scores(exam=0.55),
                "t4": scores(exam=0.55),
                "t5": scores(exam=0.55),
                "t6": scores(exam=0.55),
            },
        )
        high = capabilities.evaluate_pass(
            CAPS,
            {
                "t1": scores(exam=0.9, interview=0.9),
                "t2": scores(exam=0.9, interview=0.9),
                "t3": scores(exam=0.9),
                "t4": scores(exam=0.9),
                "t5": scores(exam=0.9),
                "t6": scores(exam=0.9),
            },
        )
        self.assertLessEqual(capabilities.LEVELS.index(low["level"]), capabilities.LEVELS.index(high["level"]))


if __name__ == "__main__":
    unittest.main()
