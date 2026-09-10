"""Read-only feedback analysis, exercised against real runtime/ledger fixtures."""
import asyncio
from copy import deepcopy
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.report_feedback_comparison import analyze, export
from swarm_lab.feedback import schedule
from swarm_lab.ledger import Ledger
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE, RunConfig, Runtime


def response(candidate, *, outcome="completed", request_id_source="response_header"):
    return ProviderResult(
        dict(candidate=candidate, message=None, used_event_ids=[]),
        dict(input_tokens=100, output_tokens=20,
             input_tokens_details=dict(cached_tokens=10, cache_write_tokens=5),
             output_tokens_details=dict(reasoning_tokens=5)),
        request_id="local-fixture-receipt", outcome=outcome,
        model="gpt-5.6-terra", service_tier="default",
        diagnostics=dict(request_id_source=request_id_source, response_status=outcome,
                         failure_category="invalid_action_json" if outcome != "completed" else None))


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)

    def estimate(self, observation):
        return 100

    def call(self, observation):
        value = next(self.responses)
        if isinstance(value, BaseException):
            raise value
        return value


class FeedbackReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.campaign = self.base / "campaign"
        self.campaign.mkdir()
        self.output = self.base / "report"
        for target in ("swarm_lab.providers.get_api_key", "swarm_lab.credentials.get_api_key", "urllib.request.urlopen"):
            guard = patch(target, side_effect=AssertionError("offline tests cannot access credentials or network"))
            guard.start()
            self.addCleanup(guard.stop)
        self.price = dict(OFFLINE_PRICE, provider="openai", model="gpt-5.6-terra", simulated=False,
                          input_per_million="2", cached_input_per_million="0.2", cache_write_per_million="2.5",
                          output_per_million="12", source_url="https://developers.openai.com/api/docs/pricing",
                          verified_on=time.strftime("%Y-%m-%d"))
        self.rows = schedule()
        for row in self.rows:
            row.update(run_id=f"run-{row['order']}", status="unstarted")
        self.manifest = dict(schedule=deepcopy(self.rows), limits=dict(call_limit=72, token_limit=600000, cost_limit="6"))
        self.ledger_path = self.campaign / "ledger.sqlite"
        self.campaign_id = "local-report-fixture"
        self.ledger = Ledger(self.ledger_path)
        self.addCleanup(self.ledger.close)
        self.ledger.create_campaign(self.campaign_id, 600000, "6", 72, self.price, simulated=False)
        for row in self.rows:
            self.ledger.create_run(row["run_id"], 100000, "1.00", self.price, simulated=False, campaign_id=self.campaign_id)

    def run_case(self, candidates, *, order=1, history_limit=8, status=None):
        row = self.rows[order-1]
        responses = [response(value) if isinstance(value, list) else value for value in candidates]
        config = RunConfig(mode="live", allow_live=True, m=12, agents=1, condition="solo", concurrency=1,
                           max_retries=0, steps=len(responses), max_output=512, model="gpt-5.6-terra",
                           reasoning_effort="medium", price=self.price, decision_protocol="feedback-v0.2",
                           memory_mode=row["arm"], history_limit=history_limit)
        summary = asyncio.run(Runtime(config, self.campaign/row["path"], FakeProvider(responses),
                                      ledger_path=self.ledger_path, campaign_id=self.campaign_id,
                                      run_id=row["run_id"]).run())
        row["summary"] = summary
        row["status"] = status or ("interrupted" if summary["stopping_reason"] == "unresolved_usage" else
                                    "failed" if summary["stopping_reason"] in {"provider_failure", "protocol_failure"} else "completed")
        return row

    def save(self, status=None):
        self.ledger.export_campaign(self.campaign_id, self.campaign)
        report = dict(campaign_id=self.campaign_id, status=status or
                      ("halted" if any(row["status"] == "interrupted" for row in self.rows) else "completed"), runs=self.rows)
        (self.campaign/"manifest.json").write_text(json.dumps(self.manifest))
        (self.campaign/"feedback-campaign.json").write_text(json.dumps(report))

    def test_duplicate_history_and_real_replay_qualify_without_initial_state_credit(self):
        row = self.run_case([[1], [1], [1, 2], [1, 2], [1, 2, 4]])
        self.run_case([[1], [1], [1]], order=2)
        self.save()
        result, curves = analyze(self.campaign)
        treatment = result["runs"][0]
        self.assertEqual((treatment["unique_valid_candidates"], treatment["valid_submissions"], treatment["duplicate_candidates"]), (3, 5, 2))
        self.assertEqual((treatment["first_valid_lower_bound"], treatment["lower_bound"], treatment["improvement_from_first_valid"]), (1, 3, 2))
        self.assertTrue(result["audit"]["verified"], result["audit"])
        self.assertEqual(result["qualification"]["status"], "qualified")
        self.assertEqual(len(result["qualification"]["qualifying_events"]), 2)
        witness = result["qualification"]["witness"]
        self.assertEqual((witness["prior_lower_bound"], witness["lower_bound"]), (1, 2))
        self.assertEqual(witness["qualifying_history"][0]["decision"], 2)
        self.assertEqual(witness["qualifying_history"][0]["kind"], "repeated")
        self.assertEqual(result["paired_blocks"][0]["treatment_minus_baseline"], 2)
        self.assertIsNone(result["paired_blocks"][1]["treatment_minus_baseline"])
        self.assertEqual(len(result["runs"]), 6)
        self.assertEqual(curves[0]["points"][-1]["calls"], 5)
        self.assertEqual(curves[-1]["points"], [])

    def test_invalid_witness_must_be_visible_before_a_strict_improvement(self):
        self.run_case([[1], [1, 2, 3], [1, 2, 4]])
        self.save()
        result, _ = analyze(self.campaign)
        witness = result["qualification"]["witness"]
        self.assertEqual(result["qualification"]["status"], "qualified")
        self.assertEqual(witness["qualifying_history"][0]["forbidden_triple"], [1, 2, 3])
        self.assertEqual(witness["qualifying_history"][0]["kind"], "invalid")
        self.assertEqual(result["runs"][0]["invalid_mathematical_candidates"], 1)

    def test_trimmed_invalid_attempt_cannot_qualify_later_improvement(self):
        self.run_case([[1, 2, 3], [1], [1, 2]], history_limit=1)
        self.save()
        result, _ = analyze(self.campaign)
        self.assertEqual(result["qualification"]["status"], "unmet")
        self.assertEqual(len(result["qualification"]["eligible_exposures"]), 1)
        self.assertEqual(result["qualification"]["qualifying_events"], [])
        self.assertEqual(result["runs"][0]["improvement_count"], 1)
        self.assertGreater(result["runs"][0]["dropped_history_entries"], 0)

    def test_duplicate_detection_spans_history_omissions(self):
        self.run_case([[1], [2], [1], [1, 2]], history_limit=1)
        self.save()
        result, _ = analyze(self.campaign)
        self.assertEqual(result["qualification"]["status"], "qualified")
        self.assertEqual(result["qualification"]["witness"]["qualifying_history"][0]["decision"], 3)
        self.assertEqual(result["runs"][0]["unique_valid_candidates"], 3)

    def test_budget_denied_observation_does_not_count_as_feedback_exposure(self):
        original = Ledger.reserve
        calls = []

        def reserve(ledger, *args, **kwargs):
            calls.append(args)
            return original(ledger, *args, **kwargs) if len(calls) <= 2 else False

        with patch.object(Ledger, "reserve", reserve):
            self.run_case([[1], [1], [1, 2]], status="budget_stopped")
        self.save()
        result, _ = analyze(self.campaign)
        self.assertEqual(result["qualification"]["status"], "unexercised")
        self.assertEqual(result["qualification"]["eligible_exposures"], [])
        row = result["runs"][0]
        self.assertEqual((row["observations"], row["observations_constructed"], row["attempts"]), (2, 3, 2))
        self.assertEqual(row["visible_history_entries"], 1)

    def test_diversity_without_quality_is_not_qualification(self):
        self.run_case([[1, 2], [1, 4], [2]])
        self.save()
        result, _ = analyze(self.campaign)
        self.assertEqual(result["qualification"]["status"], "unexercised")
        self.assertEqual(result["runs"][0]["unique_valid_candidates"], 3)
        self.assertEqual(result["runs"][0]["improvement_from_first_valid"], 0)

    def test_no_actual_valid_submission_has_zero_diversity_and_missing_quality(self):
        self.run_case([[1, 2, 3]])
        self.save()
        result, curves = analyze(self.campaign)
        self.assertEqual(result["runs"][0]["unique_valid_candidates"], 0)
        for field in ("lower_bound", "first_valid_lower_bound", "improvement_from_first_valid", "gap"):
            self.assertIsNone(result["runs"][0][field])
        self.assertIsNone(curves[0]["points"][-1]["lower_bound"])
        self.assertIsNone(result["runs"][1]["unique_valid_candidates"])
        self.assertIsNone(result["runs"][1]["attempts"])

    def test_actually_submitted_empty_set_counts_once(self):
        self.run_case([[], [], [1]])
        self.save()
        result, _ = analyze(self.campaign)
        row = result["runs"][0]
        self.assertEqual((row["unique_valid_candidates"], row["duplicate_candidates"], row["first_valid_lower_bound"]), (2, 1, 0))
        self.assertEqual(result["qualification"]["status"], "qualified")

    def test_unknown_failure_cost_and_finite_endpoint_are_preserved(self):
        self.run_case([[1], ProviderFailure("transport_unknown", diagnostics={"failure_category": "transport_timeout"})])
        self.save()
        result, curves = analyze(self.campaign)
        totals = result["totals"]
        self.assertEqual((totals["attempts"], totals["known_tokens"], totals["unknown_attempts"]), (2, 120, 1))
        self.assertFalse(totals["cost_complete"])
        self.assertIsNone(totals["calculated_cost_usd"])
        self.assertGreater(totals["reserved_tokens"], 0)
        self.assertGreater(Decimal(totals["reserved_cost"]), 0)
        self.assertTrue(result["audit"]["verified"], result["audit"])
        endpoint = curves[0]["points"][-1]
        self.assertEqual((endpoint["calls"], endpoint["known_tokens"], endpoint["lower_bound"]), (2, 120, 1))
        self.assertFalse(endpoint["tokens_complete"])
        self.assertEqual(endpoint["status"], "interrupted")
        diagnostics = result["runs"][0]["diagnostics"]
        self.assertEqual((diagnostics["persisted_client_ids"], diagnostics["returned_provider_request_ids"]), (2, 1))
        self.assertEqual(diagnostics["attempt_records"][-1]["failure_category"], "transport_timeout")

    def test_known_provider_failure_counts_resources_but_no_candidate(self):
        self.run_case([response(None, outcome="invalid_action")])
        self.save()
        result, _ = analyze(self.campaign)
        row = result["runs"][0]
        self.assertEqual((row["attempts"], row["decisions_completed"], row["unique_valid_candidates"]), (1, 0, 0))
        self.assertTrue(row["cost_complete"])
        self.assertGreater(Decimal(row["known_calculated_cost_usd"]), 0)
        self.assertIsNone(row["lower_bound"])
        self.assertEqual(row["diagnostics"]["failures_with_outcome"], 1)

    def test_response_id_fallback_is_not_counted_as_provider_header_receipt(self):
        self.run_case([response([1], request_id_source="response_id_fallback")])
        self.save()
        result, _ = analyze(self.campaign)
        counts = result["runs"][0]["diagnostics"]
        self.assertEqual(counts["persisted_client_ids"], 1)
        self.assertEqual(counts["returned_provider_request_ids"], 0)
        self.assertEqual(counts["response_id_fallbacks"], 1)

    def test_cache_and_reasoning_counters_are_subsets_not_extra_total_tokens(self):
        self.run_case([[1], [1]])
        self.save()
        result, _ = analyze(self.campaign)
        totals = result["totals"]
        self.assertEqual((totals["input_tokens"], totals["output_tokens"], totals["known_tokens"]), (200, 40, 240))
        self.assertEqual((totals["cached_input_tokens"], totals["cache_write_tokens"], totals["reasoning_tokens"]), (20, 10, 10))
        self.assertEqual(Decimal(totals["known_calculated_cost_usd"]), Decimal("0.000849"))

    def test_replay_failure_prevents_operational_qualification_even_when_event_exists(self):
        row = self.run_case([[1], [1], [1, 2]])
        self.save()
        path = self.campaign / row["path"] / "summary.json"
        summary = json.loads(path.read_text())
        summary["duplicate_candidates"] = 999
        path.write_text(json.dumps(summary))
        result, _ = analyze(self.campaign)
        self.assertEqual(result["runs"][0]["duplicate_candidates"], 1)
        self.assertFalse(result["audit"]["verified"])
        self.assertEqual(result["qualification"]["status"], "engineering_failed")
        self.assertEqual(len(result["qualification"]["qualifying_events"]), 1)

    def test_campaign_accounting_mismatch_fails_before_export(self):
        self.run_case([[1]])
        self.save()
        path = self.campaign / "campaign-summary.json"
        summary = json.loads(path.read_text())
        summary["observed_cost"] = "1"
        path.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, "observed_cost"):
            export(self.campaign, self.output)
        self.assertFalse(self.output.exists())

    def test_export_is_read_only_and_keeps_all_six_csv_rows(self):
        self.run_case([[1]])
        self.save()
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.campaign.rglob("*") if path.is_file()}
        result = export(self.campaign, self.output)
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.campaign.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        with (self.output/"runs.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1]["unique_valid_candidates"], "")
        self.assertTrue((self.output/"report.md").exists())
        with self.assertRaisesRegex(ValueError, "outside"):
            export(self.campaign, self.campaign/"report")
        self.assertEqual(len(result["runs"]), 6)


if __name__ == "__main__":
    unittest.main()
