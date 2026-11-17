import unittest

from agent_reliability.quality import compare_runs, validate_dataset


def task(task_id="a", split="dev", question="Question", family="f"):
    return {"id": task_id, "split": split, "question": question, "family_id": family}


class DatasetTests(unittest.TestCase):
    def test_valid_separation(self):
        rows = [task(), task("b", "test", "Other", "g")]
        self.assertEqual(validate_dataset(rows)["tasks"], 2)

    def test_empty(self):
        with self.assertRaises(ValueError):
            validate_dataset([])

    def test_duplicate_id(self):
        with self.assertRaises(ValueError):
            validate_dataset([task(), task()])

    def test_question_leakage(self):
        with self.assertRaises(ValueError):
            validate_dataset([task(), task("b", "test", "  QUESTION  ", "g")])

    def test_family_leakage(self):
        with self.assertRaises(ValueError):
            validate_dataset([task(), task("b", "test", "Other")])

    def test_invalid_split(self):
        with self.assertRaises(ValueError):
            validate_dataset([task(split="train")])

    def test_review_metadata(self):
        row = {**task(), "review_status": "human_reviewed"}
        with self.assertRaises(ValueError):
            validate_dataset([row])


class ComparisonTests(unittest.TestCase):
    def test_regression(self):
        old = [{"task_id": "a", "passed": True}]
        new = [{"task_id": "a", "passed": False}]
        result = compare_runs(old, new)
        self.assertFalse(result["gate_passed"])
        self.assertEqual(result["regressions"], ["a"])

    def test_improvement(self):
        old = [{"task_id": "a", "passed": False}]
        new = [{"task_id": "a", "passed": True}]
        self.assertEqual(compare_runs(old, new)["improvements"], ["a"])

    def test_different_tasks(self):
        old = [{"task_id": "a", "passed": True}]
        new = [{"task_id": "b", "passed": True}]
        with self.assertRaises(ValueError):
            compare_runs(old, new)

    def test_duplicate_attempt(self):
        row = {"task_id": "a", "passed": True}
        with self.assertRaises(ValueError):
            compare_runs([row, row], [row])

    def test_strict_boolean(self):
        with self.assertRaises(ValueError):
            compare_runs([{"task_id": "a", "passed": "false"}], [])

    def test_invalid_metrics(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_runs([{"task_id": "a", "passed": True, "cost_usd": value}], [])

    def test_metric_delta(self):
        old = {"task_id": "a", "passed": True, "latency_ms": 10, "cost_usd": 0.1}
        new = {**old, "latency_ms": 12, "cost_usd": 0.2}
        result = compare_runs([old], [new])
        self.assertEqual(result["metrics"]["latency_ms"]["delta"], 2)
        self.assertAlmostEqual(result["metrics"]["cost_usd"]["delta"], 0.1)

    def test_missing_cost_not_zero(self):
        row = {"task_id": "a", "passed": True}
        self.assertIsNone(compare_runs([row], [row])["metrics"]["cost_usd"])

    def test_threshold_boundary(self):
        old = [{"task_id": "a", "passed": True}, {"task_id": "b", "passed": True}]
        new = [old[0], {"task_id": "b", "passed": False}]
        self.assertTrue(compare_runs(old, new, 0.5)["gate_passed"])

    def test_invalid_threshold(self):
        row = {"task_id": "a", "passed": True}
        for value in (-0.1, 1.1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_runs([row], [row], value)
