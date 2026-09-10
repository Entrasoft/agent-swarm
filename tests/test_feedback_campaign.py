"""One-use feedback study guards exercised with local providers only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from swarm_lab import feedback_campaign
from swarm_lab.cli import read_events, verify_replay
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE


ORDER = ["history_feedback", "private_best_only", "private_best_only",
         "history_feedback", "history_feedback", "private_best_only"]
BASE_KEYS = {"m", "agent_id", "role", "round", "private_best", "mailbox",
             "peers", "condition", "task_id"}


def terra_price(**changes):
    price = dict(OFFLINE_PRICE, provider="openai", model="gpt-5.6-terra", simulated=False,
                 input_per_million="2", cached_input_per_million="0.2",
                 cache_write_per_million="2.5", output_per_million="12",
                 source_url="https://developers.openai.com/api/docs/pricing",
                 verified_on=time.strftime("%Y-%m-%d"))
    price.update(changes)
    return price


def result(observation, *, candidate=None, input_tokens=100, output_tokens=20,
           outcome="completed", model="gpt-5.6-terra", tier="default"):
    return ProviderResult(
        dict(candidate=[1, 2, 4] if candidate is None else candidate,
             message=None, used_event_ids=[]),
        dict(input_tokens=input_tokens, output_tokens=output_tokens,
             input_tokens_details=dict(cached_tokens=0, cache_write_tokens=0),
             output_tokens_details=dict(reasoning_tokens=0)),
        request_id="local-feedback-fake", outcome=outcome, model=model, service_tier=tier)


class FakeProvider:
    def __init__(self, config, calls, respond, estimate=100):
        self.config, self.calls, self.respond = config, calls, respond
        self.input_estimate, self.local_calls = estimate, 0

    def estimate(self, observation):
        return self.input_estimate

    def call(self, observation):
        self.local_calls += 1
        self.calls.append(deepcopy(observation))
        return self.respond(observation, self.local_calls)


class FeedbackCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.directory = self.base / "feedback"
        self.calls = []
        # Tests must never claim a repository authorization or dispatch a request.
        for guard in (
            patch.object(feedback_campaign, "AUTHORIZATION_DIR", self.base / "authorizations"),
            patch("swarm_lab.feedback_campaign.print", create=True),
            patch("swarm_lab.providers.get_api_key", side_effect=AssertionError("credentials accessed")),
            patch("urllib.request.urlopen", side_effect=AssertionError("network accessed")),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def prepare(self, **price_changes):
        return feedback_campaign.prepare(self.directory, terra_price(**price_changes))

    def execute(self, respond=None, directory=None, estimate=100):
        respond = respond or (lambda observation, ordinal: result(observation))
        return feedback_campaign.execute(directory or self.directory, allow_live=True,
            provider_factory=lambda config: FakeProvider(config, self.calls, respond, estimate))

    def events(self, row):
        return read_events(self.directory / row["path"])

    def isolated_case(self, name):
        self.directory = self.base / name
        self.calls = []
        return patch.object(feedback_campaign, "AUTHORIZATION_DIR", self.base / (name + "-claims"))

    def test_prepare_allocates_six_fixed_runs_without_credentials_network_or_claim(self):
        manifest = self.prepare()
        self.assertEqual(manifest["authorization_id"], "terra-feedback-v02-2026-09-09")
        self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())
        self.assertFalse((self.directory / "execution-started.json").exists())
        self.assertEqual(manifest["limits"], dict(call_limit=72, token_limit=600_000, cost_limit="6.00"))
        self.assertEqual(manifest["run_limits"], dict(call_limit=12, token_limit=100_000, cost_limit="1.00"))
        self.assertEqual(manifest["schedule_seed"], 20260910)
        self.assertEqual([row["arm"] for row in manifest["runs"]], ORDER)
        self.assertEqual([row["order"] for row in manifest["runs"]], list(range(1, 7)))
        self.assertEqual([row["block"] for row in manifest["runs"]], [1, 1, 2, 2, 3, 3])
        self.assertEqual([row["seed"] for row in manifest["runs"]], [0, 0, 1, 1, 2, 2])
        identities = {row["run_id"] for row in manifest["runs"]}
        self.assertEqual(len(identities), 6)
        self.assertTrue(all(str(uuid.UUID(identity)) == identity for identity in identities))
        for row, config in zip(manifest["runs"], manifest["configs"]):
            self.assertEqual((config["m"], config["agents"], config["condition"]), (24, 1, "solo"))
            self.assertEqual((config["model"], config["reasoning_effort"]), ("gpt-5.6-terra", "medium"))
            self.assertEqual((config["steps"], config["max_output"], config["timeout_seconds"]), (12, 25_000, 120))
            self.assertEqual((config["max_retries"], config["concurrency"]), (0, 1))
            self.assertEqual((config["decision_protocol"], config["memory_mode"], config["history_limit"]),
                             ("feedback-v0.2", row["arm"], 8))
            self.assertEqual(config["context_bytes"], 16_384)
        self.assertGreaterEqual(len(manifest["documents"]), 3)
        report = json.loads((self.directory / "feedback-campaign.json").read_text())
        self.assertEqual(report["status"], "prepared")
        self.assertEqual([row["status"] for row in report["runs"]], ["unstarted"] * 6)
        groups = report["usage"]["groups"]["run_id"]
        self.assertEqual(set(groups), identities)
        for usage in groups.values():
            self.assertEqual(usage["token_limit"], 100_000)
            self.assertEqual(Decimal(usage["cost_limit"]), 1)
            self.assertEqual(usage["attempts"], 0)
        self.assertEqual(self.calls, [])

    def test_preparation_is_fresh_and_execution_requires_explicit_live_opt_in(self):
        self.prepare()
        with self.assertRaises((ValueError, FileExistsError)):
            self.prepare()
        factory = unittest.mock.Mock()
        with self.assertRaises(ValueError):
            feedback_campaign.execute(self.directory, provider_factory=factory)
        factory.assert_not_called()
        self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())
        stale = self.base / "stale"
        with self.assertRaises(ValueError):
            feedback_campaign.prepare(stale, terra_price(verified_on="2000-01-01"))
        self.assertFalse(stale.exists())

    def test_full_manifest_receipt_rejects_limits_configs_ids_documents_and_metadata_tampering(self):
        original = self.prepare()
        document = next(iter(original["documents"]))
        mutations = [
            lambda value: value["limits"].update(call_limit=73),
            lambda value: value["run_limits"].update(cost_limit="2.00"),
            lambda value: value["configs"][0].update(max_retries=1),
            lambda value: value["configs"][0].update(concurrency=2),
            lambda value: value["configs"][0].update(memory_mode="private_best_only"),
            lambda value: value["configs"][0].update(decision_protocol="legacy"),
            lambda value: value["runs"][0].update(run_id=str(uuid.uuid4())),
            lambda value: value["runs"][0].update(arm="private_best_only"),
            lambda value: value["runs"].reverse(),
            lambda value: value.update(schedule_seed=1),
            lambda value: value.update(code_revision="changed"),
            lambda value: value.update(prepared_at="changed descriptive field"),
            lambda value: value["source_sha256"].update({"runtime.py": "changed"}),
            lambda value: value["documents"][document].update(text="Changed after freezing."),
            lambda value: value["documents"][document].update(sha256="0" * 64),
        ]
        for index, mutate in enumerate(mutations):
            changed = deepcopy(original)
            mutate(changed)
            (self.directory / "manifest.json").write_text(json.dumps(changed))
            with self.subTest(mutation=index):
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())
                self.assertFalse((self.directory / "execution-started.json").exists())

    def test_missing_or_altered_allocations_are_not_recreated_at_execution(self):
        for name in ("missing", "changed", "deleted-run", "changed-campaign", "missing-receipt"):
            with self.subTest(ledger=name), self.isolated_case(name):
                manifest = self.prepare()
                path = self.directory / "usage.sqlite3"
                if name == "missing":
                    path.unlink()
                else:
                    with sqlite3.connect(path) as connection:
                        if name == "changed":
                            connection.execute("UPDATE runs SET token_limit=200000")
                        elif name == "deleted-run":
                            connection.execute("DELETE FROM runs WHERE run_id=?", (manifest["runs"][0]["run_id"],))
                        elif name == "changed-campaign":
                            connection.execute("UPDATE campaigns SET call_limit=73")
                        else:
                            connection.execute("DROP TABLE feedback_preparations")
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())

    def test_actual_source_or_document_changes_after_freezing_block_dispatch(self):
        self.prepare()
        changed_source = dict(feedback_campaign.source_hashes(), **{"runtime.py": "changed"})
        changed_documents = deepcopy(feedback_campaign._documents())
        first = next(iter(changed_documents))
        changed_documents[first]["text"] += "\nChanged after preparation."
        for attribute, changed in (("source_hashes", changed_source), ("_documents", changed_documents)):
            with self.subTest(changed=attribute), patch.object(feedback_campaign, attribute, return_value=changed):
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())
                self.assertEqual(self.calls, [])

    def test_real_dispatch_requires_the_clean_revision_recorded_at_preparation(self):
        revision = "a" * 40
        with patch.object(feedback_campaign, "_git_state", return_value=(revision, False)):
            self.prepare()
        for current in ((revision, True), ("b" * 40, False), ("unavailable", None)):
            with self.subTest(git_state=current), patch.object(feedback_campaign, "_git_state", return_value=current):
                with self.assertRaises(ValueError):
                    feedback_campaign.execute(self.directory, allow_live=True)
                self.assertFalse(feedback_campaign.AUTHORIZATION_DIR.exists())
                self.assertEqual(self.calls, [])

    def test_healthy_seventy_two_calls_have_bounded_own_history_and_independent_replay(self):
        manifest = self.prepare()
        report = self.execute(lambda observation, ordinal: result(observation, candidate=[ordinal]))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["usage"]["actual_calls"], 72)
        self.assertEqual(report["usage"]["remaining_calls"], 0)
        self.assertEqual(report["usage"]["total_tokens"], 8_640)
        self.assertEqual(report["usage"]["retry_attempts"], 0)
        self.assertEqual(report["usage"]["reserved_tokens"], 0)
        self.assertEqual(Decimal(report["usage"]["calculated_model_cost"]), Decimal("0.03168"))
        entries = json.loads((self.directory / "campaign-ledger.json").read_text())["entries"]
        self.assertEqual(len({entry["attempt_id"] for entry in entries}), 72)
        self.assertEqual({entry["run_id"] for entry in entries}, {row["run_id"] for row in manifest["runs"]})
        self.assertEqual({entry["attempt"] for entry in entries}, {0})
        for index, row in enumerate(report["runs"]):
            with self.subTest(order=row["order"], arm=row["arm"]):
                self.assertEqual(row["status"], "completed")
                summary = row["summary"]
                self.assertEqual(summary["decisions_attempted"], 12)
                self.assertEqual(summary["decisions_completed"], 12)
                self.assertEqual(summary["unique_valid_candidates"], 12)
                self.assertEqual(summary["duplicate_candidates"], 0)
                self.assertEqual(summary["messages"], 0)
                self.assertTrue(verify_replay(self.directory / row["path"])["verified"])
                observations = self.calls[index * 12:(index + 1) * 12]
                self.assertEqual(observations[0]["private_best"], [])
                for ordinal, observation in enumerate(observations):
                    self.assertEqual((observation["agent_id"], observation["role"], observation["condition"]),
                                     ("agent-0", "searcher", "solo"))
                    self.assertEqual(observation["peers"], [])
                    self.assertEqual(observation["mailbox"], [])
                    self.assertLessEqual(len(json.dumps(observation).encode()), 16_384)
                    if row["arm"] == "private_best_only":
                        self.assertEqual(set(observation), BASE_KEYS)
                    else:
                        self.assertEqual(set(observation), BASE_KEYS | {"attempt_history"})
                        history = observation["attempt_history"]
                        decisions = list(range(max(1, ordinal - 7), ordinal + 1))
                        self.assertEqual([entry["decision"] for entry in history], decisions)
                        self.assertEqual([entry["candidate"] for entry in history], [[n] for n in decisions])
                        self.assertTrue(all(entry["valid"] for entry in history))
                        self.assertLessEqual(len(history), 8)

    def test_invalid_mathematics_consumes_one_decision_then_both_arms_can_repair(self):
        self.prepare()
        report = self.execute(lambda observation, ordinal: result(observation,
                              candidate=[1, 2, 3] if ordinal == 1 else [1, 2, 4]))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["usage"]["actual_calls"], 72)
        self.assertEqual(report["usage"]["retry_attempts"], 0)
        for index, row in enumerate(report["runs"]):
            self.assertEqual(row["status"], "completed")
            self.assertEqual(row["summary"]["invalid_claims"], 1)
            self.assertEqual(row["summary"]["unique_valid_candidates"], 1)
            self.assertEqual(row["summary"]["duplicate_candidates"], 10)
            self.assertEqual(row["summary"]["decisions_completed"], 12)
            self.assertEqual(row["summary"]["best_candidate"], [1, 2, 4])
            after_invalid = self.calls[index * 12 + 1]
            self.assertEqual(after_invalid["private_best"], [])
            if row["arm"] == "history_feedback":
                previous = after_invalid["attempt_history"][0]
                self.assertFalse(previous["valid"])
                self.assertEqual(previous["candidate"], [1, 2, 3])
                self.assertEqual(previous["forbidden_triple"], [1, 2, 3])
            else:
                self.assertNotIn("attempt_history", after_invalid)
            self.assertTrue(verify_replay(self.directory / row["path"])["verified"])

    def test_known_protocol_and_provider_failures_end_only_the_current_run(self):
        for name in ("protocol", "incomplete", "refusal"):
            with self.subTest(failure=name), self.isolated_case(name):
                self.prepare()
                def respond(observation, ordinal):
                    response = result(observation, outcome="completed" if name == "protocol" else name)
                    if name == "protocol":
                        response.action["used_event_ids"] = [123456]
                    return response
                report = self.execute(respond)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(report["usage"]["actual_calls"], 6)
                self.assertEqual(report["usage"]["unknown_attempts"], 0)
                self.assertEqual(report["usage"]["retry_attempts"], 0)
                self.assertEqual({row["status"] for row in report["runs"]}, {"failed"})
                self.assertTrue(all(row.get("failure") for row in report["runs"]))
                self.assertTrue(all(row["summary"]["decisions_attempted"] == 1 for row in report["runs"]))
                self.assertTrue(all(row["summary"]["decisions_completed"] == 0 for row in report["runs"]))
                self.assertTrue(all(row["summary"]["unique_valid_candidates"] == 0 for row in report["runs"]))

    def test_per_run_token_or_cost_exhaustion_never_transfers_unused_allowances(self):
        cases = [("tokens", dict(input_tokens=30_000), 30_000, 2),
                 ("currency", dict(output_tokens=22_000), 100, 3)]
        for name, usage, estimate, expected_calls in cases:
            with self.subTest(ceiling=name), self.isolated_case(name):
                self.prepare()
                report = self.execute(lambda observation, ordinal: result(observation, **usage), estimate=estimate)
                self.assertEqual(report["status"], "completed")
                self.assertEqual(report["usage"]["actual_calls"], 6 * expected_calls)
                self.assertEqual({row["status"] for row in report["runs"]}, {"budget_stopped"})
                for row in report["runs"]:
                    run_usage = row["summary"]["usage"]
                    self.assertEqual(run_usage["actual_calls"], expected_calls)
                    self.assertEqual(run_usage["token_limit"], 100_000)
                    self.assertEqual(Decimal(run_usage["cost_limit"]), 1)
                    self.assertEqual(run_usage["token_overshoot"], 0)
                    self.assertEqual(Decimal(run_usage["cost_overshoot"]), 0)
                self.assertEqual(report["usage"]["reserved_tokens"], 0)
                self.assertEqual(report["usage"]["unknown_cost_attempts"], 0)

    def test_unknown_dispatch_usage_and_cache_counts_halt_all_runs_and_keep_reserves(self):
        for name in ("transport", "absent-usage", "negative-usage", "missing-cache-read", "missing-cache-write"):
            with self.subTest(failure=name), self.isolated_case(name):
                self.prepare()
                def respond(observation, ordinal):
                    if ordinal == 1:
                        return result(observation)
                    if name == "transport":
                        raise ProviderFailure("transport_unknown", "local-unknown",
                                              {"failure_category": "timeout"})
                    response = result(observation)
                    if name == "absent-usage":
                        response.usage = None
                    elif name == "negative-usage":
                        response.usage["input_tokens"] = -1
                    elif name == "missing-cache-read":
                        del response.usage["input_tokens_details"]["cached_tokens"]
                    else:
                        del response.usage["input_tokens_details"]["cache_write_tokens"]
                    return response
                report = self.execute(respond)
                self.assertEqual(report["status"], "halted")
                self.assertEqual(report["usage"]["actual_calls"], 2)
                self.assertEqual(report["usage"]["retry_attempts"], 0)
                self.assertIsNone(report["usage"]["calculated_model_cost"])
                self.assertEqual(len(report["runs"]), 6)
                self.assertEqual(len(report["usage"]["groups"]["run_id"]), 6)
                self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 5)
                self.assertTrue(all("summary" not in row for row in report["runs"][1:]))
                self.assertGreater(Decimal(report["usage"]["reserved_cost"]), 0)
                if name in {"transport", "absent-usage", "negative-usage"}:
                    self.assertEqual(report["usage"]["reserved_tokens"], 25_100)
                with self.assertRaises((ValueError, FileExistsError)):
                    self.execute()
                self.assertEqual(len(self.calls), 2)

    def test_missing_or_unexpected_model_and_tier_halt_before_candidate_acceptance(self):
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
                self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 5)
                events = self.events(report["runs"][0])
                returned = [event["payload"] for event in events if event["event_type"] == "provider_result"]
                self.assertEqual(len(returned), 1)
                self.assertEqual((returned[0]["model"], returned[0]["service_tier"]), (model, tier))
                self.assertEqual(returned[0]["usage"]["input_tokens"], 100)
                self.assertFalse(any(event["event_type"] == "candidate_submitted" for event in events))

    def test_observed_per_run_overage_halts_even_with_campaign_headroom(self):
        for name, usage in (("tokens", dict(input_tokens=100_000)), ("currency", dict(output_tokens=90_000))):
            with self.subTest(ceiling=name), self.isolated_case("overage-" + name):
                self.prepare()
                # Fault injection: telemetry can contradict the request estimate.
                report = self.execute(lambda observation, ordinal: result(observation, **usage))
                self.assertEqual(report["status"], "halted")
                self.assertEqual(report["stop_reason"], "run_ceiling_exceeded")
                self.assertEqual(report["usage"]["actual_calls"], 1)
                self.assertEqual(report["usage"]["token_overshoot"], 0)
                self.assertEqual(Decimal(report["usage"]["cost_overshoot"]), 0)
                run_usage = report["runs"][0]["summary"]["usage"]
                self.assertGreater(run_usage["token_overshoot"] if name == "tokens"
                                   else Decimal(run_usage["cost_overshoot"]), 0)
                self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 5)

    def test_concurrent_directories_can_claim_the_authorization_only_once(self):
        self.prepare()
        other = self.base / "other"
        feedback_campaign.prepare(other, terra_price())
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
        self.assertEqual(len(self.calls), 6)
        for directory in (self.directory, other):
            with self.assertRaises((ValueError, FileExistsError)):
                self.execute(directory=directory)
        self.assertEqual(len(self.calls), 6)

    def test_copy_of_prepared_directory_cannot_repeat_a_claimed_campaign(self):
        self.prepare()
        other = self.base / "copied-before-execution"
        shutil.copytree(self.directory, other)
        self.execute(lambda observation, ordinal: result(observation, outcome="incomplete"))
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute(directory=other)
        self.assertEqual(len(self.calls), 6)
        self.assertFalse((other / "execution-started.json").exists())

    def test_existing_execution_marker_blocks_dispatch_without_reset(self):
        self.prepare()
        (self.directory / "execution-started.json").write_text("{}")
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_provider_construction_failure_halts_with_zero_attempts_and_no_secret_text(self):
        self.prepare()
        secret_marker = "credential body must never appear"
        def factory(config):
            raise RuntimeError(secret_marker)
        report = feedback_campaign.execute(self.directory, allow_live=True, provider_factory=factory)
        self.assertEqual(report["status"], "halted")
        self.assertEqual(report["usage"]["actual_calls"], 0)
        self.assertEqual(report["usage"]["reserved_tokens"], 0)
        self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 5)
        self.assertNotIn(secret_marker, json.dumps(report))
        self.assertEqual(self.calls, [])
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()

    def test_independent_replay_failure_prevents_later_run_dispatch(self):
        self.prepare()
        with patch.object(feedback_campaign, "verify_replay", side_effect=ValueError("inconsistent evidence")):
            report = self.execute()
        self.assertEqual(report["status"], "halted")
        self.assertEqual(report["usage"]["actual_calls"], 12)
        self.assertEqual(report["usage"]["unknown_attempts"], 0)
        self.assertEqual(report["runs"][0]["status"], "interrupted")
        self.assertFalse(report["runs"][0]["replay"]["verified"])
        self.assertEqual([row["status"] for row in report["runs"]][1:], ["unstarted"] * 5)
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(len(self.calls), 12)


if __name__ == "__main__":
    unittest.main()
