"""Durable attempt accounting and atomic run-budget admission, without dependencies.

Prices are frozen per run. Token counters follow OpenAI's inclusive semantics:
cache reads and writes are disjoint subsets of input; reasoning is a subset of
output. Calculated cost estimates observed usage; only ``reconcile`` records billed money.
Missing usage retains the reservation, including for failed/cancelled attempts.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator


ZERO = Decimal("0")
MILLION = Decimal("1000000")
RATE_FIELDS = ("input_per_million", "cached_input_per_million", "output_per_million",
               "cache_write_per_million")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _money(value: Any, name: str = "amount") -> Decimal:
    # Floating-point prices defeat the reason for a decimal financial ledger.
    if isinstance(value, (bool, float)):
        raise ValueError(f"{name} must be a decimal string, integer, or Decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _amount(value: Decimal) -> str:
    return format(value, "f")


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _scrub(value: Any) -> Any:
    """Preserve usage metadata while removing common credential-bearing fields."""
    forbidden = {"authorization", "api_key", "apikey", "access_token", "refresh_token",
                 "secret", "client_secret", "password", "cookie", "set_cookie", "token"}
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if str(key).lower().replace("-", "_") in forbidden
                          else _scrub(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize inclusive counters; partial/missing totals remain unknown."""
    result: dict[str, Any] = {"input_tokens": None, "output_tokens": None,
                              "cached_input_tokens": None, "cache_write_tokens": None,
                              "reasoning_tokens": None,
                              "total_tokens": None, "complete": False}
    if usage is None:
        return result
    if not isinstance(usage, dict):
        raise ValueError("usage must be an object or None")
    for key in ("input_tokens", "output_tokens"):
        if usage.get(key) is not None:
            result[key] = _count(usage[key], key)
    for details, key, output in (("input_tokens_details", "cached_tokens", "cached_input_tokens"),
                                 ("input_tokens_details", "cache_write_tokens", "cache_write_tokens"),
                                 ("output_tokens_details", "reasoning_tokens", "reasoning_tokens")):
        source = usage.get(details)
        source = {} if source is None else source
        if not isinstance(source, dict):
            raise ValueError(f"{details} must be an object")
        if source.get(key) is not None:
            result[output] = _count(source[key], output)
    for subset, total in (("cached_input_tokens", "input_tokens"),
                          ("cache_write_tokens", "input_tokens"),
                          ("reasoning_tokens", "output_tokens")):
        if result[subset] is not None and result[total] is not None and result[subset] > result[total]:
            raise ValueError(f"{subset} cannot exceed {total}")
    if (result["input_tokens"] is not None and
            (result["cached_input_tokens"] or 0) + (result["cache_write_tokens"] or 0) > result["input_tokens"]):
        raise ValueError("cache reads + cache writes cannot exceed input_tokens")
    if result["input_tokens"] is not None and result["output_tokens"] is not None:
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
        result["complete"] = True
        if usage.get("total_tokens") is not None:
            if _count(usage["total_tokens"], "total_tokens") != result["total_tokens"]:
                raise ValueError("total_tokens disagrees with input_tokens + output_tokens")
    return result


def _cost(price: dict[str, Any], input_tokens: int, output_tokens: int,
          cached_tokens: int | None = 0, cache_write_tokens: int | None = None,
          *, reservation: bool = False) -> Decimal | None:
    """Price only disjoint per-million token buckets; never invent missing rates."""
    rates = {field: None if price.get(field) is None else _money(price[field], field)
             for field in RATE_FIELDS}
    input_rate, cached_rate, output_rate, write_rate = (rates[field] for field in RATE_FIELDS)
    write_accounting = "cache_write_per_million" in price or bool(cache_write_tokens)
    if reservation:
        # Any input could be an ordinary token, cache read, or cache write.
        # A missing applicable rate makes the bound unknown, never zero.
        input_rates = [input_rate, cached_rate] + ([write_rate] if write_accounting else [])
        input_rate = None if any(rate is None for rate in input_rates) else max(input_rates)
        cached_tokens = cache_write_tokens = 0
    elif write_accounting and input_tokens and (cached_tokens is None or cache_write_tokens is None):
        # New tariffs require disjoint counters. The API docs do not define
        # absent write telemetry as zero. Preserve the conservative reservation.
        return None
    cached_tokens = cached_tokens or 0
    cache_write_tokens = cache_write_tokens or 0
    buckets = ((input_tokens - cached_tokens - cache_write_tokens, input_rate),
               (cached_tokens, cached_rate), (cache_write_tokens, write_rate),
               (output_tokens, output_rate))
    if any(tokens and rate is None for tokens, rate in buckets):
        return None
    return sum((Decimal(tokens) * (rate or ZERO) for tokens, rate in buckets), ZERO) / MILLION


class Ledger:
    """SQLite-backed accounting; safe across threads, processes, and restarts.

    ``reserve`` returns False when a ceiling blocks admission. Repeating an
    identical attempt ID is idempotent; it is not a second dispatch authorization.
    Dispatch ownership belongs to the runtime. Different retry attempts need new
    IDs and share their ``logical_call_id``. All currency values are strings.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), timeout=30, isolation_level=None,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                token_limit INTEGER NOT NULL, cost_limit TEXT NOT NULL,
                price_json TEXT NOT NULL, simulated INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
                agent TEXT NOT NULL, task_id TEXT NOT NULL, logical_call_id TEXT NOT NULL,
                attempt INTEGER NOT NULL, purpose TEXT NOT NULL, model TEXT NOT NULL,
                service_tier TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                input_estimate INTEGER NOT NULL, max_output INTEGER NOT NULL,
                estimated_tokens INTEGER NOT NULL, estimated_cost TEXT,
                context_estimates_json TEXT NOT NULL, outcome TEXT NOT NULL,
                status TEXT NOT NULL, request_id TEXT, usage_json TEXT,
                normalized_json TEXT NOT NULL, observed_cost TEXT, reconciled_cost TEXT,
                reserved_tokens INTEGER NOT NULL, reserved_cost TEXT NOT NULL,
                UNIQUE(run_id, logical_call_id, attempt)
            );
            CREATE INDEX IF NOT EXISTS attempts_run ON attempts(run_id, created_at);
            CREATE TABLE IF NOT EXISTS corrections (
                correction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                timestamp TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL,
                before_json TEXT, after_json TEXT NOT NULL
            );
        """)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    @staticmethod
    def _run(db: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        result = dict(row)
        result["price"] = json.loads(result.pop("price_json"))
        result["simulated"] = bool(result["simulated"])
        return result

    @staticmethod
    def _entry(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for key in ("context_estimates", "usage", "normalized"):
            value = result.pop(f"{key}_json")
            result[key] = json.loads(value) if value is not None else None
        # Existing databases retain their frozen legacy tariff and counters.
        result["normalized"].setdefault("cache_write_tokens", None)
        result.update(result["normalized"])
        return result

    def create_run(self, run_id: str, token_limit: int, cost_limit: str,
                   price: dict[str, Any], simulated: bool) -> None:
        token_limit = _count(token_limit, "token_limit")
        ceiling = _amount(_money(cost_limit, "cost_limit"))
        frozen = json.loads(_json(_scrub(price)))
        for field in RATE_FIELDS:
            if frozen.get(field) is not None:
                frozen[field] = _amount(_money(frozen[field], field))
        if frozen.get("rate_units", "per_million_tokens") != "per_million_tokens":
            raise ValueError("this ledger supports per_million_tokens pricing only")
        if not simulated and frozen.get("simulated"):
            raise ValueError("simulated prices cannot be used for a real run")
        parameters = (token_limit, ceiling, _json(frozen), int(simulated))
        with self._transaction() as db:
            old = db.execute("SELECT token_limit,cost_limit,price_json,simulated FROM runs WHERE run_id=?",
                             (run_id,)).fetchone()
            if old is not None:
                if tuple(old) != parameters:
                    raise ValueError("run already exists with a different budget or frozen price")
                return
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                       (run_id, _now(), *parameters))

    def reserve(self, run_id: str, attempt_id: str, agent: str, task_id: str,
                logical_call_id: str, attempt: int, purpose: str, input_estimate: int,
                max_output: int, model: str, service_tier: str = "default",
                context_estimates: dict[str, Any] | None = None) -> bool:
        input_estimate = _count(input_estimate, "input_estimate")
        max_output = _count(max_output, "max_output")
        attempt = _count(attempt, "attempt")
        context = context_estimates or {}
        for key, value in context.items():
            _count(value, f"context_estimates.{key}")
        if sum(context.values()) > input_estimate:
            raise ValueError("context component estimates exceed input_estimate")
        parameters = dict(run_id=run_id, agent=agent, task_id=task_id, logical_call_id=logical_call_id,
                          attempt=attempt, purpose=purpose, input_estimate=input_estimate,
                          max_output=max_output, model=model, service_tier=service_tier,
                          context_estimates_json=_json(context))
        with self._transaction() as db:
            run = self._run(db, run_id)
            old = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if old is not None:
                if any(old[key] != value for key, value in parameters.items()):
                    raise ValueError("attempt_id already exists with different request parameters")
                return True
            price = run["price"]
            if price.get("model") and price["model"] != model:
                raise ValueError("request model differs from the run's frozen price model")
            if price.get("service_tier") and price["service_tier"] != service_tier:
                raise ValueError("request tier differs from the run's frozen price tier")
            estimate = _cost(price, input_estimate, max_output, reservation=True)
            # Unpriced work consumes the full currency ceiling; it never admits
            # parallel unpriced work by pretending the rate is zero.
            reserved_cost = estimate if estimate is not None else _money(run["cost_limit"])
            entries = [self._entry(row) for row in db.execute("SELECT * FROM attempts WHERE run_id=?", (run_id,))]
            committed = self._aggregate(entries)
            tokens = input_estimate + max_output
            if (committed["committed_tokens"] + tokens > run["token_limit"] or
                    _money(committed["committed_cost"]) + reserved_cost > _money(run["cost_limit"])):
                return False
            # With no price or currency allowance, unknown cost is not admissible.
            if estimate is None and reserved_cost == 0:
                return False
            now = _now()
            data = dict(attempt_id=attempt_id, **parameters, created_at=now, updated_at=now,
                        estimated_tokens=tokens, estimated_cost=None if estimate is None else _amount(estimate),
                        outcome="pending", status="estimated", request_id=None, usage_json=None,
                        normalized_json=_json(normalize_usage(None)), observed_cost=None,
                        reconciled_cost=None, reserved_tokens=tokens, reserved_cost=_amount(reserved_cost))
            columns = ",".join(data)
            placeholders = ",".join("?" for _ in data)
            try:
                db.execute(f"INSERT INTO attempts ({columns}) VALUES ({placeholders})", tuple(data.values()))
            except sqlite3.IntegrityError as exc:
                raise ValueError("logical call attempt number is already reserved under a different ID") from exc
            return True

    def settle(self, attempt_id: str, outcome: str, usage: dict[str, Any] | None,
               request_id: str | None = None) -> None:
        """Record telemetry once; late missing telemetry may be completed safely."""
        self._settle(attempt_id, outcome, usage, request_id, correction_reason=None)

    def correct(self, attempt_id: str, usage: dict[str, Any] | None, reason: str,
                outcome: str | None = None, request_id: str | None = None) -> None:
        """Explicitly correct telemetry, retaining an immutable before/after audit."""
        if not reason.strip():
            raise ValueError("a correction reason is required")
        self._settle(attempt_id, outcome, usage, request_id, correction_reason=reason)

    def _settle(self, attempt_id: str, outcome: str | None, usage: dict[str, Any] | None,
                request_id: str | None, correction_reason: str | None) -> None:
        clean_usage = _scrub(usage)
        normalized = normalize_usage(clean_usage)
        with self._transaction() as db:
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown attempt: {attempt_id}")
            old = self._entry(row)
            run = self._run(db, old["run_id"])
            outcome = outcome or old["outcome"]
            if not isinstance(outcome, str) or not outcome.strip():
                raise ValueError("outcome is required")
            if old["request_id"] is not None and request_id is not None and old["request_id"] != request_id:
                raise ValueError("provider request ID cannot change for a single attempt")
            request_id = request_id or old["request_id"]
            if old["usage"] == clean_usage and old["outcome"] == outcome and old["request_id"] == request_id:
                return
            if old["normalized"]["complete"] and correction_reason is None:
                if old["usage"] != clean_usage or old["outcome"] != outcome:
                    raise ValueError("conflicting telemetry; use correct() with a reason")
            # Partial counters can increase exposure, but never release the
            # original reservation before both totals have been reported.
            observed = (_cost(run["price"], normalized["input_tokens"], normalized["output_tokens"],
                              normalized["cached_input_tokens"], normalized["cache_write_tokens"])
                        if normalized["complete"] else None)
            partial_input = max(old["input_estimate"], normalized["input_tokens"] or 0)
            partial_output = max(old["max_output"], normalized["output_tokens"] or 0)
            reserved_tokens = 0 if normalized["complete"] else partial_input + partial_output
            if old["reconciled_cost"] is not None or observed is not None:
                reserved_cost = ZERO
            else:
                reserve_estimate = _cost(run["price"], partial_input, partial_output,
                                         cache_write_tokens=normalized["cache_write_tokens"], reservation=True)
                reserved_cost = (_money(run["cost_limit"]) if reserve_estimate is None else
                                 max(reserve_estimate, _money(old["reserved_cost"])))
            status = ("reconciled" if old["reconciled_cost"] is not None else
                      "observed" if normalized["complete"] else "estimated")
            update = dict(outcome=outcome, status=status, request_id=request_id, usage=clean_usage,
                          normalized=normalized, observed_cost=None if observed is None else _amount(observed),
                          reserved_tokens=reserved_tokens, reserved_cost=_amount(reserved_cost))
            db.execute("""UPDATE attempts SET outcome=?,status=?,request_id=?,usage_json=?,normalized_json=?,
                          observed_cost=?,reserved_tokens=?,reserved_cost=?,updated_at=? WHERE attempt_id=?""",
                       (outcome, status, request_id, None if clean_usage is None else _json(clean_usage),
                        _json(normalized), update["observed_cost"], reserved_tokens, _amount(reserved_cost),
                        _now(), attempt_id))
            kind = "correction" if correction_reason else ("late_telemetry" if old["outcome"] != "pending" else "telemetry")
            db.execute("INSERT INTO corrections(attempt_id,timestamp,kind,reason,before_json,after_json) VALUES(?,?,?,?,?,?)",
                       (attempt_id, _now(), kind, correction_reason or "provider usage telemetry",
                        _json(old), _json(update)))

    def reconcile(self, attempt_id: str, charge: str, currency: str | None = None,
                  reason: str = "billing statement") -> None:
        """Attach the final billed charge; corrected bills preserve their history."""
        charge = _amount(_money(charge, "charge"))
        if not reason.strip():
            raise ValueError("a reconciliation reason is required")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown attempt: {attempt_id}")
            old = self._entry(row)
            run = self._run(db, old["run_id"])
            if currency is not None and currency != run["price"].get("currency", "USD"):
                raise ValueError("billing currency differs from run currency")
            if old["reconciled_cost"] is not None and Decimal(old["reconciled_cost"]) == Decimal(charge):
                return
            db.execute("UPDATE attempts SET reconciled_cost=?,status='reconciled',reserved_cost='0',updated_at=? WHERE attempt_id=?",
                       (charge, _now(), attempt_id))
            db.execute("INSERT INTO corrections(attempt_id,timestamp,kind,reason,before_json,after_json) VALUES(?,?,?,?,?,?)",
                       (attempt_id, _now(), "reconciliation", reason, _json(old), _json({"reconciled_cost": charge})))

    def _entries(self, db: sqlite3.Connection, run: dict[str, Any]) -> list[dict[str, Any]]:
        entries = [self._entry(row) for row in db.execute("SELECT * FROM attempts WHERE run_id=? ORDER BY created_at,attempt_id", (run["run_id"],))]
        for entry in entries:
            entry["simulated"] = run["simulated"]
            entry["provider"] = run["price"].get("provider")
            entry["price_version"] = run["price"].get("version")
            entry["currency"] = run["price"].get("currency", "USD")
            entry["context_accounting"] = "estimated"
            if entry["input_tokens"] == 0:
                entry["cache_accounting"] = "no input tokens"
            elif "cache_write_per_million" in run["price"] or entry["cache_write_tokens"]:
                reported = entry["cached_input_tokens"] is not None and entry["cache_write_tokens"] is not None
                entry["cache_accounting"] = ("reported_disjoint_subsets" if reported
                                              else "incomplete subsets; cost unknown")
            else:
                entry["cache_accounting"] = "reported_subset" if entry["cached_input_tokens"] is not None else "unreported; priced as uncached"
            entry["corrections"] = [dict(item) for item in db.execute(
                "SELECT correction_id,timestamp,kind,reason,before_json,after_json FROM corrections WHERE attempt_id=? ORDER BY correction_id",
                (entry["attempt_id"],))]
        return entries

    def entries(self, run_id: str) -> list[dict[str, Any]]:
        with self._transaction() as db:
            return self._entries(db, self._run(db, run_id))

    @staticmethod
    def _aggregate(entries: list[dict[str, Any]]) -> dict[str, Any]:
        complete = [entry for entry in entries if entry["normalized"]["complete"]]
        observed = sum((Decimal(entry["observed_cost"]) for entry in entries if entry["observed_cost"] is not None), ZERO)
        reconciled = sum((Decimal(entry["reconciled_cost"]) for entry in entries if entry["reconciled_cost"] is not None), ZERO)
        known = sum((Decimal(entry["reconciled_cost"] if entry["reconciled_cost"] is not None else entry["observed_cost"])
                     for entry in entries if entry["reconciled_cost"] is not None or entry["observed_cost"] is not None), ZERO)
        reserved = sum((Decimal(entry["reserved_cost"]) for entry in entries), ZERO)
        tokens = sum(entry["normalized"]["total_tokens"] for entry in complete)
        result = {
            "attempts": len(entries), "pending_attempts": sum(entry["outcome"] == "pending" for entry in entries),
            "unknown_attempts": len(entries) - len(complete),
            "unpriced_attempts": sum(entry["observed_cost"] is None and entry["reconciled_cost"] is None and entry["normalized"]["complete"] for entry in entries),
            "input_tokens": sum(entry["normalized"]["input_tokens"] for entry in complete),
            "output_tokens": sum(entry["normalized"]["output_tokens"] for entry in complete),
            "cached_input_tokens": sum(entry["normalized"]["cached_input_tokens"] or 0 for entry in complete),
            "cache_write_tokens": sum(entry["normalized"]["cache_write_tokens"] or 0 for entry in complete),
            "reasoning_tokens": sum(entry["normalized"]["reasoning_tokens"] or 0 for entry in complete),
            "cache_reporting_attempts": sum(entry["normalized"]["cached_input_tokens"] is not None for entry in complete),
            "cache_write_reporting_attempts": sum(entry["normalized"]["cache_write_tokens"] is not None for entry in complete),
            "missing_cache_pricing_attempts": sum(entry["normalized"]["cached_input_tokens"] is None and
                                                   entry["normalized"]["input_tokens"] > 0 and
                                                   entry["observed_cost"] is not None for entry in complete),
            "reasoning_reporting_attempts": sum(entry["normalized"]["reasoning_tokens"] is not None for entry in complete),
            "total_tokens": tokens,
            "reserved_tokens": sum(entry["reserved_tokens"] for entry in entries),
            "estimated_tokens": sum(entry["estimated_tokens"] for entry in entries),
            "estimated_cost": _amount(sum((Decimal(entry["estimated_cost"]) for entry in entries if entry["estimated_cost"] is not None), ZERO)),
            "observed_cost": _amount(observed), "reconciled_cost": _amount(reconciled),
            "known_cost": _amount(known), "reserved_cost": _amount(reserved),
            "committed_cost": _amount(known + reserved),
            "unresolved_charges": sum(entry["reconciled_cost"] is None for entry in entries),
            "retry_attempts": len(entries) - len({entry["logical_call_id"] for entry in entries}),
        }
        result["committed_tokens"] = tokens + result["reserved_tokens"]
        result["unknown_cost_attempts"] = sum(entry["observed_cost"] is None and entry["reconciled_cost"] is None for entry in entries)
        result["cost_total"] = None if result["unknown_cost_attempts"] else result["known_cost"]
        first_attempt = {}
        for entry in entries:
            key = entry["logical_call_id"]
            first_attempt[key] = min(first_attempt.get(key, entry["attempt"]), entry["attempt"])
        result["retry_cost"] = _amount(sum((Decimal(entry["reconciled_cost"] or entry["observed_cost"] or "0")
                                           for entry in entries if entry["attempt"] > first_attempt[entry["logical_call_id"]]), ZERO))
        result["billing_status"] = "reconciled" if entries and not result["unresolved_charges"] else "not_reconciled"
        return result

    def summary(self, run_id: str) -> dict[str, Any]:
        # One snapshot includes all attempts, so per-call totals and groups agree
        # even when another connection settles requests concurrently.
        with self._transaction() as db:
            run = self._run(db, run_id)
            entries = [self._entry(row) for row in db.execute("SELECT * FROM attempts WHERE run_id=? ORDER BY created_at,attempt_id", (run_id,))]
        return self._summary(run, entries)

    def _summary(self, run: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
        result = dict(run, **self._aggregate(entries))
        result["currency"] = run["price"].get("currency", "USD")
        result["actual_calls"] = 0 if run["simulated"] else len(entries)
        result["simulated_calls"] = len(entries) if run["simulated"] else 0
        result["calculated_model_cost"] = "0" if run["simulated"] else result["cost_total"]
        result["actual_model_cost"] = ("0" if run["simulated"] or not entries else
                                       result["reconciled_cost"] if not result["unresolved_charges"] else None)
        result["cost_semantics"] = "observed_cost is calculated from reported usage; reconciled_cost is a billing charge"
        result["remaining_tokens"] = max(0, run["token_limit"] - result["committed_tokens"])
        difference = Decimal(run["cost_limit"]) - Decimal(result["committed_cost"])
        result["remaining_cost"] = _amount(max(ZERO, difference))
        result["token_overshoot"] = max(0, result["committed_tokens"] - run["token_limit"])
        result["cost_overshoot"] = _amount(max(ZERO, -difference))
        result["overshoot_reason"] = ("Reported usage or reconciled charges exceeded the conservative pre-call reservation."
                                       if result["token_overshoot"] or difference < 0 else None)
        result["groups"] = {}
        for field in ("agent", "purpose", "model", "logical_call_id"):
            result["groups"][field] = {key: self._aggregate([entry for entry in entries if entry[field] == key])
                                       for key in sorted({entry[field] for entry in entries})}
        result["timeline"] = []
        # A reservation-ordered cumulative final-accounting projection. This is
        # explicitly not a historical balance at the timestamp of dispatch.
        for index, entry in enumerate(entries):
            cumulative = self._aggregate(entries[:index + 1])
            result["timeline"].append({"timestamp": entry["created_at"], "attempt_id": entry["attempt_id"],
                                        "agent": entry["agent"], "status": entry["status"],
                                        "total_tokens": cumulative["total_tokens"], "known_cost": cumulative["known_cost"],
                                        "committed_tokens": cumulative["committed_tokens"],
                                        "committed_cost": cumulative["committed_cost"]})
        result["timeline_basis"] = "attempt dispatch order; cumulative latest accounting, not historical balances"
        result["usage_semantics"] = "cache reads and writes are disjoint subsets of input; reasoning is included in output"
        return result

    def export(self, run_id: str, directory: str | Path) -> dict[str, str]:
        """Export an internally consistent JSON/CSV ledger and run summary."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            run = self._run(db, run_id)
            entries = self._entries(db, run)
        summary = self._summary(run, entries)
        paths = {"json": directory / "usage-ledger.json", "csv": directory / "usage-ledger.csv",
                 "summary": directory / "usage-summary.json"}
        paths["json"].write_text(json.dumps({"schema_version": 1, "run_id": run_id,
                                             "price": summary["price"], "entries": entries}, indent=2) + "\n", encoding="utf-8")
        paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        fields = ["attempt_id", "run_id", "agent", "task_id", "logical_call_id", "attempt", "purpose",
                  "provider", "model", "service_tier", "price_version", "currency", "simulated", "created_at",
                  "updated_at", "request_id", "outcome", "status", "input_estimate", "max_output", "estimated_tokens",
                  "estimated_cost", "input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens", "total_tokens",
                  "observed_cost", "reconciled_cost", "reserved_tokens", "reserved_cost", "context_estimates", "usage"]
        with paths["csv"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for entry in entries:
                writer.writerow({key: _json(value) if isinstance(value, (dict, list)) else value
                                 for key, value in entry.items()})
        return {key: str(path) for key, path in paths.items()}
