"""Consequential accounting tests; no network, SDK, or credentials needed."""

import csv
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from swarm_lab.ledger import Ledger, normalize_usage


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "usage-fixture.json"
PRICE = dict(provider="offline-fixture", model="fixture-v1", service_tier="default", currency="USD",
             version="offline-v1", effective_date="2026-09-09", retrieved_date="2026-09-09",
             source_url="offline fixture; not market prices", simulated=True,
             input_per_million="1", cached_input_per_million="0.25", output_per_million="2")
WRITE_PRICE = dict(PRICE, input_per_million="2", cached_input_per_million="0.20",
                   cache_write_per_million="2.50", output_per_million="12")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "usage.sqlite3"
        self.ledger = Ledger(self.path)
        self.ledger.create_run("r", 10000, "1", PRICE, True)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def reserve(self, attempt_id="a", **overrides):
        parameters = dict(run_id="r", attempt_id=attempt_id, agent="worker", task_id="task",
                          logical_call_id=attempt_id, attempt=0, purpose="research",
                          input_estimate=100, max_output=50, model="fixture-v1")
        parameters.update(overrides)
        return self.ledger.reserve(**parameters)

    def usage(self, input_tokens=100, output_tokens=20, cached=40, reasoning=10):
        return dict(input_tokens=input_tokens, output_tokens=output_tokens,
                    input_tokens_details={"cached_tokens": cached},
                    output_tokens_details={"reasoning_tokens": reasoning})

    def test_fixture_exact_arithmetic_and_all_aggregate_dimensions(self):
        fixture = json.loads(FIXTURE.read_text())
        run_id = fixture["run_id"]
        self.ledger.create_run(run_id, fixture["token_limit"], fixture["cost_limit"], fixture["price"], True)
        for attempt in fixture["attempts"]:
            fields = {key: attempt[key] for key in ("attempt_id", "agent", "task_id", "logical_call_id",
                                                    "attempt", "purpose", "input_estimate", "max_output")}
            self.assertTrue(self.ledger.reserve(run_id=run_id, model="fixture-v1", **fields))
            self.ledger.settle(attempt["attempt_id"], attempt["outcome"], attempt["usage"])
        result = self.ledger.summary(run_id)
        for key, expected in fixture["expected"].items():
            if isinstance(expected, str) and key not in {"billing_status"}:
                self.assertEqual(Decimal(result[key]), Decimal(expected), key)
            else:
                self.assertEqual(result[key], expected, key)
        entries = self.ledger.entries(run_id)
        for entry, expected in zip(entries, fixture["attempts"]):
            self.assertEqual(entry["observed_cost"], expected["expected_cost"])
        for dimension in ("agent", "purpose", "model", "logical_call_id"):
            groups = result["groups"][dimension].values()
            self.assertEqual(sum(group["total_tokens"] for group in groups), result["total_tokens"])
            self.assertEqual(sum(Decimal(group["committed_cost"]) for group in groups), Decimal(result["committed_cost"]))
        self.assertEqual(result["timeline"][-1]["known_cost"], result["known_cost"])
        self.assertEqual(result["timeline"][-1]["total_tokens"], result["total_tokens"])

    def test_subsets_not_added_twice_and_raw_metadata_preserved(self):
        self.reserve()
        usage = self.usage()
        usage["provider_annotation"] = {"cache": "read", "api_key": "not-a-real-secret"}
        self.ledger.settle("a", "completed", usage, "request-1")
        entry = self.ledger.entries("r")[0]
        self.assertEqual(entry["total_tokens"], 120)
        self.assertEqual(entry["observed_cost"], "0.00011")
        self.assertEqual(entry["request_id"], "request-1")
        self.assertEqual(entry["usage"]["provider_annotation"], {"cache": "read", "api_key": "[REDACTED]"})
        self.assertEqual(entry["cached_input_tokens"], 40)
        self.assertEqual(entry["reasoning_tokens"], 10)
        self.assertEqual(self.ledger.summary("r")["actual_model_cost"], "0")

    def test_cache_reads_and_writes_are_disjoint_priced_subsets(self):
        self.ledger.create_run("writes", 10000, "1", WRITE_PRICE, True)
        self.assertTrue(self.reserve(run_id="writes"))
        usage = self.usage()
        usage["input_tokens_details"]["cache_write_tokens"] = 30
        self.ledger.settle("a", "completed", usage)
        entry = self.ledger.entries("writes")[0]
        # 30 ordinary * 2 + 40 read * .20 + 30 write * 2.50 + 20 output * 12.
        self.assertEqual(Decimal(entry["observed_cost"]), Decimal("0.000383"))
        self.assertEqual(Decimal(entry["estimated_cost"]), Decimal("0.00085"))
        self.assertEqual(entry["total_tokens"], 120)
        self.assertEqual(entry["cache_write_tokens"], 30)
        self.assertEqual(entry["usage"], usage)
        self.assertEqual(entry["cache_accounting"], "reported_disjoint_subsets")
        result = self.ledger.summary("writes")
        self.assertEqual(result["cache_write_tokens"], 30)
        self.assertEqual(result["cache_write_reporting_attempts"], 1)
        self.assertEqual(result["reserved_cost"], "0")
        for groups in result["groups"].values():
            self.assertEqual(sum(group["cache_write_tokens"] for group in groups.values()), 30)
        paths = self.ledger.export("writes", Path(self.temp.name) / "writes-export")
        with Path(paths["csv"]).open(newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["cache_write_tokens"], "30")
        self.assertEqual(json.loads(row["usage"]), usage)

    def test_new_tariff_missing_cache_subset_retains_unknown_cost(self):
        for missing in ("cached_tokens", "cache_write_tokens"):
            with self.subTest(missing=missing):
                self.ledger.create_run(missing, 10000, "0.00085", WRITE_PRICE, True)
                self.assertTrue(self.reserve(missing, run_id=missing))
                usage = self.usage()
                usage["input_tokens_details"]["cache_write_tokens"] = 30
                del usage["input_tokens_details"][missing]
                self.ledger.settle(missing, "completed", usage)
                result = self.ledger.summary(missing)
                self.assertEqual(result["total_tokens"], 120)
                self.assertIsNone(result["cost_total"])
                self.assertEqual(result["unpriced_attempts"], 1)
                self.assertEqual(Decimal(result["reserved_cost"]), Decimal("0.00085"))
                entry = self.ledger.entries(missing)[0]
                self.assertEqual(entry["cache_accounting"], "incomplete subsets; cost unknown")
                self.assertFalse(self.reserve(f"next-{missing}", run_id=missing))
                usage["input_tokens_details"][missing] = 0
                self.ledger.correct(missing, usage, "provider supplied missing cache counter")
                self.assertIsNotNone(self.ledger.summary(missing)["cost_total"])
                self.assertEqual(self.ledger.summary(missing)["reserved_cost"], "0")

    def test_zero_input_requires_no_cache_counters_or_prices(self):
        self.ledger.create_run("empty-input", 10000, "1", dict(WRITE_PRICE,
            input_per_million=None, cached_input_per_million=None, cache_write_per_million=None), True)
        self.assertTrue(self.reserve(run_id="empty-input", input_estimate=0))
        self.ledger.settle("a", "completed", {"input_tokens": 0, "output_tokens": 20})
        self.assertEqual(self.ledger.summary("empty-input")["cost_total"], "0.00024")

    def test_cache_write_counts_are_validated_as_disjoint_subsets(self):
        for written, cached in ((-1, 0), (True, 0), (1.5, 0), (101, 0), (61, 40)):
            with self.subTest(written=written, cached=cached):
                usage = self.usage(cached=cached)
                usage["input_tokens_details"]["cache_write_tokens"] = written
                with self.assertRaises(ValueError):
                    normalize_usage(usage)
        for details in ([], False, "bad"):
            with self.assertRaises(ValueError):
                normalize_usage(dict(self.usage(), input_tokens_details=details))

    def test_missing_write_rate_is_unknown_and_blocks_parallel_admission(self):
        self.ledger.create_run("write-rate", 10000, "1", dict(WRITE_PRICE, cache_write_per_million=None), True)
        self.assertTrue(self.reserve(run_id="write-rate"))
        self.assertFalse(self.reserve("next", run_id="write-rate"))
        usage = self.usage()
        usage["input_tokens_details"]["cache_write_tokens"] = 30
        self.ledger.settle("a", "completed", usage)
        result = self.ledger.summary("write-rate")
        self.assertIsNone(result["cost_total"])
        self.assertEqual(result["reserved_cost"], "1")

    def test_unexpected_write_charge_on_legacy_tariff_holds_full_currency_ceiling(self):
        self.assertTrue(self.reserve())
        usage = self.usage()
        usage["input_tokens_details"]["cache_write_tokens"] = 30
        self.ledger.settle("a", "completed", usage)
        result = self.ledger.summary("r")
        self.assertIsNone(result["cost_total"])
        self.assertEqual(result["reserved_cost"], "1")
        self.assertFalse(self.reserve("next"))

    def test_existing_database_without_write_counter_keeps_legacy_cost(self):
        self.reserve()
        self.ledger.settle("a", "completed", self.usage())
        normalized = normalize_usage(self.usage())
        del normalized["cache_write_tokens"]
        self.ledger._db.execute("UPDATE attempts SET normalized_json=? WHERE attempt_id='a'",
                                (json.dumps(normalized),))
        with Ledger(self.path) as reopened:
            entry = reopened.entries("r")[0]
            self.assertIsNone(entry["cache_write_tokens"])
            self.assertEqual(entry["observed_cost"], "0.00011")
            self.assertEqual(reopened.summary("r")["cache_write_reporting_attempts"], 0)

    def test_ambiguous_timeout_cancel_failure_retains_reservation(self):
        for index, outcome in enumerate(("timed_out", "cancelled", "failed")):
            attempt = f"a{index}"
            self.reserve(attempt)
            self.ledger.settle(attempt, outcome, None)
        result = self.ledger.summary("r")
        self.assertEqual(result["unknown_attempts"], 3)
        self.assertEqual(result["reserved_tokens"], 450)
        self.assertEqual(Decimal(result["reserved_cost"]), Decimal("0.0006"))
        self.assertIsNone(result["cost_total"])
        self.assertTrue(all(entry["input_tokens"] is None for entry in self.ledger.entries("r")))

    def test_late_usage_releases_reservation_and_duplicates_are_idempotent(self):
        self.reserve()
        self.ledger.settle("a", "timed_out", None)
        self.ledger.settle("a", "completed", self.usage(), "request-1")
        before = self.ledger.summary("r")
        self.ledger.settle("a", "completed", self.usage(), "request-1")
        self.assertEqual(before, self.ledger.summary("r"))
        self.assertEqual(before["reserved_tokens"], 0)
        self.assertEqual(before["unknown_attempts"], 0)
        corrections = self.ledger.entries("r")[0]["corrections"]
        self.assertEqual([entry["kind"] for entry in corrections], ["telemetry", "late_telemetry"])

    def test_restart_and_idempotent_reservation_preserve_frozen_prices(self):
        self.reserve()
        with Ledger(self.path) as restarted:
            self.assertEqual(restarted.summary("r")["reserved_tokens"], 150)
            restarted.settle("a", "completed", self.usage())
        self.assertTrue(self.reserve())
        self.assertEqual(len(self.ledger.entries("r")), 1)
        self.ledger.create_run("r", 10000, "1", PRICE, True)
        with self.assertRaises(ValueError):
            self.ledger.create_run("r", 10000, "1", dict(PRICE, input_per_million="5"), True)
        with self.assertRaises(ValueError):
            self.reserve(input_estimate=101)

    def test_retry_has_new_attempt_and_shares_run_budget(self):
        self.reserve("first", logical_call_id="call", attempt=0)
        self.ledger.settle("first", "failed", self.usage())
        self.reserve("retry", logical_call_id="call", attempt=1)
        self.ledger.settle("retry", "completed", self.usage())
        summary = self.ledger.summary("r")
        self.assertEqual(summary["total_tokens"], 240)
        self.assertEqual(summary["retry_attempts"], 1)
        self.assertEqual(Decimal(summary["retry_cost"]), Decimal("0.00011"))
        with self.assertRaises(ValueError):
            self.reserve("duplicate", logical_call_id="call", attempt=1)

    def test_concurrent_token_reservations_across_connections(self):
        self.ledger.create_run("bounded", 1000, "1", PRICE, True)

        def admit(index):
            with Ledger(self.path) as connection:
                return connection.reserve("bounded", f"concurrent-{index}", f"a{index}", "t", str(index), 0,
                                          "research", 60, 40, "fixture-v1")

        with ThreadPoolExecutor(max_workers=12) as workers:
            admitted = list(workers.map(admit, range(40)))
        self.assertEqual(sum(admitted), 10)
        self.assertEqual(self.ledger.summary("bounded")["committed_tokens"], 1000)

    def test_concurrent_currency_reservations_are_exact_decimal(self):
        self.ledger.create_run("currency", 10000, "0.0006", PRICE, True)

        def admit(index):
            return self.ledger.reserve("currency", f"cost-{index}", "a", "t", str(index), 0,
                                       "coordination", 100, 0, "fixture-v1")

        with ThreadPoolExecutor(max_workers=12) as workers:
            admitted = list(workers.map(admit, range(40)))
        self.assertEqual(sum(admitted), 6)
        self.assertEqual(self.ledger.summary("currency")["remaining_cost"], "0")

    def test_concurrent_admission_reserves_most_expensive_input_bucket(self):
        for highest in ("input_per_million", "cached_input_per_million", "cache_write_per_million"):
            with self.subTest(highest=highest):
                price = dict(WRITE_PRICE, **{highest: "3"})
                self.ledger.create_run(highest, 10000, "0.0012", price, True)

                def admit(index):
                    with Ledger(self.path) as connection:
                        return connection.reserve(highest, f"{highest}-{index}", "a", "t", str(index),
                                                  0, "research", 100, 0, "fixture-v1")

                with ThreadPoolExecutor(max_workers=8) as workers:
                    admitted = list(workers.map(admit, range(16)))
                self.assertEqual(sum(admitted), 4)
                self.assertEqual(self.ledger.summary(highest)["remaining_cost"], "0")

    def test_conflicting_telemetry_requires_audited_correction(self):
        self.reserve()
        self.ledger.settle("a", "completed", self.usage())
        with self.assertRaises(ValueError):
            self.ledger.settle("a", "completed", self.usage(output_tokens=30))
        self.ledger.correct("a", self.usage(output_tokens=30), "provider corrected output count")
        self.assertEqual(self.ledger.summary("r")["total_tokens"], 130)
        entry = self.ledger.entries("r")[0]
        self.assertEqual(entry["corrections"][-1]["kind"], "correction")
        self.assertEqual(json.loads(entry["corrections"][-1]["before_json"])["total_tokens"], 120)

    def test_billing_reconciliation_separate_from_observed_cost(self):
        self.reserve()
        self.ledger.settle("a", "completed", self.usage())
        self.ledger.reconcile("a", "0.00012", currency="USD")
        self.ledger.reconcile("a", "0.00012", currency="USD")
        result = self.ledger.summary("r")
        self.assertEqual(Decimal(result["known_cost"]), Decimal("0.00012"))
        self.assertEqual(result["observed_cost"], "0.00011")
        self.assertEqual(result["billing_status"], "reconciled")
        self.assertEqual(len(self.ledger.entries("r")[0]["corrections"]), 2)
        with self.assertRaises(ValueError):
            self.ledger.reconcile("a", "0.00012", currency="EUR")

    def test_unknown_tokens_remain_reserved_after_bill_arrives(self):
        self.reserve()
        self.ledger.settle("a", "failed", None)
        self.ledger.reconcile("a", "0.00015")
        result = self.ledger.summary("r")
        self.assertEqual(result["reserved_tokens"], 150)
        self.assertEqual(result["reserved_cost"], "0")
        self.assertEqual(result["unknown_attempts"], 1)
        self.assertEqual(result["reconciled_cost"], "0.00015")

    def test_missing_prices_report_unpriced_and_hold_budget(self):
        self.ledger.create_run("unpriced", 1000, "1", dict(PRICE, input_per_million=None), True)
        self.reserve("unpriced-1", run_id="unpriced")
        self.assertFalse(self.reserve("unpriced-2", run_id="unpriced"))
        self.ledger.settle("unpriced-1", "completed", self.usage())
        result = self.ledger.summary("unpriced")
        self.assertEqual(result["total_tokens"], 120)
        self.assertEqual(result["unpriced_attempts"], 1)
        self.assertIsNone(result["cost_total"])
        self.assertEqual(result["reserved_cost"], "1")

    def test_overshoot_is_reported_and_prevents_more_admission(self):
        self.ledger.create_run("small", 100, "0.0001", PRICE, True)
        self.reserve("small-1", run_id="small", input_estimate=50, max_output=0)
        self.ledger.settle("small-1", "completed", self.usage(input_tokens=100, output_tokens=100, cached=0))
        result = self.ledger.summary("small")
        self.assertEqual(result["token_overshoot"], 100)
        self.assertEqual(Decimal(result["cost_overshoot"]), Decimal("0.0002"))
        self.assertIn("exceeded", result["overshoot_reason"])
        self.assertFalse(self.reserve("small-2", run_id="small", input_estimate=0, max_output=0))

    def test_partial_usage_is_unknown_and_preserved(self):
        self.reserve()
        self.ledger.settle("a", "failed", {"input_tokens": 100})
        result = self.ledger.summary("r")
        self.assertEqual(result["unknown_attempts"], 1)
        self.assertEqual(result["reserved_tokens"], 150)
        self.assertIsNone(result["cost_total"])
        self.assertEqual(self.ledger.entries("r")[0]["input_tokens"], 100)
        self.ledger.settle("a", "failed", self.usage())
        self.assertEqual(self.ledger.summary("r")["unknown_attempts"], 0)

    def test_context_is_estimated_without_an_additional_charge(self):
        self.reserve(context_estimates={"system": 20, "history": 30, "peer_messages": 50})
        self.ledger.settle("a", "completed", self.usage())
        result = self.ledger.summary("r")
        self.assertEqual(result["total_tokens"], 120)
        self.assertEqual(self.ledger.entries("r")[0]["context_accounting"], "estimated")
        with self.assertRaises(ValueError):
            self.reserve("bad", context_estimates={"system": 101})

    def test_partial_usage_above_estimate_increases_reserved_exposure(self):
        self.reserve()
        self.ledger.settle("a", "failed", {"input_tokens": 1000})
        result = self.ledger.summary("r")
        self.assertEqual(result["reserved_tokens"], 1050)
        self.assertEqual(Decimal(result["reserved_cost"]), Decimal("0.0011"))

    def test_missing_cache_subset_is_labeled_as_inferred_pricing(self):
        self.reserve()
        self.ledger.settle("a", "completed", {"input_tokens": 100, "output_tokens": 20})
        result = self.ledger.summary("r")
        self.assertEqual(result["missing_cache_pricing_attempts"], 1)
        self.assertEqual(result["observed_cost"], "0.00014")

    def test_exports_preserve_unknown_and_agree_with_summary(self):
        self.reserve()
        self.ledger.settle("a", "failed", None)
        paths = self.ledger.export("r", Path(self.temp.name) / "exports")
        entries = json.loads(Path(paths["json"]).read_text())["entries"]
        summary = json.loads(Path(paths["summary"]).read_text())
        with Path(paths["csv"]).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertIsNone(entries[0]["input_tokens"])
        self.assertEqual(rows[0]["input_tokens"], "")
        self.assertEqual(summary["committed_tokens"], sum(entry["reserved_tokens"] for entry in entries))
        self.assertEqual(summary["price"], PRICE)

    def test_strict_counters_price_units_and_model_tier(self):
        for usage in (self.usage(cached=101), self.usage(reasoning=21), {"input_tokens": -1},
                      {"input_tokens": True}, dict(self.usage(), total_tokens=160)):
            with self.assertRaises(ValueError):
                normalize_usage(usage)
        for cost in ("NaN", "Infinity", "-1", 0.1):
            with self.assertRaises(ValueError):
                self.ledger.create_run("bad", 100, cost, PRICE, True)
        with self.assertRaises(ValueError):
            self.reserve(model="wrong-model")
        with self.assertRaises(ValueError):
            self.reserve(service_tier="batch")
        with self.assertRaises(ValueError):
            self.ledger.create_run("bad", 100, "1", dict(PRICE, rate_units="per_thousand_tokens"), True)
        with self.assertRaises(ValueError):
            self.ledger.create_run("bad", 100, "1", PRICE, False)


if __name__ == "__main__":
    unittest.main()
