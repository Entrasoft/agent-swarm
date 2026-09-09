"""Campaign ceilings cover all runs and survive unknown outcomes and restarts."""

import csv
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from swarm_lab.ledger import Ledger


PRICE = dict(provider="test", model="test-model", service_tier="default", currency="USD",
             version="test-v1", input_per_million="2", cached_input_per_million="0.20",
             cache_write_per_million="2.50", output_per_million="12")


class CampaignLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "campaign.sqlite3"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def campaign(self, token_limit=1000, cost_limit="1", call_limit=6, **kwargs):
        args = dict(campaign_id="c", token_limit=token_limit, cost_limit=cost_limit,
                    call_limit=call_limit, price=PRICE, simulated=False)
        args.update(kwargs)
        self.ledger.create_campaign(**args)
        return args

    def make_run(self, run_id, **kwargs):
        args = dict(run_id=run_id, token_limit=1000, cost_limit="1", price=PRICE,
                    simulated=False, campaign_id="c")
        args.update(kwargs)
        self.ledger.create_run(**args)
        return args

    def reserve(self, run_id, attempt_id, ledger=None, **kwargs):
        args = dict(run_id=run_id, attempt_id=attempt_id, agent="searcher-0", task_id="task-0",
                    logical_call_id="call-0", attempt=0, purpose="search", input_estimate=100,
                    max_output=50, model="test-model")
        args.update(kwargs)
        return (ledger or self.ledger).reserve(**args)

    @staticmethod
    def usage(input_tokens=80, output_tokens=20):
        return dict(input_tokens=input_tokens, output_tokens=output_tokens,
                    input_tokens_details={"cached_tokens": 20, "cache_write_tokens": 30},
                    output_tokens_details={"reasoning_tokens": 10})

    def test_token_ceiling_covers_pending_across_runs(self):
        self.campaign(token_limit=299)
        self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        self.assertFalse(self.reserve("b", "b0"))
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(summary["remaining_tokens"], 149)
        self.assertEqual(summary["actual_calls"], 1)
        self.assertEqual(self.ledger.summary("b")["attempts"], 0)

    def test_cost_ceiling_covers_pending_across_runs(self):
        # Each admission reserves 100 * $2.50/M + 50 * $12/M = $0.00085.
        self.campaign(cost_limit="0.00169")
        self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        self.assertFalse(self.reserve("b", "b0"))
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(Decimal(summary["committed_cost"]), Decimal("0.00085"))
        self.assertEqual(Decimal(summary["remaining_cost"]), Decimal("0.00084"))

    def test_calls_are_not_released_by_zero_usage_or_failed_outcomes(self):
        self.campaign(call_limit=1)
        self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        self.ledger.settle("a0", "failed", {"input_tokens": 0, "output_tokens": 0})
        self.assertFalse(self.reserve("b", "b0"))
        # Idempotent telemetry is not permission to dispatch again.
        self.assertTrue(self.reserve("a", "a0"))
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(summary["remaining_calls"], 0)
        self.assertEqual(summary["actual_calls"], 1)
        self.assertEqual(summary["total_tokens"], 0)

    def test_run_ceiling_still_applies_under_larger_campaign(self):
        self.campaign()
        self.make_run("tokens", token_limit=149)
        self.make_run("money", cost_limit="0.00084")
        self.assertFalse(self.reserve("tokens", "a0"))
        self.assertFalse(self.reserve("money", "b0"))
        self.assertEqual(self.ledger.campaign_summary("c")["attempts"], 0)

    def test_concurrent_connections_cannot_both_admit_last_capacity(self):
        for name, limits in (("tokens", dict(token_limit=299)),
                             ("cost", dict(cost_limit="0.00169")),
                             ("calls", dict(call_limit=1))):
            with self.subTest(ceiling=name):
                self.campaign(campaign_id=name, **limits)
                self.make_run(name + "a", campaign_id=name)
                self.make_run(name + "b", campaign_id=name)
                barrier = threading.Barrier(2)
                with Ledger(self.path) as other:
                    def dispatch(run_id, ledger):
                        barrier.wait(timeout=5)
                        return self.reserve(run_id, run_id + "0", ledger=ledger)

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(dispatch, name + "a", self.ledger),
                                   pool.submit(dispatch, name + "b", other)]
                        results = [future.result(timeout=10) for future in futures]
                self.assertEqual(sorted(results), [False, True])
                self.assertEqual(self.ledger.campaign_summary(name)["attempts"], 1)

    def test_restart_preserves_unknown_holds_and_prior_membership(self):
        args = self.campaign(token_limit=299, call_limit=2)
        run_args = self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        self.ledger.settle("a0", "timed_out", None)
        before = self.ledger.campaign_summary("c")
        with Ledger(self.path) as reopened:
            reopened.create_campaign(**args)
            reopened.create_run(**run_args)
            self.assertEqual(before, reopened.campaign_summary("c"))
            self.assertFalse(self.reserve("b", "b0", ledger=reopened))
            reopened.settle("a0", "completed", self.usage())
            self.assertTrue(self.reserve("b", "b0", ledger=reopened))
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(summary["remaining_calls"], 0)
        self.assertEqual(summary["committed_tokens"], 250)

    def test_missing_cost_subsets_hold_campaign_currency_after_tokens_known(self):
        self.campaign(cost_limit="0.00169")
        self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        usage = self.usage()
        del usage["input_tokens_details"]["cache_write_tokens"]
        self.ledger.settle("a0", "completed", usage)
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(summary["unknown_attempts"], 0)
        self.assertEqual(summary["unpriced_attempts"], 1)
        self.assertIsNone(summary["calculated_model_cost"])
        self.assertFalse(self.reserve("b", "b0"))
        self.ledger.correct("a0", self.usage(), "provider supplied missing subset")
        self.assertTrue(self.reserve("b", "b0"))

    def test_frozen_campaign_cannot_change_limits_tariff_or_simulation(self):
        args = self.campaign()
        for change in (dict(token_limit=1001), dict(cost_limit="2"), dict(call_limit=7),
                       dict(price=dict(PRICE, output_per_million="1")), dict(simulated=True)):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    self.ledger.create_campaign(**dict(args, **change))

    def test_campaign_run_cannot_mix_tariff_model_tier_or_simulation(self):
        self.campaign()
        for change in (dict(price=dict(PRICE, model="other-model")),
                       dict(price=dict(PRICE, currency="CAD")),
                       dict(price=dict(PRICE, output_per_million="1")),
                       dict(simulated=True)):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    self.make_run("bad", **change)
        self.make_run("a")
        with self.assertRaises(ValueError):
            self.reserve("a", "a0", model="other-model")
        with self.assertRaises(ValueError):
            self.reserve("a", "a0", service_tier="flex")
        self.assertEqual(self.ledger.campaign_summary("c")["attempts"], 0)

    def test_missing_tariff_model_cannot_hide_mixed_models(self):
        price = {key: value for key, value in PRICE.items() if key != "model"}
        self.campaign(price=price)
        self.make_run("a", price=price)
        self.make_run("b", price=price)
        self.assertTrue(self.reserve("a", "a0"))
        with self.assertRaises(ValueError):
            self.reserve("b", "b0", model="other-model")

    def test_cannot_move_old_spend_into_or_out_of_campaign(self):
        self.campaign()
        self.campaign(campaign_id="new")
        legacy = self.make_run("legacy", campaign_id=None)
        self.assertTrue(self.reserve("legacy", "old0"))
        with self.assertRaises(ValueError):
            self.ledger.create_run(**dict(legacy, campaign_id="c"))
        member = self.make_run("member")
        self.assertTrue(self.reserve("member", "member0"))
        for target in (None, "new"):
            with self.assertRaises(ValueError):
                self.ledger.create_run(**dict(member, campaign_id=target))
        self.assertEqual(self.ledger.campaign_summary("new")["attempts"], 0)
        self.assertEqual(self.ledger.campaign_summary("c")["attempts"], 1)

    def test_aggregate_exports_and_per_run_groups_match_same_snapshot(self):
        self.campaign()
        for run_id in ("a", "b", "empty"):
            self.make_run(run_id)
        self.assertTrue(self.reserve("a", "a0"))
        self.ledger.settle("a0", "completed", self.usage())
        self.assertTrue(self.reserve("b", "b0"))
        self.ledger.settle("b0", "failed", None)
        summary = self.ledger.campaign_summary("c")
        self.assertEqual(summary["total_tokens"], 100)
        self.assertEqual(summary["committed_tokens"], 250)
        self.assertEqual(summary["unknown_attempts"], 1)
        self.assertEqual(summary["remaining_calls"], 4)
        self.assertEqual(summary["retry_attempts"], 0)  # Same logical ID in separate runs.
        self.assertEqual(summary["groups"]["run_id"]["a"], self.ledger.summary("a"))
        self.assertEqual(summary["groups"]["run_id"]["empty"]["attempts"], 0)
        for field in ("attempts", "total_tokens", "committed_tokens"):
            self.assertEqual(sum(run[field] for run in summary["groups"]["run_id"].values()), summary[field])
        self.assertEqual(sum(Decimal(run["committed_cost"]) for run in summary["groups"]["run_id"].values()),
                         Decimal(summary["committed_cost"]))
        paths = self.ledger.export_campaign("c", Path(self.temp.name) / "export")
        self.assertEqual(json.loads(Path(paths["summary"]).read_text()), summary)
        exported = json.loads(Path(paths["json"]).read_text())
        self.assertEqual(exported["campaign_id"], "c")
        self.assertEqual(exported["run_ids"], ["a", "b", "empty"])
        self.assertEqual(len(exported["entries"]), 2)
        with Path(paths["csv"]).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["run_id"] for row in rows], ["a", "b"])
        self.assertEqual(rows[1]["total_tokens"], "")

    def test_unpriced_usage_holds_full_campaign_even_with_small_run_limit(self):
        # Legacy tariff can become unpriced if the API reports a new charge type.
        price = {key: value for key, value in PRICE.items() if key != "cache_write_per_million"}
        self.campaign(price=price)
        self.make_run("a", price=price, cost_limit="0.01")
        self.make_run("b", price=price)
        self.assertTrue(self.reserve("a", "a0"))
        self.ledger.settle("a0", "completed", self.usage())
        self.assertEqual(self.ledger.campaign_summary("c")["reserved_cost"], "1")
        self.assertFalse(self.reserve("b", "b0"))

    def test_billing_overshoot_and_partial_token_overage_block_later_runs(self):
        self.campaign(token_limit=300, cost_limit="0.01")
        self.make_run("a")
        self.make_run("b")
        self.assertTrue(self.reserve("a", "a0"))
        self.ledger.settle("a0", "timed_out", {"input_tokens": 251})
        self.assertFalse(self.reserve("b", "b0"))
        self.assertEqual(self.ledger.campaign_summary("c")["token_overshoot"], 1)
        self.ledger.settle("a0", "completed", self.usage())
        self.ledger.reconcile("a0", "0.02")
        self.assertFalse(self.reserve("b", "b0"))
        self.assertEqual(Decimal(self.ledger.campaign_summary("c")["cost_overshoot"]), Decimal("0.01"))


if __name__ == "__main__":
    unittest.main()
