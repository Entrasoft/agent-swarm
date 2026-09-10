"""Feedback protocol behavior and spending failure boundaries, using local fakes.

No credential lookup or network request is permitted by any test in this module.
The fake usage exercises the real durable ledger without spending API credits.
"""

import asyncio
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from swarm_lab.cli import read_events, verify_replay
from swarm_lab.math_task import exact_optimum
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE, RunConfig, Runtime


BASE_OBSERVATION_KEYS = {
    "m", "agent_id", "role", "round", "private_best", "mailbox", "peers",
    "condition", "task_id",
}
HISTORY_KEYS = {
    "decision", "candidate", "valid", "reason", "forbidden_triple",
    "verification_event_id",
}


def action(candidate):
    return {"candidate": candidate, "message": None, "used_event_ids": []}


def response(value, *, outcome="completed", usage=True, model="gpt-5.6-terra",
             service_tier="default"):
    return ProviderResult(
        value,
        {
            "input_tokens": 100, "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        } if usage else None,
        request_id="local-feedback-fixture", outcome=outcome,
        model=model, service_tier=service_tier,
    )


class FakeProvider:
    """The original call(observation) interface remains usable by offline fakes."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.observations = []

    def estimate(self, observation):
        return 100

    def call(self, observation):
        self.observations.append(deepcopy(observation))
        value = self.responses[len(self.observations) - 1]
        if isinstance(value, BaseException):
            raise value
        return value


class FeedbackRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        for target in (
            "swarm_lab.providers.get_api_key", "swarm_lab.credentials.get_api_key",
            "urllib.request.urlopen",
        ):
            guard = patch(target, side_effect=AssertionError("offline tests must not access credentials or network"))
            guard.start()
            self.addCleanup(guard.stop)

    def config(self, **changes):
        price = dict(
            OFFLINE_PRICE, provider="openai", model="gpt-5.6-terra", simulated=False,
            input_per_million="2", cached_input_per_million="0.2",
            cache_write_per_million="2.5", output_per_million="12",
            source_url="https://developers.openai.com/api/docs/pricing",
            verified_on=time.strftime("%Y-%m-%d"),
        )
        values = dict(
            mode="live", allow_live=True, m=12, agents=1, condition="solo",
            concurrency=1, max_retries=0, steps=3, max_output=512,
            model="gpt-5.6-terra", reasoning_effort="medium", price=price,
            decision_protocol="feedback-v0.2", memory_mode="history_feedback",
        )
        values.update(changes)
        return RunConfig(**values)

    def run_case(self, responses, *, name="case", provider=None, stop_on_failure=False, **changes):
        fake = provider or FakeProvider(responses)
        directory = self.base / name
        config = self.config(steps=len(responses), **changes)
        summary = asyncio.run(Runtime(config, directory, provider=fake,
                                      stop_on_failure=stop_on_failure).run())
        return summary, read_events(directory), fake

    def test_invalid_attempt_receives_witness_then_repairs_without_free_retry(self):
        summary, events, fake = self.run_case([
            response(action([3, 1, 2])),
            response(action([4, 1, 2])),
        ])
        self.assertEqual(fake.observations[0]["attempt_history"], [])
        record = fake.observations[1]["attempt_history"][0]
        self.assertEqual(set(record), HISTORY_KEYS)
        self.assertEqual(record["decision"], 1)
        self.assertFalse(record["valid"])
        self.assertEqual(record["forbidden_triple"], [1, 2, 3])
        self.assertEqual(set(record["candidate"]), {1, 2, 3})
        self.assertIn("arithmetic progression", record["reason"])
        verification = next(event for event in events if event["event_id"] == record["verification_event_id"])
        self.assertEqual(verification["event_type"], "verification")
        self.assertEqual(verification["recipient"], "agent-0")
        self.assertFalse(verification["payload"]["valid"])
        feedback = next(event for event in events if event["event_type"] == "feedback_recorded")
        delivered = next(event for event in events if event["event_type"] == "feedback_read")
        self.assertEqual(feedback["payload"], record)
        self.assertEqual(feedback["parent_event_ids"], [verification["event_id"]])
        self.assertEqual(delivered["parent_event_ids"], [verification["event_id"]])
        self.assertEqual(delivered["task_id"], "task-1")
        self.assertEqual(delivered["actor"], "agent-0")
        self.assertEqual(fake.observations[1]["private_best"], [])
        self.assertEqual(summary["lower_bound"], 3)
        self.assertEqual(summary["best_candidate"], [1, 2, 4])
        self.assertEqual(summary["invalid_claims"], 1)
        self.assertEqual(summary["decisions_attempted"], 2)
        self.assertEqual(summary["decisions_completed"], 2)
        self.assertEqual(summary["usage"]["actual_calls"], 2)
        self.assertEqual(summary["usage"]["retry_attempts"], 0)
        self.assertEqual(summary["stopping_reason"], "step_limit")
        self.assertTrue(verify_replay(self.base / "case")["verified"])

    def test_duplicates_are_normalized_remembered_and_counted_separately_from_progress(self):
        summary, events, fake = self.run_case([
            response(action([4, 1, 2])), response(action([2, 4, 1])),
            response(action([1, 2, 4, 5])),
        ])
        history = fake.observations[2]["attempt_history"]
        self.assertEqual([entry["candidate"] for entry in history], [[1, 2, 4], [1, 2, 4]])
        self.assertEqual([entry["decision"] for entry in history], [1, 2])
        self.assertTrue(all(entry["valid"] and entry["forbidden_triple"] is None for entry in history))
        self.assertEqual(summary["unique_valid_candidates"], 2)
        self.assertEqual(summary["duplicate_candidates"], 1)
        self.assertEqual(summary["lower_bound"], 4)
        self.assertEqual(summary["memory_mode"], "history_feedback")
        self.assertEqual(summary["decision_protocol"], "feedback-v0.2")
        self.assertEqual(len([event for event in events if event["event_type"] == "verification"]), 3)

    def test_baseline_keeps_original_observation_and_same_invalid_math_continuation_rule(self):
        summary, _, fake = self.run_case([
            response(action([1, 2, 3])), response(action([4, 1, 2])),
            response(action([1, 2, 4, 5])),
        ], memory_mode="private_best_only")
        self.assertTrue(all(set(observation) == BASE_OBSERVATION_KEYS for observation in fake.observations))
        self.assertEqual([observation["private_best"] for observation in fake.observations],
                         [[], [], [1, 2, 4]])
        self.assertEqual(summary["decisions_attempted"], 3)
        self.assertEqual(summary["invalid_claims"], 1)
        self.assertEqual(summary["lower_bound"], 4)
        self.assertEqual(summary["memory_mode"], "private_best_only")

    def test_history_is_private_and_hidden_evaluation_happens_after_all_decisions(self):
        fake = FakeProvider([response(action([1])), response(action([2])), response(action([4]))])

        def hidden_evaluation(m, timeout):
            self.assertEqual(len(fake.observations), 3)
            return exact_optimum(m, timeout)

        with patch("swarm_lab.runtime.exact_optimum", side_effect=hidden_evaluation) as oracle:
            _, events, _ = self.run_case(fake.responses, provider=fake)
        oracle.assert_called_once()
        for observation in fake.observations:
            self.assertEqual(set(observation), BASE_OBSERVATION_KEYS | {"attempt_history"})
            self.assertEqual(observation["mailbox"], [])
            self.assertEqual(observation["peers"], [])
            for entry in observation["attempt_history"]:
                self.assertEqual(set(entry), HISTORY_KEYS)
                verification = next(event for event in events if event["event_id"] == entry["verification_event_id"])
                self.assertEqual(verification["recipient"], observation["agent_id"])
        evaluation_id = next(event["event_id"] for event in events if event["event_type"] == "evaluation")
        self.assertTrue(all(event["event_id"] < evaluation_id for event in events
                            if event["event_type"] == "observation"))

    def test_history_limit_keeps_latest_attempts_and_does_not_leak_between_runs(self):
        responses = [response(action([candidate])) for candidate in (1, 2, 4, 5, 7)]
        _, _, first = self.run_case(responses, history_limit=2)
        self.assertEqual([entry["decision"] for entry in first.observations[-1]["attempt_history"]], [3, 4])
        self.assertEqual([entry["candidate"] for entry in first.observations[-1]["attempt_history"]], [[4], [5]])
        _, _, second = self.run_case([response(action([10]))], name="fresh", history_limit=2)
        self.assertEqual(second.observations[0]["attempt_history"], [])
        self.assertEqual(second.observations[0]["private_best"], [])

    def test_context_limit_trims_whole_oldest_records_without_truncating_feedback(self):
        responses = [response(action([candidate])) for candidate in (1, 2, 4, 5, 7, 8)]
        _, _, fake = self.run_case(responses, history_limit=8, context_bytes=512)
        for ordinal, observation in enumerate(fake.observations):
            self.assertLessEqual(len(json.dumps(observation).encode("utf-8")), 512)
            history = observation["attempt_history"]
            self.assertTrue(all(set(entry) == HISTORY_KEYS for entry in history))
            self.assertEqual([entry["decision"] for entry in history],
                             list(range(ordinal - len(history) + 1, ordinal + 1)))
        self.assertGreater(len(fake.observations[-1]["attempt_history"]), 0)
        self.assertLess(len(fake.observations[-1]["attempt_history"]), 5)

    def test_oversized_invalid_candidate_keeps_bounded_diagnostic_record_and_next_decision(self):
        huge_candidate = [1] * 600
        self.assertGreater(len(json.dumps(huge_candidate).encode("utf-8")), 1024)
        summary, _, fake = self.run_case([
            response(action(huge_candidate)), response(action([1, 2, 4])),
        ])
        history = fake.observations[1]["attempt_history"]
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["candidate"])
        self.assertTrue(history[0]["candidate_omitted"])
        self.assertFalse(history[0]["valid"])
        self.assertIn("duplicate", history[0]["reason"])
        self.assertEqual(summary["decisions_attempted"], 2)
        self.assertEqual(summary["lower_bound"], 3)

    def test_invalid_math_kinds_continue_but_never_update_private_best(self):
        candidates = ([1, 1], [0, 2], [13], [1, 2, 3])
        for index, candidate in enumerate(candidates):
            with self.subTest(candidate=candidate):
                summary, _, fake = self.run_case([
                    response(action(candidate)), response(action([1, 2, 4])),
                ], name=f"invalid-{index}")
                self.assertEqual(len(fake.observations), 2)
                self.assertEqual(fake.observations[1]["private_best"], [])
                self.assertFalse(fake.observations[1]["attempt_history"][0]["valid"])
                self.assertEqual(summary["unique_valid_candidates"], 1)

    def test_malformed_protocol_actions_halt_without_candidate_verification_or_second_call(self):
        malformed = [
            [], {"candidate": [1]}, action(None), action([True]), action([1.0]),
            action(["1"]), dict(action([1]), extra="untrusted"),
            dict(action([1]), message={"recipient": "agent-0"}),
            dict(action([1]), used_event_ids=[1]),
        ]
        for index, value in enumerate(malformed):
            with self.subTest(action=value):
                summary, events, fake = self.run_case([
                    response(value), response(action([1, 2, 4])),
                ], name=f"protocol-{index}")
                self.assertEqual(len(fake.observations), 1)
                self.assertEqual(summary["stopping_reason"], "protocol_failure")
                self.assertEqual(summary["decisions_attempted"], 1)
                self.assertEqual(summary["decisions_completed"], 0)
                self.assertEqual(summary["usage"]["actual_calls"], 1)
                self.assertEqual(summary["usage"]["unknown_attempts"], 0)
                self.assertFalse(any(event["event_type"] == "verification" for event in events))
                self.assertFalse(any(event["event_type"] == "task_completed" for event in events))
                self.assertEqual(len([event for event in events if event["event_type"] == "task_failed"]), 1)
                self.assertEqual(summary["lower_bound"], 0)

    def test_legacy_explicit_stop_on_invalid_candidate_remains_unchanged(self):
        summary, _, fake = self.run_case([
            response(action([1, 2, 3])), response(action([1, 2, 4])),
        ], decision_protocol="legacy", memory_mode="private_best_only", stop_on_failure=True)
        self.assertEqual(len(fake.observations), 1)
        self.assertEqual(summary["stopping_reason"], "invalid_candidate")
        self.assertEqual(summary["lower_bound"], 0)
        self.assertTrue(all(set(observation) == BASE_OBSERVATION_KEYS for observation in fake.observations))

    def test_known_provider_failures_stop_without_retry_and_keep_actual_usage(self):
        for index, outcome in enumerate(("incomplete", "invalid_action", "refusal")):
            with self.subTest(outcome=outcome):
                summary, events, fake = self.run_case([
                    response(None, outcome=outcome), response(action([1, 2, 4])),
                ], name=f"known-{index}")
                self.assertEqual(len(fake.observations), 1)
                self.assertEqual(summary["stopping_reason"], "provider_failure")
                self.assertEqual(summary["decisions_attempted"], 1)
                self.assertEqual(summary["usage"]["actual_calls"], 1)
                self.assertEqual(summary["usage"]["unknown_attempts"], 0)
                self.assertEqual(summary["usage"]["reserved_tokens"], 0)
                self.assertEqual(summary["usage"]["total_tokens"], 120)
                self.assertFalse(any(event["event_type"] == "verification" for event in events))

    def test_budget_rejection_is_not_an_attempt_and_feedback_replay_remains_valid(self):
        # First reservation: 100 estimated input + 512 maximum output. After
        # settling 120 actual tokens, the next 612-token reservation cannot fit.
        summary, events, fake = self.run_case([
            response(action([1, 2, 4])), response(action([1, 2, 4, 5])),
        ], token_limit=700)
        self.assertEqual(len(fake.observations), 1)
        self.assertEqual(summary["stopping_reason"], "budget_exhausted")
        self.assertEqual(summary["decisions_attempted"], 1)
        self.assertEqual(summary["decisions_completed"], 1)
        self.assertEqual(summary["usage"]["actual_calls"], 1)
        self.assertEqual(summary["usage"]["reserved_tokens"], 0)
        self.assertEqual(len([event for event in events if event["event_type"] == "observation"]), 2)
        self.assertEqual(len([event for event in events if event["event_type"] == "provider_request"]), 1)
        self.assertTrue(verify_replay(self.base / "case")["verified"])

    def test_unknown_usage_halts_and_retains_spending_reservation(self):
        unknowns = (
            ProviderFailure("transport_unknown"),
            response(action([1, 2, 4]), usage=False),
            response(action([1, 2, 4]), model="different-model"),
            response(action([1, 2, 4]), service_tier="flex"),
        )
        for index, value in enumerate(unknowns):
            with self.subTest(failure=index):
                summary, _, fake = self.run_case([
                    value, response(action([1, 2, 4])),
                ], name=f"unknown-{index}")
                self.assertEqual(len(fake.observations), 1)
                self.assertEqual(summary["stopping_reason"], "unresolved_usage")
                self.assertEqual(summary["usage"]["unknown_attempts"], 1)
                self.assertGreater(summary["usage"]["reserved_tokens"], 0)
                self.assertGreater(Decimal(summary["usage"]["reserved_cost"]), 0)
                self.assertIsNone(summary["usage"]["actual_model_cost"])
                self.assertTrue(verify_replay(self.base / f"unknown-{index}")["verified"])

    def test_failure_diagnostics_and_request_identity_survive_unknown_settlement(self):
        diagnostics = {
            "schema_version": 1, "response_headers_received": True,
            "failure_category": "malformed_response_json", "parse_error": "json_decode_error",
            "parse_line": 1, "parse_column": 5, "parse_position": 4,
        }
        failure = ProviderFailure("malformed_response_unknown", request_id="fixture-request-1",
                                  diagnostics=diagnostics)
        summary, events, fake = self.run_case([failure, response(action([1, 2, 4]))])
        self.assertEqual(len(fake.observations), 1)
        request = next(event for event in events if event["event_type"] == "provider_request")
        failed = next(event for event in events if event["event_type"] == "provider_failure")
        settled = next(event for event in events if event["event_type"] == "usage")
        self.assertEqual(failed["payload"]["diagnostics"], diagnostics)
        self.assertEqual(failed["payload"]["request_id"], "fixture-request-1")
        self.assertEqual(failed["payload"]["client_request_id"], request["payload"]["client_request_id"])
        self.assertEqual(failed["payload"]["attempt_id"], request["payload"]["attempt_id"])
        self.assertEqual(failed["payload"]["attempt_id"], settled["payload"]["attempt_id"])
        self.assertLess(request["event_id"], failed["event_id"])
        self.assertLess(failed["event_id"], settled["event_id"])
        self.assertEqual(summary["stopping_reason"], "unresolved_usage")
        self.assertGreater(summary["usage"]["reserved_tokens"], 0)

    def test_request_correlation_is_persisted_before_dispatch_and_excluded_from_observation(self):
        test = self
        directory = self.base / "correlated"

        class CorrelatedProvider(FakeProvider):
            identifiers = []

            def call_with_id(self, observation, client_request_id):
                request = [event for event in read_events(directory)
                           if event["event_type"] == "provider_request"][-1]
                test.assertEqual(request["payload"]["client_request_id"], client_request_id)
                test.assertEqual(request["task_id"], observation["task_id"])
                test.assertIsInstance(client_request_id, str)
                test.assertTrue(client_request_id)
                test.assertNotIn("client_request_id", observation)
                self.identifiers.append(client_request_id)
                return super().call(observation)

        fake = CorrelatedProvider([response(action([1])), response(action([2]))])
        _, events, _ = self.run_case(fake.responses, name="correlated", provider=fake)
        self.assertEqual(len(fake.identifiers), 2)
        self.assertEqual(len(set(fake.identifiers)), 2)
        requests = [event for event in events if event["event_type"] == "provider_request"]
        usage = [event for event in events if event["event_type"] == "usage"]
        self.assertEqual([event["payload"]["attempt_id"] for event in requests],
                         [event["payload"]["attempt_id"] for event in usage])
        self.assertTrue(all(request["event_id"] < settlement["event_id"]
                            for request, settlement in zip(requests, usage)))

    def test_feedback_protocol_rejects_incompatible_configs_before_files_or_provider_construction(self):
        changes = (
            {"agents": 2, "condition": "independent"}, {"concurrency": 2},
            {"max_retries": 1}, {"decision_protocol": "unknown"},
            {"memory_mode": "unknown"}, {"history_limit": 0}, {"history_limit": 33},
            {"history_limit": True}, {"allocation": "exploratory"}, {"withhold_message": 1},
            {"decision_protocol": "legacy", "memory_mode": "history_feedback"},
        )
        for index, change in enumerate(changes):
            with self.subTest(change=change), patch("swarm_lab.runtime.OpenAIProvider") as provider:
                directory = self.base / f"config-{index}"
                with self.assertRaises(ValueError):
                    Runtime(self.config(**change), directory)
                provider.assert_not_called()
                self.assertFalse(directory.exists())

    def test_replay_rejects_fabricated_feedback_candidates_witnesses_state_and_stale_history(self):
        _, original, _ = self.run_case([
            response(action([1, 2, 3])), response(action([4, 1, 2])),
            response(action([1, 2, 4, 5])), response(action([1, 2, 4, 5])),
        ], history_limit=2)
        path = self.base / "case" / "events.jsonl"

        def observation(events, ordinal):
            return next(event["payload"] for event in events
                        if event["event_type"] == "observation" and event["payload"]["round"] == ordinal)

        def replace_candidate(events):
            observation(events, 1)["attempt_history"][0]["candidate"] = [1, 2, 4]

        def replace_witness(events):
            observation(events, 1)["attempt_history"][0]["forbidden_triple"] = [2, 3, 4]

        def inject_evaluator_state(events):
            observation(events, 1)["attempt_history"][0]["upper_bound"] = 6

        def restore_evicted_entry(events):
            observation(events, 3)["attempt_history"][0] = deepcopy(observation(events, 1)["attempt_history"][0])

        for tamper in (replace_candidate, replace_witness, inject_evaluator_state, restore_evicted_entry):
            with self.subTest(tamper=tamper.__name__):
                changed = deepcopy(original)
                tamper(changed)
                path.write_text("".join(json.dumps(event) + "\n" for event in changed))
                with self.assertRaises(ValueError):
                    verify_replay(self.base / "case")

    def test_replay_rejects_feedback_fields_in_baseline_observations(self):
        _, events, _ = self.run_case([
            response(action([1, 2, 3])), response(action([1, 2, 4])),
        ], memory_mode="private_best_only")
        observation = next(event["payload"] for event in events if event["event_type"] == "observation")
        observation["attempt_history"] = []
        path = self.base / "case" / "events.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        with self.assertRaises(ValueError):
            verify_replay(self.base / "case")

    def test_replay_rejects_fabricated_feedback_event_witness_parent_and_decision(self):
        _, original, _ = self.run_case([
            response(action([1, 2, 3])), response(action([1, 2, 4])),
        ])
        path = self.base / "case" / "events.jsonl"

        def recorded_witness(events):
            record = next(event for event in events if event["event_type"] == "feedback_recorded")
            record["payload"]["forbidden_triple"] = [2, 3, 4]

        def unrelated_read_parent(events):
            read = next(event for event in events if event["event_type"] == "feedback_read")
            run_start = next(event for event in events if event["event_type"] == "run_started")
            # Still an earlier valid event ID, so generic provenance validation
            # cannot detect that this parent is not the referenced verification.
            read["parent_event_ids"] = [run_start["event_id"]]

        def fabricated_read_decision(events):
            read = next(event for event in events if event["event_type"] == "feedback_read")
            read["payload"]["decision"] = 999

        for tamper in (recorded_witness, unrelated_read_parent, fabricated_read_decision):
            with self.subTest(tamper=tamper.__name__):
                changed = deepcopy(original)
                tamper(changed)
                path.write_text("".join(json.dumps(event) + "\n" for event in changed))
                with self.assertRaises(ValueError):
                    verify_replay(self.base / "case")

    def test_replay_recomputes_primary_metrics_even_when_summary_and_finished_event_match(self):
        summary, original, _ = self.run_case([
            response(action([1, 2, 4])), response(action([4, 2, 1])),
        ])
        directory = self.base / "case"
        metrics = ("unique_valid_candidates", "duplicate_candidates",
                   "decisions_attempted", "decisions_completed")
        for metric in metrics:
            with self.subTest(metric=metric):
                changed_summary = deepcopy(summary)
                changed_summary[metric] += 1
                changed_events = deepcopy(original)
                finished = next(event for event in changed_events if event["event_type"] == "run_finished")
                finished["payload"] = changed_summary
                (directory / "summary.json").write_text(json.dumps(changed_summary))
                (directory / "events.jsonl").write_text(
                    "".join(json.dumps(event) + "\n" for event in changed_events))
                with self.assertRaisesRegex(ValueError, "Feedback summary counts"):
                    verify_replay(directory)


if __name__ == "__main__":
    unittest.main()
