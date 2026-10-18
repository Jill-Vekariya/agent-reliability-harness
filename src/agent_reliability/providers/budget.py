"""Atomic USD accounting; unresolved charges remain reserved after failures."""

import sqlite3
import uuid
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any


def micros(amount: str | Decimal) -> int:
    value = Decimal(amount)
    if not value.is_finite() or value < 0:
        raise ValueError("Amount must be finite and nonnegative")
    return int((value * 1000000).to_integral_value(rounding=ROUND_CEILING))


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path, cap_usd: str, task_cap_usd: str) -> None:
        self.path, self.cap, self.task_cap = path, micros(cap_usd), micros(task_cap_usd)
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, task TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, state TEXT NOT NULL)"
            )

    def reserve(self, task: str, upper_bound_usd: str) -> str:
        amount = micros(upper_bound_usd)
        if amount <= 0 or self.cap <= 0:
            raise BudgetExceeded("Nonzero authorized budget and safe positive bound required")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            # Unknown settlements freeze further spending until reconciled.
            if conn.execute("SELECT COUNT(*) FROM reservations WHERE state='unknown'").fetchone()[
                0
            ]:
                raise BudgetExceeded("Unresolved provider charge; reconcile before more requests")
            total = conn.execute(
                "SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM reservations"
            ).fetchone()[0]
            per_task = conn.execute(
                "SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM reservations WHERE task=?",
                (task,),
            ).fetchone()[0]
            if total + amount > self.cap or per_task + amount > self.task_cap:
                raise BudgetExceeded("Campaign or task cap exceeded")
            key = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO reservations VALUES(?,?,?,NULL,'reserved')", (key, task, amount)
            )
            return key

    def reconcile(self, key: str, actual_usd: str | None) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT reserved,state FROM reservations WHERE id=?", (key,)
            ).fetchone()
            if row is None or row[1] == "settled":
                raise ValueError("Unknown or already settled reservation")
            if actual_usd is None:
                conn.execute("UPDATE reservations SET state='unknown' WHERE id=?", (key,))
                return
            amount = micros(actual_usd)
            if amount > row[0]:
                conn.execute("UPDATE reservations SET state='unknown' WHERE id=?", (key,))
                conn.commit()
                raise BudgetExceeded("Actual charge exceeded conservative reservation")
            conn.execute(
                "UPDATE reservations SET actual=?, state='settled' WHERE id=?", (amount, key)
            )

    def summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            settled, unresolved = conn.execute(
                "SELECT COALESCE(SUM(actual),0), COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0) FROM reservations"
            ).fetchone()
        return {
            "settled_usd": str(Decimal(settled) / 1000000),
            "reserved_usd": str(Decimal(unresolved) / 1000000),
            "cap_usd": str(Decimal(self.cap) / 1000000),
        }
