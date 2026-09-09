"""Analysis keeps failed attempts, missing observations and finite endpoints."""
from copy import deepcopy
import csv
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.report_live_comparison import analyze, export


def event(number, kind, payload=None, **kwargs):
    return dict(event_id=number, event_type=kind, payload=payload or {}, actor="agent-0",
                recipient=None, task_id="task-0", elapsed_seconds=number / 10,
                parent_event_ids=[], **kwargs)


def usage(attempts=1, input_tokens=10, output_tokens=20, cost="0.20", unknown=0):
    return dict(attempts=attempts, input_tokens=input_tokens, output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens, observed_cost=cost,
                unknown_attempts=unknown, unknown_cost_attempts=unknown, pending_attempts=0,
                cached_input_tokens=3, cache_write_tokens=4, reasoning_tokens=12,
                reserved_tokens=100 if unknown else 0, reserved_cost="1" if unknown else "0",
                groups={"agent": {"agent-0": {"attempts": attempts}}, "purpose": {}})


def recorded_events(cost="0.20", size=3):
    return [event(1, "observation", {"mailbox": []}),
            event(2, "usage", dict(attempt_id="a", input_tokens=10, output_tokens=20, cost=cost)),
            event(3, "verification", dict(valid=True, candidate=list(range(size)), lower_bound=size)),
            event(4, "task_completed")]


class LiveReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "campaign"
        self.directory.mkdir()
        self.output = Path(self.temporary.name) / "report"
        self.rows = []

    def add_run(self, condition="solo", repetition=1, status="completed", size=3,
                run_usage=None, events=None, summary_changes=None):
        row = dict(order=len(self.rows) + 1, condition=condition, repetition=repetition,
                   path=f"run-{len(self.rows)}", run_id=f"id-{len(self.rows)}", seed=repetition - 1, status=status)
        if status != "unstarted":
            row["summary"] = dict(lower_bound=size, upper_bound=3, gap=3-size,
                                  stopping_reason="step_limit", decisions_completed=1,
                                  usage=run_usage or usage(), messages=0, message_bytes=0,
                                  invalid_claims=0, duplicate_candidates=0, artifact_reuse=0,
                                  oracle={"status": "optimal", "elapsed_seconds": .001})
            row["summary"].update(summary_changes or {})
            directory = self.directory / row["path"]
            directory.mkdir()
            (directory / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in (events if events is not None else recorded_events(size=size))))
        self.rows.append(row)
        return row

    def save(self, aggregate=None):
        report = dict(schema_version=1, campaign_id="test", status="completed", runs=self.rows)
        if aggregate is not None:
            report["usage"] = aggregate
        (self.directory / "comparison.json").write_text(json.dumps(report))

    def test_failures_and_unstarted_keep_planned_denominator_and_all_costs(self):
        self.add_run()
        failed_events = [event(1, "usage", dict(attempt_id="a", input_tokens=10, output_tokens=20, cost="0.40")),
                         event(2, "attempt_failed", {"outcome": "invalid_output"})]
        self.add_run(repetition=2, status="failed", size=0,
                     run_usage=usage(cost="0.40"), events=failed_events,
                     summary_changes={"decisions_completed": 0, "stopping_reason": "provider_failure"})
        self.add_run(repetition=3, status="unstarted")
        self.add_run(repetition=4, status="budget_stopped", size=2)
        self.add_run(repetition=5, status="unstarted")
        self.save()
        analysis, curves, _ = analyze(self.directory)
        group = analysis["conditions"]["solo"]
        self.assertEqual((group["planned_runs"], group["attempted_runs"], group["solved_runs"]), (5, 3, 1))
        self.assertEqual(group["status_counts"]["failed"], 1)
        self.assertEqual(group["status_counts"]["budget_stopped"], 1)
        self.assertEqual(group["lower_bound"], {"n": 3, "min": 0, "median": 2, "max": 3})
        self.assertEqual(Decimal(group["calculated_cost_per_verified_solution_usd"]), Decimal("0.80"))
        self.assertEqual(curves[1]["points"][-1]["known_cost_usd"], "0.40")
        self.assertEqual(curves[1]["points"][-1]["lower_bound"], 0)
        self.assertEqual(curves[2]["points"], [])
        for field in ("lower_bound", "gap", "solved", "attempts", "known_tokens", "calculated_cost_usd"):
            self.assertIsNone(analysis["runs"][2][field])

    def test_unknown_failure_spend_is_incomplete_not_zero_or_omitted(self):
        self.add_run()
        self.add_run(repetition=2, status="interrupted", size=0, run_usage=usage(input_tokens=0, output_tokens=0, cost="0", unknown=1),
                     events=[event(1, "usage", dict(attempt_id="a", input_tokens=None, output_tokens=None, cost=None))],
                     summary_changes={"gap": None, "upper_bound": 24, "decisions_completed": 0})
        self.save()
        analysis, curves, _ = analyze(self.directory)
        group = analysis["conditions"]["solo"]
        self.assertEqual(group["known_calculated_cost_usd"], "0.20")
        self.assertFalse(group["cost_complete"])
        self.assertIsNone(group["calculated_cost_usd"])
        self.assertIsNone(group["calculated_cost_per_verified_solution_usd"])
        self.assertEqual(group["cost_per_solution_status"], "incomplete_unknown_cost")
        self.assertEqual(group["attempts"], 2)
        self.assertEqual(group["gap"]["n"], 1)
        self.assertFalse(curves[1]["points"][-1]["cost_complete"])
        self.assertFalse(curves[1]["points"][-1]["tokens_complete"])

    def test_no_solutions_has_undefined_cost_per_solution(self):
        self.add_run(size=2)
        self.save()
        group = analyze(self.directory)[0]["totals"]
        self.assertIsNone(group["calculated_cost_per_verified_solution_usd"])
        self.assertEqual(group["cost_per_solution_status"], "undefined_no_solutions")

    def test_curve_charges_last_failed_attempt_and_subsets_are_not_double_counted(self):
        events = recorded_events(size=2)
        events += [event(5, "usage", dict(attempt_id="b", input_tokens=7, output_tokens=9, cost="0.10")), event(6, "attempt_failed")]
        self.add_run(status="failed", size=2, run_usage=usage(attempts=2, input_tokens=17, output_tokens=29, cost="0.30"), events=events)
        self.save()
        analysis, curves, _ = analyze(self.directory)
        points = curves[0]["points"]
        self.assertEqual(points[-1]["known_tokens"], 46)
        self.assertEqual(points[-1]["known_cost_usd"], "0.30")
        self.assertEqual(points[-1]["lower_bound"], 2)
        self.assertEqual(points[-1]["status"], "failed")
        self.assertEqual(analysis["totals"]["known_tokens"], 46)
        self.assertEqual(analysis["runs"][0]["reasoning_tokens"], 12)

    def test_campaign_cost_mismatch_fails_before_output(self):
        self.add_run()
        self.save(aggregate=usage(cost="0.21"))
        with self.assertRaisesRegex(ValueError, "costs do not match"):
            export(self.directory, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_quality_remains_missing(self):
        self.add_run(status="interrupted", summary_changes={"lower_bound": None, "upper_bound": None, "gap": None})
        self.save()
        analysis, _, _ = analyze(self.directory)
        self.assertEqual(analysis["totals"]["lower_bound"]["n"], 0)
        self.assertIsNone(analysis["runs"][0]["gap"])
        self.assertEqual(analysis["totals"]["known_calculated_cost_usd"], "0.20")

    def test_trace_selects_first_adaptive_delivery_and_actual_receiver(self):
        self.add_run(condition="fixed")
        self.add_run(condition="adaptive", size=3, events=recorded_events())
        events = recorded_events()
        delivery = event(5, "message_delivered", {"content": {"candidate": [1, 2]}, "type": "inform"})
        delivery["recipient"] = "agent-1"
        observation = event(6, "observation", {"mailbox": [{"event_id": 5, "content": {"candidate": [1, 2]}}]})
        observation.update(actor="agent-1", task_id="task-1")
        reuse = event(7, "artifact_used", {"attribution": "policy-reported use; not a causal claim"})
        reuse.update(actor="agent-1", task_id="task-1", parent_event_ids=[5])
        verification = event(8, "verification", dict(valid=True, candidate=[1, 2, 4], lower_bound=3))
        verification.update(recipient="agent-1", task_id="task-1")
        events += [delivery, observation, reuse, verification]
        self.add_run(condition="adaptive", repetition=2, events=events)
        self.add_run(condition="adaptive", repetition=3, events=deepcopy(events))
        self.save()
        analysis, _, trace = analyze(self.directory)
        self.assertIn("Run: `run-2`", trace)
        self.assertIn("Event 5: message_delivered", trace)
        self.assertIn("Event 6: observation", trace)
        self.assertIn("Event 8: verification", trace)
        self.assertIn("selected candidate task: True", trace)
        self.assertIn("do not establish", trace)
        self.assertEqual(analysis["runs"][2]["artifact_used_count"], 1)

    def test_no_message_trace_explicit_and_source_immutable(self):
        self.add_run()
        self.save(aggregate=usage())
        before = {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            export(self.directory, self.output)
        self.assertIn("No adaptive run contains a delivered message", (self.output / "trace-annotations.md").read_text())
        self.assertEqual(before, {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()})
        with (self.output / "runs.csv").open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)
        self.assertTrue((self.output / "curves.json").is_file())
        with self.assertRaisesRegex(ValueError, "outside the source"):
            export(self.directory, self.directory / "report")

    def test_coordinator_usage_is_subset_and_not_added_to_total(self):
        run_usage = usage()
        run_usage["groups"]["purpose"]["coordination"] = dict(attempts=1, total_tokens=15, observed_cost="0.10")
        self.add_run(condition="fixed", run_usage=run_usage)
        self.save()
        group = analyze(self.directory)[0]["conditions"]["fixed"]
        self.assertEqual(group["known_tokens"], 30)
        self.assertEqual(group["known_calculated_cost_usd"], "0.20")
        self.assertEqual(group["coordinator_known_tokens"], 15)
        self.assertEqual(group["coordinator_known_calculated_cost_usd"], "0.10")

    def test_corrected_ledger_supersedes_usage_event_in_curve(self):
        row = self.add_run(run_usage=usage(cost="0.25"))
        ledger = {"entries": [dict(attempt_id="a", input_tokens=10, output_tokens=20, observed_cost="0.25")]}
        (self.directory / row["path"] / "usage-ledger.json").write_text(json.dumps(ledger))
        self.save()
        points = analyze(self.directory)[1][0]["points"]
        self.assertEqual(points[1]["known_cost_usd"], "0.25")
        self.assertEqual(points[-1]["known_cost_usd"], "0.25")

    def test_partial_token_failure_uses_complete_attempt_subtotal(self):
        self.add_run(status="failed", size=0,
                     run_usage=usage(input_tokens=0, output_tokens=0, cost="0", unknown=1),
                     events=[event(1, "usage", dict(attempt_id="a", input_tokens=100, output_tokens=None, cost=None))],
                     summary_changes={"decisions_completed": 0})
        self.save()
        analysis, curves, _ = analyze(self.directory)
        self.assertIsNone(analysis["runs"][0]["total_tokens"])
        self.assertEqual(analysis["runs"][0]["known_tokens"], 0)
        self.assertFalse(curves[0]["points"][-1]["tokens_complete"])
        self.assertEqual(curves[0]["points"][-1]["known_tokens"], 0)

    def test_latest_summary_exports_supersede_embedded_snapshot_after_correction(self):
        row = self.add_run()
        self.save(aggregate=usage())
        corrected_usage = usage(cost="0.25")
        ledger = {"entries": [dict(attempt_id="a", input_tokens=10, output_tokens=20, observed_cost="0.25")]}
        (self.directory / row["path"] / "usage-ledger.json").write_text(json.dumps(ledger))
        (self.directory / row["path"] / "usage-summary.json").write_text(json.dumps(corrected_usage))
        (self.directory / "campaign-summary.json").write_text(json.dumps(corrected_usage))
        analysis, curves, _ = analyze(self.directory)
        self.assertEqual(analysis["totals"]["known_calculated_cost_usd"], "0.25")
        self.assertEqual(curves[0]["points"][-1]["known_cost_usd"], "0.25")

    def test_trace_does_not_jump_from_failed_receiver_task_to_later_candidate(self):
        events = recorded_events()
        delivery = event(5, "message_delivered", {"content": "earlier message"})
        delivery["recipient"] = "agent-1"
        observation = event(6, "observation", {"mailbox": [{"event_id": 5}]})
        observation.update(actor="agent-1", task_id="task-1")
        later_candidate = event(8, "verification", dict(valid=True, candidate=[1, 2, 4]))
        later_candidate.update(recipient="agent-1", task_id="task-5")
        self.add_run(condition="adaptive", events=events + [delivery, observation, later_candidate])
        self.save()
        trace = analyze(self.directory)[2]
        self.assertIn("no valid receiver candidate is recorded in that decision task", trace)
        self.assertNotIn("Event 8: verification", trace)

    def test_billing_reconciliation_does_not_invent_missing_calculated_cost(self):
        run_usage = usage(input_tokens=0, output_tokens=0, cost="0", unknown=1)
        run_usage.update(unknown_cost_attempts=0, reconciled_cost="0.25", known_cost="0.25")
        self.add_run(status="failed", size=0, run_usage=run_usage,
                     events=[event(1, "usage", dict(attempt_id="a", input_tokens=None, output_tokens=None, cost=None))])
        self.save()
        analysis, curves, _ = analyze(self.directory)
        self.assertIsNone(analysis["runs"][0]["calculated_cost_usd"])
        self.assertEqual(analysis["runs"][0]["reconciled_cost_usd"], "0.25")
        self.assertFalse(curves[0]["points"][-1]["cost_complete"])

    def test_missing_quality_and_missing_events_do_not_plot_zero_endpoint(self):
        self.add_run(status="interrupted", events=[],
                     summary_changes={"lower_bound": None, "upper_bound": None, "gap": None})
        self.save()
        analysis, curves, _ = analyze(self.directory)
        self.assertEqual(curves[0]["points"], [])
        self.assertIsNone(analysis["runs"][0]["lower_bound"])
        self.assertEqual(analysis["runs"][0]["known_calculated_cost_usd"], "0.20")

    def test_failed_run_keeps_earlier_verified_solution_and_later_cost(self):
        events = recorded_events()
        events += [event(5, "usage", dict(attempt_id="b", input_tokens=10, output_tokens=20, cost="0.10")), event(6, "attempt_failed")]
        self.add_run(status="failed", run_usage=usage(attempts=2, input_tokens=20, output_tokens=40, cost="0.30"), events=events)
        self.save()
        analysis, curves, _ = analyze(self.directory)
        self.assertTrue(analysis["runs"][0]["solved"])
        self.assertEqual(analysis["totals"]["status_counts"]["failed"], 1)
        self.assertEqual(analysis["totals"]["calculated_cost_per_verified_solution_usd"], "0.30")
        self.assertEqual(curves[0]["points"][-1]["known_tokens"], 60)


if __name__ == "__main__":
    unittest.main()
