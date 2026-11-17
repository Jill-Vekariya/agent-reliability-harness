import unittest

from agent_reliability.diagnostics import summarize


def trace(attempt="a", latency=10, cost="0.10", **extra):
    return {
        "schema_version": 1,
        "task_id": "task",
        "attempt_id": attempt,
        "termination": "finished",
        "latency_ms": latency,
        "cost_usd": cost,
        **extra,
    }


class TraceDiagnosticsTests(unittest.TestCase):
    def test_exact_decimal_cost(self):
        report = summarize([trace(), trace("b", cost="0.20")])
        self.assertEqual(report["cost_usd"], "0.30")

    def test_unknown_cost_is_not_zero(self):
        report = summarize([trace(), trace("b", cost=None)])
        self.assertIsNone(report["cost_usd"])
        self.assertEqual(report["traces_with_known_cost"], 1)

    def test_nearest_rank_percentiles(self):
        report = summarize([trace(str(i), i) for i in range(1, 21)])
        self.assertEqual(report["latency_ms"], {"p50": 10, "p95": 19, "max": 20})

    def test_sql_health_counters(self):
        results = {
            "r1": {"ok": False, "blocked": True},
            "r2": {"ok": False, "resource_limited": True},
            "r3": {"ok": True, "truncated": True},
        }
        report = summarize([trace(results=results, infrastructure_error="private error text")])
        expected = {
            "sql_results": 3,
            "sql_failures": 2,
            "blocked_results": 1,
            "resource_limited_results": 1,
            "truncated_results": 1,
            "infrastructure_errors": 1,
        }
        for key, value in expected.items():
            self.assertEqual(report[key], value)
        self.assertNotIn("private error text", str(report))

    def test_duplicate_attempt_rejected(self):
        with self.assertRaises(ValueError):
            summarize([trace(), trace()])

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            summarize([])

    def test_invalid_latencies(self):
        for value in (-1, True, None, "10", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize([trace(latency=value)])

    def test_invalid_costs(self):
        for value in ("-1", "NaN", "Infinity", "bad", 0.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize([trace(cost=value)])

    def test_invalid_result_flags(self):
        with self.assertRaises(ValueError):
            summarize([trace(results={"r1": {"ok": True, "blocked": "false"}})])

    def test_schema_rejected(self):
        with self.assertRaises(ValueError):
            summarize([trace(schema_version=2)])

    def test_payloads_not_emitted(self):
        events = [{"payload": {"sql": "secret SQL"}}]
        final = {"rows": [["secret row"]]}
        report = summarize([trace(events=events, final=final)])
        self.assertNotIn("secret", str(report))
