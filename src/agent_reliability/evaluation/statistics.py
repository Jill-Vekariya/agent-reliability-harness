import math
import random
from collections import defaultdict
from collections.abc import Callable
from typing import Any


def pass_at_k(n: int, c: int, k: int) -> float:
    if not (0 <= c <= n and 1 <= k <= n):
        raise ValueError("pass@k requires 0<=c<=n and 1<=k<=n")
    return 1.0 if n - c < k else 1 - math.comb(n - c, k) / math.comb(n, k)


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def family_bootstrap(
    rows: list[dict[str, Any]],
    statistic: Callable[[list[dict[str, Any]]], float],
    resamples: int = 10000,
    seed: int = 20261018,
) -> tuple[float, float]:
    if not rows:
        raise ValueError("No observations")
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        families[row["family_id"]].append(row)
    keys = sorted(families)
    rng = random.Random(seed)
    samples = [
        statistic([r for key in rng.choices(keys, k=len(keys)) for r in families[key]])
        for _ in range(resamples)
    ]
    return float(quantile(samples, 0.025)), float(quantile(samples, 0.975))  # type: ignore[arg-type]


def paired_difference(
    a: list[dict[str, Any]], b: list[dict[str, Any]], resamples: int = 10000
) -> dict[str, Any]:
    def key(r: dict[str, Any]) -> tuple[Any, Any]:
        return r["task_id"], r["repetition"]

    left, right = {key(r): r for r in a}, {key(r): r for r in b}
    if len(left) != len(a) or len(right) != len(b) or left.keys() != right.keys():
        raise ValueError("Paired configurations need identical unique task/repetition coverage")
    rows = []
    for k in left:
        if left[k]["family_id"] != right[k]["family_id"]:
            raise ValueError("Family assignment changed")
        rows.append(
            {
                "family_id": left[k]["family_id"],
                "difference": int(right[k]["correct"]) - int(left[k]["correct"]),
            }
        )

    def average(sample: list[dict[str, Any]]) -> float:
        return sum(r["difference"] for r in sample) / len(sample)

    return {"effect": average(rows), "ci95": family_bootstrap(rows, average, resamples=resamples)}


def live_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Replays/regression retain live origin but are not fresh measurements.
    eligible = [
        r
        for r in rows
        if r["origin"] == "live" and r["mode"] == "record" and r["category"] == "ordinary"
    ]
    if len({r["attempt_id"] for r in eligible}) != len(eligible):
        raise ValueError("Duplicate fresh attempts")
    if not eligible:
        return {"status": "not yet measured", "fresh_ordinary_attempts": 0}
    tasks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        tasks[row["task_id"]].append(row)

    def success(sample: list[dict[str, Any]]) -> float:
        return sum(r["correct"] for r in sample) / len(sample)

    complete = {
        k: v for k, v in tasks.items() if len(v) == 5 and len({r["repetition"] for r in v}) == 5
    }
    rate = sum(r["correct"] for r in eligible) / len(eligible)
    costs = [float(r["cost_usd"]) for r in eligible if r.get("cost_usd") is not None]
    successes = sum(r["correct"] for r in eligible)
    latency = [float(r["latency_ms"]) for r in eligible]
    result: dict[str, Any] = {
        "status": "measured",
        "fresh_ordinary_attempts": len(eligible),
        "tasks": len(tasks),
        "families": len({r["family_id"] for r in eligible}),
        "operational_success_rate": rate,
        "success_ci95": family_bootstrap(eligible, success),
        "complete_five_attempt_tasks": len(complete),
        "pass_at_1": None,
        "pass_at_5": None,
        "flakiness": None,
        "all_five_success": None,
        "latency_p50_ms": quantile(latency, 0.5),
        "latency_p95_ms": quantile(latency, 0.95),
        "mean_cost_usd": sum(costs) / len(eligible) if len(costs) == len(eligible) else None,
        "cost_per_success_usd": sum(costs) / successes
        if len(costs) == len(eligible) and successes
        else None,
    }
    if len(complete) == len(tasks):
        counts = [sum(r["correct"] for r in group) for group in complete.values()]
        result.update(
            pass_at_1=sum(c / 5 for c in counts) / len(counts),
            pass_at_5=sum(c > 0 for c in counts) / len(counts),
            flakiness=sum(0 < c < 5 for c in counts) / len(counts),
            all_five_success=sum(c == 5 for c in counts) / len(counts),
        )
        task_rows = [
            {
                "family_id": group[0]["family_id"],
                "pass_at_1": count / 5,
                "pass_at_5": float(count > 0),
                "flakiness": float(0 < count < 5),
                "all_five_success": float(count == 5),
            }
            for group, count in zip(complete.values(), counts, strict=True)
        ]
        for name in ("pass_at_1", "pass_at_5", "flakiness", "all_five_success"):

            def average_task_metric(sample: list[dict[str, Any]], metric: str = name) -> float:
                return sum(float(r[metric]) for r in sample) / len(sample)

            result[name + "_ci95"] = family_bootstrap(task_rows, average_task_metric)
    for probability, name in ((0.5, "p50"), (0.95, "p95")):

        def latency_quantile(sample: list[dict[str, Any]], p: float = probability) -> float:
            value = quantile([float(r["latency_ms"]) for r in sample], p)
            assert value is not None
            return value

        result["latency_" + name + "_ci95_ms"] = family_bootstrap(eligible, latency_quantile)
    if len(costs) == len(eligible):
        result["mean_cost_ci95_usd"] = family_bootstrap(
            eligible, lambda sample: sum(float(r["cost_usd"]) for r in sample) / len(sample)
        )
    return result
