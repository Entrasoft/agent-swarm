"""Authorized calibration boundaries, using only local fake providers."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from swarm_lab import calibration
from swarm_lab.cli import read_events, verify_replay
from swarm_lab.math_task import exact_optimum
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE


def terra_price(**changes):
    price = dict(OFFLINE_PRICE, provider="openai", model="gpt-5.6-terra", simulated=False,
                 input_per_million="2", cached_input_per_million="0.2",
                 cache_write_per_million="2.5", output_per_million="12",
                 source_url="https://developers.openai.com/api/docs/pricing",
                 verified_on=time.strftime("%Y-%m-%d"))
    price.update(changes)
    return price


class FakeProvider:
    def __init__(self, config, calls, *, candidate=None, output_tokens=None,
                 fail_at=None, malformed_usage_at=None, reported_model="gpt-5.6-terra",
                 reported_service_tier="default"):
        self.config = config
        self.calls = calls
        self.candidate = candidate or (lambda observation: [1, 2, 4])
        self.output_tokens = output_tokens or (lambda observation: 20)
        self.fail_at = fail_at
        self.malformed_usage_at = malformed_usage_at
        self.reported_model = reported_model
        self.reported_service_tier = reported_service_tier

    def estimate(self, observation):
        return 100

    def call(self, observation):
        self.calls.append(deepcopy(observation))
        ordinal = len(self.calls)
        if ordinal == self.fail_at:
            raise ProviderFailure("transport_unknown", "fake-unknown")
        usage = {"input_tokens": 100, "output_tokens": self.output_tokens(observation),
                 "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                 "output_tokens_details": {"reasoning_tokens": 0}}
        if ordinal == self.malformed_usage_at:
            usage["input_tokens"] = -1
        return ProviderResult(
            {"candidate": self.candidate(observation), "message": None, "used_event_ids": []},
            usage, request_id=f"fake-{ordinal}", model=self.reported_model,
            service_tier=self.reported_service_tier)


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "campaign"
        self.calls = []
        # Tests must neither consume nor rely on the real authorization claim.
        authorization_dir = patch.object(calibration, "AUTHORIZATION_DIR", Path(self.temp.name) / "authorizations")
        authorization_dir.start()
        self.addCleanup(authorization_dir.stop)

    def prepare(self, **price_changes):
        return calibration.prepare(self.directory, terra_price(**price_changes))

    def execute(self, **provider_options):
        def factory(config):
            return FakeProvider(config, self.calls, **provider_options)
        return calibration.execute(self.directory, allow_live=True, provider_factory=factory)

    def run_path(self, row):
        path = Path(row["path"])
        return path if path.is_absolute() else self.directory / path

    def test_preparation_freezes_scope_without_credentials_or_network(self):
        with patch("swarm_lab.providers.get_api_key", side_effect=AssertionError("credentials accessed")), \
             patch("swarm_lab.credentials.get_api_key", side_effect=AssertionError("credentials accessed")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network accessed")):
            manifest = self.prepare()
        self.assertTrue(self.directory.is_dir())
        serialized = json.dumps(manifest)
        self.assertIn("gpt-5.6-terra", serialized)
        self.assertIn("medium", serialized)
        self.assertIn("25000", serialized)
        self.assertIn("100000", serialized)
        self.assertIn("source_sha256", serialized)
        self.assertNotIn("OPENAI_API_KEY", serialized)
        self.assertEqual(self.calls, [])

    def test_live_opt_in_required_before_provider_factory(self):
        self.prepare()
        with patch("swarm_lab.runtime.OpenAIProvider") as provider:
            with self.assertRaises(ValueError):
                calibration.execute(self.directory)
        provider.assert_not_called()

    def test_prepared_scope_and_source_tampering_fail_before_dispatch(self):
        manifest = self.prepare()
        manifest_path = self.directory / "manifest.json"
        mutations = (
            lambda value: value["limits"].update(call_limit=7),
            lambda value: value["configs"][0].update(steps=4),
            lambda value: value["configs"][1].update(max_retries=1),
            lambda value: value["configs"][1].update(model="another-model"),
            lambda value: value["source_sha256"].update({"runtime.py": "changed"}),
            lambda value: value.update(protocol=value["protocol"] + "\nChanged after preparation."),
        )
        for mutate in mutations:
            changed = deepcopy(manifest)
            mutate(changed)
            manifest_path.write_text(json.dumps(changed))
            with self.subTest(manifest=changed["limits"]):
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse((self.directory / "execution-started.json").exists())

    def test_preparation_cannot_overwrite_existing_campaign(self):
        original = self.prepare()
        with self.assertRaises((ValueError, FileExistsError)):
            self.prepare()
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), original)

    def test_preparation_rejects_stale_price_before_creating_campaign(self):
        with self.assertRaises(ValueError):
            self.prepare(verified_on="2000-01-01")
        self.assertFalse(self.directory.exists())

    def test_six_calls_use_one_campaign_and_unique_attempts(self):
        self.prepare()
        report = self.execute()
        self.assertEqual([row["m"] for row in report["runs"]], [18, 24])
        self.assertEqual([call["m"] for call in self.calls], [18] * 3 + [24] * 3)
        self.assertEqual(report["usage"]["actual_calls"], 6)
        self.assertEqual(report["usage"]["total_tokens"], 720)
        self.assertEqual(report["usage"]["remaining_calls"], 0)
        self.assertEqual(report["usage"]["retry_attempts"], 0)
        self.assertEqual(report["usage"]["reserved_tokens"], 0)
        self.assertEqual(report["usage"]["token_overshoot"], 0)
        self.assertEqual(Decimal(report["usage"]["cost_overshoot"]), 0)
        entries = json.loads((self.directory / "campaign-ledger.json").read_text())["entries"]
        self.assertEqual(len(entries), 6)
        self.assertEqual(len({entry["attempt_id"] for entry in entries}), 6)
        self.assertEqual(len({entry["run_id"] for entry in entries}), 2)
        self.assertEqual({entry["attempt"] for entry in entries}, {0})
        self.assertEqual(sum(entry["total_tokens"] for entry in entries), report["usage"]["total_tokens"])
        for row in report["runs"]:
            self.assertTrue(verify_replay(self.run_path(row))["verified"])
        self.assertEqual(self.calls[0]["private_best"], [])
        self.assertEqual(self.calls[3]["private_best"], [])
        self.assertTrue(all(not call["mailbox"] and not call["peers"] for call in self.calls))

    def test_same_campaign_cannot_generate_twice(self):
        self.prepare()
        self.execute()
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(len(self.calls), 6)

    def test_new_output_directory_cannot_reuse_the_same_authorization(self):
        self.prepare()
        other_directory = Path(self.temp.name) / "another-campaign"
        calibration.prepare(other_directory, terra_price())
        self.execute()
        def factory(config):
            return FakeProvider(config, self.calls)
        with self.assertRaises((ValueError, FileExistsError)):
            calibration.execute(other_directory, allow_live=True, provider_factory=factory)
        self.assertEqual(len(self.calls), 6)
        self.assertFalse((other_directory / "m18-solo").exists())

    def test_concurrent_output_directories_share_one_authorization_claim(self):
        self.prepare()
        other_directory = Path(self.temp.name) / "another-campaign"
        calibration.prepare(other_directory, terra_price())
        both_ready = threading.Barrier(2)
        def execute_once(directory):
            both_ready.wait(timeout=5)
            try:
                return calibration.execute(directory, allow_live=True,
                    provider_factory=lambda config: FakeProvider(config, self.calls))
            except (ValueError, FileExistsError):
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(execute_once, [self.directory, other_directory]))
        self.assertEqual(results.count("blocked"), 1)
        completed = [result for result in results if isinstance(result, dict)]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["usage"]["actual_calls"], 6)
        self.assertEqual(len(self.calls), 6)

    def test_combined_token_ceiling_stops_second_size(self):
        self.prepare()
        report = self.execute(output_tokens=lambda observation: 22_000)
        self.assertEqual([call["m"] for call in self.calls], [18, 18, 18, 24])
        self.assertEqual(report["usage"]["actual_calls"], 4)
        self.assertEqual(report["usage"]["total_tokens"], 88_400)
        self.assertEqual(report["usage"]["reserved_tokens"], 0)
        self.assertEqual(report["usage"]["token_overshoot"], 0)
        self.assertEqual(report["selection"]["status"], "inconclusive")

    def test_combined_currency_ceiling_stops_with_tokens_remaining(self):
        # A synthetic tariff isolates currency admission from the token limit.
        self.prepare(output_per_million="30")
        report = self.execute(output_tokens=lambda observation: 5_000 if observation["m"] == 18 else 25_000)
        self.assertEqual([call["m"] for call in self.calls], [18, 18, 18, 24, 24])
        usage = report["usage"]
        self.assertEqual(usage["total_tokens"], 65_500)
        self.assertEqual(Decimal(usage["calculated_model_cost"]), Decimal("1.951"))
        self.assertEqual(Decimal(usage["cost_overshoot"]), 0)
        self.assertGreater(usage["remaining_tokens"], 25_100)
        self.assertEqual(report["selection"]["status"], "inconclusive")

    def test_unknown_request_stops_without_retry_and_retains_reservation(self):
        self.prepare()
        report = self.execute(fail_at=2)
        self.assertEqual([call["m"] for call in self.calls], [18, 18])
        usage = report["usage"]
        self.assertEqual(usage["actual_calls"], 2)
        self.assertEqual(usage["unknown_attempts"], 1)
        self.assertEqual(usage["reserved_tokens"], 25_100)
        self.assertIsNone(usage["calculated_model_cost"])
        self.assertEqual(usage["retry_attempts"], 0)
        self.assertEqual(report["selection"]["status"], "inconclusive")
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(len(self.calls), 2)

    def test_malformed_usage_preserves_started_attempt_and_prevents_next_size(self):
        self.prepare()
        report = self.execute(malformed_usage_at=2)
        self.assertEqual([call["m"] for call in self.calls], [18, 18])
        self.assertEqual(report["usage"]["unknown_attempts"], 1)
        self.assertEqual(report["usage"]["reserved_tokens"], 25_100)
        self.assertEqual(report["selection"]["status"], "inconclusive")
        self.assertEqual(report["runs"][1]["failure"], "not_started_after_failure")
        self.assertTrue((self.directory / "campaign-ledger.json").exists())
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(len(self.calls), 2)

    def test_crash_marker_blocks_generation_even_without_recorded_attempts(self):
        self.prepare()
        (self.directory / "execution-started.json").write_text("{}")
        with self.assertRaises((ValueError, FileExistsError)):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_invalid_candidate_stops_without_replacement_call(self):
        self.prepare()
        report = self.execute(candidate=lambda observation: [1, 2, 3])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report["usage"]["actual_calls"], 1)
        self.assertEqual(report["usage"]["unknown_attempts"], 0)
        self.assertEqual(report["selection"]["status"], "inconclusive")

    def test_unexpected_or_missing_provider_identifiers_preserve_raw_usage_and_stop(self):
        cases = (
            ("other-model", "default", "unexpected_model"),
            (None, "default", "unexpected_model"),
            ("gpt-5.6-terra", "priority", "unexpected_service_tier"),
            ("gpt-5.6-terra", None, "unexpected_service_tier"),
        )
        for index, (model, tier, outcome) in enumerate(cases):
            with self.subTest(model=model, tier=tier):
                self.directory = Path(self.temp.name) / f"identifier-case-{index}"
                self.calls = []
                with patch.object(calibration, "AUTHORIZATION_DIR", Path(self.temp.name) / f"claims-{index}"):
                    self.prepare()
                    report = self.execute(reported_model=model, reported_service_tier=tier)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(report["usage"]["actual_calls"], 1)
                self.assertEqual(report["usage"]["unknown_attempts"], 1)
                self.assertEqual(report["usage"]["reserved_tokens"], 25_100)
                self.assertIsNone(report["usage"]["calculated_model_cost"])
                self.assertEqual(report["selection"]["status"], "inconclusive")
                self.assertIsNone(report["selection"]["selected_m"])
                self.assertEqual(report["runs"][1]["failure"], "not_started_after_failure")
                events = read_events(self.run_path(report["runs"][0]))
                results = [event["payload"] for event in events if event["event_type"] == "provider_result"]
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["model"], model)
                self.assertEqual(results[0]["service_tier"], tier)
                self.assertEqual(results[0]["outcome"], outcome)
                self.assertEqual(results[0]["usage"], {
                    "input_tokens": 100, "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0}})
                self.assertFalse(any(event["event_type"] == "candidate_submitted" for event in events))

    def test_optimal_candidate_does_not_hide_a_subsequent_provider_failure(self):
        optimum = list(exact_optimum(18).candidate)
        self.prepare()
        report = self.execute(candidate=lambda observation: optimum, fail_at=2)
        summary = report["runs"][0]["summary"]
        self.assertEqual(summary["gap"], 0)
        self.assertIn(summary["stopping_reason"], {"provider_failure", "unresolved_usage"})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(report["selection"]["status"], "inconclusive")
        self.assertEqual(report["runs"][1]["failure"], "not_started_after_failure")

    def test_selection_prefers_m24_when_both_have_first_call_headroom(self):
        self.prepare()
        report = self.execute()
        self.assertEqual(report["selection"]["status"], "eligible")
        self.assertEqual(report["selection"]["selected_m"], 24)

    def test_selection_falls_back_to_m18_if_m24_first_call_is_optimal(self):
        optima = {m: list(exact_optimum(m).candidate) for m in (18, 24)}
        self.prepare()
        report = self.execute(candidate=lambda observation: optima[24] if observation["m"] == 24 else [1, 2, 4])
        self.assertEqual(report["selection"]["status"], "eligible")
        self.assertEqual(report["selection"]["selected_m"], 18)

    def test_selection_declares_saturation_without_extending_task(self):
        optima = {m: list(exact_optimum(m).candidate) for m in (18, 24)}
        self.prepare()
        report = self.execute(candidate=lambda observation: optima[observation["m"]])
        self.assertEqual(report["selection"]["status"], "saturated")
        self.assertIsNone(report["selection"]["selected_m"])
        self.assertEqual(len(self.calls), 6)

    def test_final_optimum_does_not_erase_first_call_headroom(self):
        optima = {m: list(exact_optimum(m).candidate) for m in (18, 24)}
        self.prepare()
        report = self.execute(candidate=lambda observation: [1, 2, 4] if observation["round"] == 0 else optima[observation["m"]])
        self.assertEqual(report["selection"]["status"], "eligible")
        self.assertEqual(report["selection"]["selected_m"], 24)
        self.assertTrue(all(row["summary"]["gap"] == 0 for row in report["runs"]))

    def test_inexact_or_missing_evaluation_cannot_select_difficulty(self):
        self.prepare()
        report = self.execute()
        for status in ("timeout", None):
            rows = deepcopy(report["runs"])
            rows[0]["summary"]["oracle"]["status"] = status
            result = calibration.select_difficulty(rows)
            self.assertEqual(result["status"], "inconclusive")
            self.assertIsNone(result["selected_m"])
        result = calibration.select_difficulty(report["runs"][:1])
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["selected_m"])


if __name__ == "__main__":
    unittest.main()
