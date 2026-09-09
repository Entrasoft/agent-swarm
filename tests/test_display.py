"""Consequential display/replay behavior, without a graphical environment."""

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from swarm_lab.display import EventProjection, JsonlTail, graph_position, project_events


def event(event_id, event_type, *, payload=None, actor="agent-0", recipient=None, **extra):
    return {
        "run_id": "display-test", "event_id": event_id,
        "timestamp": "2026-09-09T12:00:00Z", "elapsed_seconds": event_id / 10,
        "actor": actor, "recipient": recipient, "event_type": event_type,
        "task_id": None, "artifact_id": None, "artifact_version": None,
        "parent_event_ids": [], "payload": payload or {}, "verification_status": None,
        **extra,
    }


class ProjectionTests(unittest.TestCase):
    def test_verified_bounds_not_worker_assertions_and_replay_matches(self):
        events = [
            event(1, "run_started", actor="runtime", payload={
                "config": {"mode": "algorithmic", "m": 12, "agents": 1},
                "team": [{"agent_id": "agent-0", "role": "searcher"}],
            }),
            event(2, "assignment", actor="scheduler", recipient="agent-0", task_id="search-1"),
            event(3, "candidate_submitted", payload={"candidate": [1, 2, 4], "lower_bound": 12}),
            event(4, "verification", actor="verifier", recipient="agent-0",
                  payload={"valid": True, "lower_bound": 3, "upper_bound": 12}),
            event(5, "run_finished", actor="runtime", payload={"summary": {
                "lower_bound": 3, "upper_bound": 6, "stopping_reason": "step_limit"}}),
        ]
        incremental = EventProjection()
        for item in events[:3]:
            incremental.apply(item)
        self.assertEqual(incremental.lower_bound, 0)
        self.assertEqual(incremental.agents["agent-0"].task_id, "search-1")
        for item in events[3:]:
            incremental.apply(item)
        replay = project_events(events)
        self.assertEqual(vars(incremental), vars(replay))
        self.assertEqual((replay.lower_bound, replay.upper_bound, replay.gap), (3, 6, 3))
        self.assertEqual(replay.stopping_reason, "step_limit")
        self.assertEqual(replay.agents["agent-0"].state, "stopped")
        self.assertEqual(replay.mode, "algorithmic")
        self.assertEqual([edge.category for edge in replay.edges], ["assignment", "verification"])

    def test_usage_corrections_duplicates_subsets_and_unknowns(self):
        first = event(1, "usage", payload={"attempt_id": "a", "input_tokens": 100,
            "output_tokens": 30, "cached_input_tokens": 50, "reasoning_tokens": 10,
            "cost": "0.003", "simulated": True})
        p = project_events([
            first, first,
            event(2, "usage", payload={"attempt_id": "b", "input_tokens": None,
                "output_tokens": None, "cost": None, "simulated": True}),
            event(3, "usage", payload={"attempt_id": "a", "input_tokens": 110,
                "output_tokens": 35, "cost": "0.0035", "simulated": True}),
            event(4, "usage", actor="agent-1", payload={"attempt_id": "c", "input_tokens": 7,
                "output_tokens": 2, "cost": "0.0001", "simulated": False}),
        ])
        total = p.totals()["simulated"]
        self.assertEqual(len(p.events), 4)
        self.assertEqual((total.attempts, total.input_tokens, total.output_tokens), (2, 110, 35))
        self.assertEqual((total.unknown_input, total.unknown_output, total.unknown_cost), (1, 1, 1))
        self.assertEqual(total.costs, {"USD": Decimal("0.0035")})
        self.assertEqual(p.totals()["reported"].input_tokens, 7)
        self.assertEqual(p.agent_totals()[("agent-0", "simulated")], total)
        timeline = p.usage_timeline()
        self.assertEqual(len(timeline), 3)
        simulated = [point for point in timeline if point["source"] == "simulated"][-1]
        self.assertEqual(simulated["tokens"], 145)
        self.assertEqual(simulated["costs"]["USD"], Decimal("0.0035"))
        self.assertEqual(simulated["unknown_tokens"], 2)

    def test_estimates_and_currencies_stay_separate(self):
        p = project_events([
            event(1, "usage", payload={"attempt_id": "a", "input_tokens": 10, "output_tokens": 3,
                "cost": "0.1", "currency": "EUR", "status": "estimated"}),
            event(2, "usage", payload={"attempt_id": "b", "input_tokens": 20, "output_tokens": 4,
                "cost": "0.2", "currency": "USD", "status": "estimated"}),
            event(3, "usage", payload={"attempt_id": "c", "input_tokens": 30, "output_tokens": 5,
                "cost": "0.3", "status": "reconciled"}),
        ])
        self.assertEqual(p.totals()["estimated"].costs, {"EUR": Decimal("0.1"), "USD": Decimal("0.2")})
        self.assertEqual(p.totals()["reconciled"].costs, {"USD": Decimal("0.3")})

    def test_invalid_usage_is_unknown_not_zero_and_not_inferred(self):
        p = project_events([
            event(1, "usage", payload={"attempt_id": "a", "input_tokens": True,
                "output_tokens": -5, "cost": "NaN"}),
            event(2, "usage", payload={"input_tokens": 900, "output_tokens": 900, "cost": "10"}),
        ])
        self.assertEqual(set(p.totals()), {"unknown"})
        total = p.totals()["unknown"]
        self.assertEqual((total.attempts, total.unknown_input, total.unknown_output, total.unknown_cost), (1, 1, 1, 1))
        self.assertEqual(total.costs, {})
        self.assertIsNone(p.lower_bound)
        self.assertIsNone(p.gap)

    def test_public_provenance_missing_parents_cycles_and_artifact_versions(self):
        p = project_events([
            event(1, "candidate_submitted", artifact_id="c1", artifact_version=1, parent_event_ids=[2]),
            event(2, "verification", artifact_id="c1", artifact_version=2, parent_event_ids=[1, 99]),
            event(3, "artifact_used", recipient="agent-1", artifact_id="c1", artifact_version=2, parent_event_ids=[2]),
            event(4, "message_read", recipient="agent-1", parent_event_ids=[3]),
        ])
        provenance = p.provenance(3)
        self.assertEqual([item["event_id"] for item in provenance["parent_events"]], [2, 1])
        self.assertEqual(provenance["missing_parent_event_ids"], [99])
        self.assertEqual([item["event_id"] for item in provenance["artifact_history"]], [1, 2, 3])
        self.assertEqual([edge.category for edge in p.edges], ["artifact", "message"])

    def test_graph_positions_stable_for_configured_team(self):
        positions = {f"agent-{i}": graph_position(f"agent-{i}", 10) for i in range(10)}
        self.assertEqual(len(set(positions.values())), 10)
        for identity, expected in reversed(list(positions.items())):
            self.assertEqual(graph_position(identity, 10), expected)
        self.assertEqual(graph_position("scheduler", 1), graph_position("scheduler", 10))
        self.assertEqual(graph_position("custom-worker", 4), graph_position("custom-worker", 10))

    def test_runtime_flat_start_and_artifact_delivery_provenance(self):
        p = project_events([
            event(1, "run_started", actor="runtime", payload={"mode": "algorithmic", "m": 12,
                "agents": 2, "team": [{"agent_id": "agent-0", "role": "coordinator"}]}),
            event(2, "message_delivered", actor="agent-0", recipient="agent-1",
                payload={"type": "share_artifact"}),
            event(3, "artifact_used", actor="agent-1", parent_event_ids=[2]),
            event(4, "evaluation", actor="evaluator", payload={"lower_bound": 6, "upper_bound": 6}),
        ])
        self.assertEqual(p.mode, "algorithmic")
        self.assertEqual(p.agents["agent-0"].role, "coordinator")
        self.assertEqual(p.upper_bound, 6)
        self.assertEqual((p.edges[-1].actor, p.edges[-1].recipient, p.edges[-1].category),
                         ("agent-0", "agent-1", "artifact"))


class JsonlTailTests(unittest.TestCase):
    def test_partial_utf8_record_waits_and_is_counted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            tail = JsonlTail(path)
            self.assertEqual(tail.poll().events, [])
            first = event(1, "message_sent", payload={"text": "café"})
            record = (json.dumps(first, ensure_ascii=False) + "\n").encode()
            split = record.index("é".encode()) + 1
            path.write_bytes(record[:split])
            self.assertEqual(tail.poll().events, [])
            with path.open("ab") as stream:
                stream.write(record[split:])
            self.assertEqual(tail.poll().events, [first])
            self.assertEqual(tail.poll().events, [])

    def test_corrupt_complete_line_is_visible_and_truncation_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            first = event(1, "run_started")
            path.write_text("not-json\n" + json.dumps(first) + "\n")
            tail = JsonlTail(path)
            batch = tail.poll()
            self.assertEqual(batch.events, [first])
            self.assertEqual(len(batch.warnings), 1)
            self.assertIn("Line 1", batch.warnings[0])
            path.write_text('{"event_id":2}\n')
            batch = tail.poll()
            self.assertTrue(batch.reset)
            self.assertEqual(batch.events, [{"event_id": 2}])


if __name__ == "__main__":
    unittest.main()
