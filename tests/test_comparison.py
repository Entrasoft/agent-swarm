"""Frozen comparison, allocation and dispatch safety with local fake providers only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from swarm_lab import comparison
from swarm_lab.cli import read_events, verify_replay
from swarm_lab.math_task import exact_optimum
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE


ORDER = [
    "independent", "fixed", "adaptive", "solo",
    "fixed", "adaptive", "independent", "solo",
    "independent", "solo", "adaptive", "fixed",
    "solo", "adaptive", "fixed", "independent",
    "fixed", "solo", "independent", "adaptive",
]


def terra_price(**changes):
    price = dict(OFFLINE_PRICE, provider="openai", model="gpt-5.6-terra", simulated=False,
                 input_per_million="2", cached_input_per_million="0.2",
                 cache_write_per_million="2.5", output_per_million="12",
                 source_url="https://developers.openai.com/api/docs/pricing",
                 verified_on=time.strftime("%Y-%m-%d"))
    price.update(changes)
    return price


def result(observation, *, candidate=None, message=None, input_tokens=100, output_tokens=20,
           outcome="completed", model="gpt-5.6-terra", tier="default"):
    return ProviderResult(
        dict(candidate=[1, 2, 4] if candidate is None else candidate, message=message,
             used_event_ids=[entry["event_id"] for entry in observation["mailbox"]]),
        dict(input_tokens=input_tokens, output_tokens=output_tokens,
             input_tokens_details=dict(cached_tokens=0, cache_write_tokens=0),
             output_tokens_details=dict(reasoning_tokens=0)),
        request_id="local-fake", outcome=outcome, model=model, service_tier=tier)


class FakeProvider:
    def __init__(self, config, calls, respond):
        self.config, self.calls, self.respond = config, calls, respond
        self.local_calls = 0

    def estimate(self, observation):
        return 100

    def call(self, observation):
        self.local_calls += 1
        self.calls.append(deepcopy(observation))
        return self.respond(observation, self.local_calls)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.directory = self.base / "comparison"
        self.calls = []
        # Never consume the actual repository authorization, even in concurrency tests.
        guard = patch.object(comparison, "AUTHORIZATION_DIR", self.base / "authorizations")
        guard.start()
        self.addCleanup(guard.stop)
        progress = patch("swarm_lab.comparison.print", create=True)
        progress.start()
        self.addCleanup(progress.stop)

    def prepare(self, **price_changes):
        return comparison.prepare(self.directory, terra_price(**price_changes))

    def execute(self, respond=None, directory=None):
        respond = respond or (lambda observation, ordinal: result(observation))
        return comparison.execute(directory or self.directory, allow_live=True,
            provider_factory=lambda config: FakeProvider(config, self.calls, respond))

    def events(self, row):
        return read_events(self.directory / row["path"])

    def isolated_case(self, name):
        self.directory = self.base / name
        self.calls = []
        return patch.object(comparison, "AUTHORIZATION_DIR", self.base / (name + "-claims"))

    def test_prepare_preallocates_twenty_equal_runs_without_credentials_or_network(self):
        with patch("swarm_lab.providers.get_api_key", side_effect=AssertionError("credentials accessed")), \
             patch("swarm_lab.credentials.get_api_key", side_effect=AssertionError("credentials accessed")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network accessed")):
            manifest = self.prepare()
        self.assertFalse(comparison.AUTHORIZATION_DIR.exists())
        self.assertFalse((self.directory / "execution-started.json").exists())
        self.assertEqual(manifest["limits"], dict(call_limit=240, token_limit=2_000_000, cost_limit="20.00"))
        self.assertEqual(manifest["run_limits"], dict(call_limit=12, token_limit=100_000, cost_limit="1.00"))
        self.assertEqual(manifest["schedule_seed"], 20260909)
        self.assertEqual([row["condition"] for row in manifest["runs"]], ORDER)
        self.assertEqual([row["order"] for row in manifest["runs"]], list(range(1, 21)))
        self.assertEqual([row["repetition"] for row in manifest["runs"]], [r for r in range(1, 6) for _ in range(4)])
        self.assertEqual([row["seed"] for row in manifest["runs"]], [r for r in range(5) for _ in range(4)])
        self.assertEqual(len({row["run_id"] for row in manifest["runs"]}), 20)
        for config in manifest["configs"]:
            self.assertEqual((config["m"], config["model"], config["reasoning_effort"]),
                             (24, "gpt-5.6-terra", "medium"))
            self.assertEqual((config["steps"], config["max_output"], config["timeout_seconds"]), (12, 25_000, 120))
            self.assertEqual((config["max_retries"], config["concurrency"]), (0, 1))
        report = json.loads((self.directory / "comparison.json").read_text())
        self.assertEqual(report["status"], "prepared")
        self.assertEqual({row["status"] for row in report["runs"]}, {"unstarted"})
        groups = report["usage"]["groups"]["run_id"]
        self.assertEqual(set(groups), {row["run_id"] for row in manifest["runs"]})
        for usage in groups.values():
            self.assertEqual(usage["token_limit"], 100_000)
            self.assertEqual(Decimal(usage["cost_limit"]), 1)
            self.assertEqual(usage["attempts"], 0)
        self.assertEqual(self.calls, [])

    def test_prepare_and_execute_require_fresh_scope_and_explicit_opt_in(self):
        self.prepare()
        with self.assertRaises((ValueError, FileExistsError)):
            self.prepare()
        with patch("swarm_lab.runtime.OpenAIProvider") as provider:
            with self.assertRaises(ValueError):
                comparison.execute(self.directory)
        provider.assert_not_called()
        self.assertFalse(comparison.AUTHORIZATION_DIR.exists())
        stale = self.base / "stale"
        with self.assertRaises(ValueError):
            comparison.prepare(stale, terra_price(verified_on="2000-01-01"))
        self.assertFalse(stale.exists())

    def test_frozen_limits_protocol_source_and_matrix_reject_mutation_before_claim(self):
        original = self.prepare()
        mutations = [
            lambda value: value["limits"].update(call_limit=241),
            lambda value: value["run_limits"].update(cost_limit="2.00"),
            lambda value: value["configs"][0].update(max_retries=1),
            lambda value: value["configs"][0].update(concurrency=2),
            lambda value: value["runs"][0].update(condition="solo"),
            lambda value: value["runs"][0].update(run_id=str(uuid.uuid4())),
            lambda value: value["runs"].reverse(),
            lambda value: value.update(schedule_seed=1),
            lambda value: value.update(code_revision="changed"),
            lambda value: value.update(full_output_headroom_tokens=1),
            lambda value: value.update(full_output_headroom_cost="0"),
            lambda value: value["source_sha256"].update({"runtime.py": "changed"}),
            lambda value: value.update(protocol=value["protocol"] + "\nChanged after freezing."),
        ]
        for index, mutate in enumerate(mutations):
            changed = deepcopy(original)
            mutate(changed)
            (self.directory / "manifest.json").write_text(json.dumps(changed))
            with self.subTest(mutation=index):
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse(comparison.AUTHORIZATION_DIR.exists())
                self.assertFalse((self.directory / "execution-started.json").exists())

    def test_missing_or_changed_durable_allocations_cannot_be_recreated_at_execution(self):
        for name in ("missing", "changed"):
            with self.subTest(ledger=name), self.isolated_case(name):
                self.prepare()
                path = self.directory / "usage.sqlite3"
                if name == "missing":
                    path.unlink()
                else:
                    with sqlite3.connect(path) as connection:
                        connection.execute("UPDATE runs SET token_limit=200000")
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse(comparison.AUTHORIZATION_DIR.exists())

    def test_full_matrix_accounts_coordinators_preserves_isolation_and_actual_message_order(self):
        manifest = self.prepare()
        optimum = list(exact_optimum(24).candidate)

        def respond(observation, ordinal):
            index = int(observation["agent_id"].split("-")[1])
            candidate = optimum if observation["role"] == "coordinator" else [index + 1]
            message = None
            if observation["condition"] in {"fixed", "adaptive"}:
                recipient = (1 if index == 0 else 0) if observation["condition"] == "fixed" else (index + 1) % 4
                message = dict(type="share_artifact", recipient=f"agent-{recipient}",
                               content=dict(candidate=candidate, assumptions="Local fake fixture"))
            return result(observation, candidate=candidate, message=message)

        report = self.execute(respond)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["usage"]["actual_calls"], 240)
        self.assertEqual(report["usage"]["total_tokens"], 28_800)
        self.assertEqual(report["usage"]["remaining_calls"], 0)
        self.assertEqual(report["usage"]["retry_attempts"], 0)
        self.assertEqual(report["usage"]["reserved_tokens"], 0)
        self.assertEqual(report["usage"]["groups"]["purpose"]["coordination"]["attempts"], 30)
        self.assertEqual([call["condition"] for call in self.calls], [condition for condition in ORDER for _ in range(12)])
        entries = json.loads((self.directory / "campaign-ledger.json").read_text())["entries"]
        self.assertEqual(len({entry["attempt_id"] for entry in entries}), 240)
        self.assertEqual({entry["run_id"] for entry in entries}, {row["run_id"] for row in manifest["runs"]})
        self.assertEqual({entry["attempt"] for entry in entries}, {0})
        for index, row in enumerate(report["runs"]):
            with self.subTest(order=row["order"], condition=row["condition"]):
                self.assertEqual(row["status"], "completed")
                self.assertEqual(row["summary"]["run_id"], manifest["runs"][index]["run_id"])
                self.assertEqual(row["summary"]["decisions_completed"], 12)
                self.assertTrue(verify_replay(self.directory / row["path"])["verified"])
                observations = self.calls[index * 12:(index + 1) * 12]
                roster = ["agent-0"] if row["condition"] == "solo" else [f"agent-{a}" for a in range(4)]
                self.assertEqual([call["agent_id"] for call in observations], (roster * 12)[:12])
                self.assertTrue(all(call["private_best"] == [] for call in observations[:len(roster)]))
                self.assertEqual(observations[0]["mailbox"], [])
                self.assertTrue(all(set(call) == {"m", "agent_id", "role", "round", "private_best", "mailbox", "peers", "condition", "task_id"}
                                    for call in observations))
                if row["condition"] in {"solo", "independent"}:
                    self.assertEqual(row["summary"]["messages"], 0)
                    self.assertTrue(all(call["mailbox"] == [] for call in observations))
                    for call in observations[len(roster):]:
                        self.assertEqual(call["private_best"], [int(call["agent_id"].split("-")[1]) + 1])
                else:
                    self.assertEqual(row["summary"]["gap"], 0)
                    self.assertEqual(row["summary"]["best_candidate"], optimum)
                    self.assertEqual(row["summary"]["messages"], 12)
                    self.assertEqual(observations[1]["mailbox"][0]["actor"], "agent-0")
                    events = self.events(row)
                    delivery = next(e for e in events if e["event_type"] == "message_delivered")
                    later_observation = next(e for e in events if e["event_type"] == "observation" and e["actor"] == "agent-1")
                    self.assertLess(delivery["event_id"], later_observation["event_id"])
                    self.assertEqual(later_observation["payload"]["mailbox"][0]["event_id"], delivery["event_id"])
        self.assertEqual(Decimal(report["usage"]["calculated_model_cost"]), Decimal("0.1056"))

    def test_per_run_token_and_currency_limits_never_reallocate_underspend(self):
        for name, usage in (("tokens", dict(input_tokens=30_000)), ("currency", dict(output_tokens=22_000))):
            with self.subTest(ceiling=name), self.isolated_case(name):
                self.prepare()
                report = self.execute(lambda observation, ordinal: result(observation, **usage))
                self.assertEqual(report["status"], "completed")
                self.assertEqual(len(report["runs"]), 20)
                self.assertEqual(report["usage"]["actual_calls"], 60)
                self.assertEqual({row["status"] for row in report["runs"]}, {"budget_stopped"})
                for row in report["runs"]:
                    run_usage = row["summary"]["usage"]
                    self.assertEqual(run_usage["actual_calls"], 3)
                    self.assertEqual(run_usage["token_limit"], 100_000)
                    self.assertEqual(Decimal(run_usage["cost_limit"]), 1)
                    self.assertEqual(run_usage["token_overshoot"], 0)
                    self.assertEqual(Decimal(run_usage["cost_overshoot"]), 0)
                self.assertEqual(report["usage"]["reserved_tokens"], 0)
                self.assertEqual(report["usage"]["unknown_cost_attempts"], 0)

    def test_known_invalid_or_incomplete_response_ends_only_that_run_without_replacements(self):
        for name in ("invalid", "incomplete"):
            with self.subTest(failure=name), self.isolated_case(name):
                self.prepare()
                def respond(observation, ordinal):
                    return result(observation, candidate=[1, 2, 3]) if name == "invalid" else result(observation, outcome="incomplete")
                report = self.execute(respond)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(report["usage"]["actual_calls"], 20)
                self.assertEqual(report["usage"]["unknown_attempts"], 0)
                self.assertEqual(report["usage"]["retry_attempts"], 0)
                self.assertEqual([call["condition"] for call in self.calls], ORDER)
                self.assertEqual({row["status"] for row in report["runs"]}, {"failed"})
                self.assertTrue(all(row.get("failure") for row in report["runs"]))
                self.assertTrue(all(row["summary"]["gap"] > 0 for row in report["runs"]))

    def test_observed_run_overage_halts_even_when_campaign_still_has_headroom(self):
        # Deliberately inconsistent fake usage tests the accounting guard rather
        # than assuming a provider always respects its requested output limit.
        cases = (("tokens", dict(input_tokens=100_000)),
                 ("currency", dict(output_tokens=90_000)))
        for name, usage in cases:
            with self.subTest(ceiling=name), self.isolated_case("overage-" + name):
                self.prepare()
                report = self.execute(lambda observation, ordinal: result(observation, **usage))
                self.assertEqual(report["status"], "halted")
                self.assertEqual(report["stop_reason"], "run_ceiling_exceeded")
                self.assertEqual(report["usage"]["actual_calls"], 1)
                self.assertEqual(report["usage"]["unknown_attempts"], 0)
                self.assertEqual(report["usage"]["token_overshoot"], 0)
                self.assertEqual(Decimal(report["usage"]["cost_overshoot"]), 0)
                run_usage = report["runs"][0]["summary"]["usage"]
                self.assertGreater(run_usage["token_overshoot"] if name == "tokens"
                                   else Decimal(run_usage["cost_overshoot"]), 0)
                self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 19)

    def test_unknown_or_malformed_usage_halts_campaign_retaining_all_allocations(self):
        for name in ("unknown", "malformed", "unpriced"):
            with self.subTest(usage=name), self.isolated_case(name):
                self.prepare()
                def respond(observation, ordinal):
                    if ordinal == 1:
                        return result(observation)
                    if name == "unknown":
                        raise ProviderFailure("transport_unknown", "local-unknown")
                    response = result(observation)
                    if name == "malformed":
                        response.usage["input_tokens"] = -1
                    else:
                        del response.usage["input_tokens_details"]["cache_write_tokens"]
                    return response
                report = self.execute(respond)
                self.assertEqual(report["status"], "halted")
                self.assertEqual(report["usage"]["actual_calls"], 2)
                self.assertEqual(report["usage"]["retry_attempts"], 0)
                self.assertIsNone(report["usage"]["calculated_model_cost"])
                self.assertEqual(len(report["runs"]), 20)
                self.assertEqual(len(report["usage"]["groups"]["run_id"]), 20)
                self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 19)
                self.assertTrue(all("summary" not in row for row in report["runs"][1:]))
                self.assertGreater(Decimal(report["usage"]["reserved_cost"]), 0)
                if name != "unpriced":
                    self.assertEqual(report["usage"]["reserved_tokens"], 25_100)
                with self.assertRaises((ValueError, FileExistsError)):
                    self.execute()
                self.assertEqual(len(self.calls), 2)

    def test_missing_or_unexpected_model_and_tier_preserve_usage_but_halt_before_candidate(self):
        cases = [("other-model", "default"), (None, "default"),
                 ("gpt-5.6-terra", "priority"), ("gpt-5.6-terra", None)]
        for index, (model, tier) in enumerate(cases):
            with self.subTest(model=model, tier=tier), self.isolated_case(f"identity-{index}"):
                self.prepare()
                report = self.execute(lambda observation, ordinal: result(observation, model=model, tier=tier))
                self.assertEqual(report["status"], "halted")
                self.assertEqual(report["usage"]["actual_calls"], 1)
                self.assertEqual(report["usage"]["unknown_attempts"], 1)
                self.assertEqual(report["usage"]["reserved_tokens"], 25_100)
                self.assertEqual(len(report["runs"]), 20)
                events = self.events(report["runs"][0])
                returned = [event["payload"] for event in events if event["event_type"] == "provider_result"]
                self.assertEqual(len(returned), 1)
                self.assertEqual((returned[0]["model"], returned[0]["service_tier"]), (model, tier))
                self.assertEqual(returned[0]["usage"]["input_tokens"], 100)
                self.assertFalse(any(event["event_type"] == "candidate_submitted" for event in events))

    def test_optimal_candidate_does_not_erase_later_known_failure(self):
        self.prepare()
        optimum = list(exact_optimum(24).candidate)
        report = self.execute(lambda observation, ordinal: result(observation, candidate=optimum,
                             outcome="completed" if ordinal == 1 else "incomplete"))
        self.assertEqual(report["usage"]["actual_calls"], 40)
        self.assertEqual({row["status"] for row in report["runs"]}, {"failed"})
        self.assertTrue(all(row.get("failure") for row in report["runs"]))
        for row in report["runs"]:
            self.assertEqual(row["summary"]["gap"], 0)
            self.assertEqual(row["summary"]["stopping_reason"], "provider_failure")
            self.assertEqual(row["summary"]["decisions_completed"], 1)

    def test_concurrent_directories_and_subsequent_repeats_share_one_authorization(self):
        self.prepare()
        other = self.base / "other"
        comparison.prepare(other, terra_price())
        barrier = threading.Barrier(2)
        def start(directory):
            barrier.wait(timeout=5)
            try:
                return self.execute(lambda observation, ordinal: result(observation, outcome="incomplete"), directory)
            except (ValueError, FileExistsError):
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as executor:
            reports = list(executor.map(start, [self.directory, other]))
        self.assertEqual(reports.count("blocked"), 1)
        self.assertEqual(len(self.calls), 20)
        for directory in (self.directory, other):
            with self.assertRaises((ValueError, FileExistsError)):
                self.execute(directory=directory)
        self.assertEqual(len(self.calls), 20)

    def test_existing_execution_marker_blocks_dispatch_without_reset(self):
        self.prepare()
        (self.directory / "execution-started.json").write_text("{}")
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
