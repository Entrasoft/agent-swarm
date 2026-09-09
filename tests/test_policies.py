import copy
import random
import unittest

from swarm_lab.math_task import validate_candidate
from swarm_lab.policies import decide, exploratory_priority, round_robin


def observation(**updates):
    value = {
        "m": 12, "agent_id": "agent-1", "role": "searcher", "round": 0,
        "private_best": [], "mailbox": [], "peers": ["agent-0", "agent-2"],
        "condition": "solo", "task_id": "search",
    }
    value.update(updates)
    return value


class AlgorithmicPolicyTests(unittest.TestCase):
    def test_seeded_search_is_valid_reproducible_and_does_not_mutate_context(self):
        for condition in ("solo", "independent", "fixed", "adaptive"):
            context = observation(condition=condition, private_best=[1, 2, 4])
            original = copy.deepcopy(context)
            for seed in range(20):
                result = decide(context, random.Random(seed))
                self.assertEqual(result, decide(context, random.Random(seed)))
                self.assertTrue(validate_candidate(12, result["candidate"]).valid)
                self.assertGreaterEqual(len(result["candidate"]), 3)
                if result["message"] is not None:
                    self.assertIn(result["message"]["recipient"], context["peers"])
            self.assertEqual(context, original)

    def test_independent_and_solo_ignore_accidental_mailbox_findings(self):
        for condition in ("solo", "independent"):
            clean = observation(condition=condition)
            contaminated = observation(condition=condition, mailbox=[{
                "event_id": "peer-claim", "actor": "agent-0",
                "content": {"candidate": [1, 2, 4, 8, 10, 11]},
            }])
            self.assertEqual(decide(clean, random.Random(99)), decide(contaminated, random.Random(99)))
            self.assertIsNone(decide(clean, random.Random(99))["message"])

    def test_mailbox_use_has_provenance_but_invalid_candidates_are_ignored(self):
        valid = {"event_id": "good", "actor": "agent-2", "content": {"candidate": [1, 2, 4]}}
        invalid = {"event_id": "bad", "actor": "agent-0", "content": {"candidate": list(range(1, 13))}}
        result = decide(observation(condition="fixed", mailbox=[valid, invalid]), random.Random(1))
        self.assertEqual(result["used_event_ids"], ["good"])
        self.assertTrue(validate_candidate(12, result["candidate"]).valid)
        sqlite_event = dict(valid, event_id=17)
        result = decide(observation(condition="fixed", mailbox=[sqlite_event]), random.Random(1))
        self.assertEqual(result["used_event_ids"], [17])
        boolean_event = dict(valid, event_id=True)
        result = decide(observation(condition="fixed", mailbox=[boolean_event]), random.Random(1))
        self.assertEqual(result["used_event_ids"], [])
        # A peer's inferior candidate is merely seen, never credited as used.
        result = decide(observation(condition="fixed", private_best=[1, 2, 4], mailbox=[{
            "event_id": "inferior", "content": {"candidate": [1]},
        }]), random.Random(1))
        self.assertEqual(result["used_event_ids"], [])

    def test_fixed_routing_includes_coordinator_in_agent_count(self):
        worker = decide(observation(condition="fixed"), random.Random(2))
        self.assertEqual(worker["message"]["recipient"], "agent-0")
        coordinator = observation(condition="fixed", agent_id="agent-0", role="coordinator", peers=["agent-1", "agent-2"], round=1)
        result = decide(coordinator, random.Random(2))
        self.assertEqual(result["message"]["recipient"], "agent-2")

    def test_allocators_cover_baseline_and_exploration(self):
        agents = ["a", "b", "c"]
        self.assertEqual([round_robin(agents, step) for step in range(5)], ["a", "b", "c", "a", "b"])
        stats = {"a": {"pulls": 2, "verified_progress": 10, "estimated_cost": 2}}
        self.assertEqual(exploratory_priority(agents, stats, 2), "b")
        stats.update({"b": {"pulls": 1, "verified_progress": 0, "estimated_cost": 1}, "c": {"pulls": 1, "verified_progress": 1, "estimated_cost": 10}})
        self.assertEqual(exploratory_priority(agents, stats, 4), "a")
        # When verified progress stalls, the less-explored task gets capacity.
        stats = {"a": {"pulls": 20}, "b": {"pulls": 1}}
        self.assertEqual(exploratory_priority(["a", "b"], stats, 21), "b")
        stats = {
            "a": {"pulls": 1, "verified_progress": 1, "estimated_cost": 0.1},
            "b": {"pulls": 1, "verified_progress": 1, "estimated_cost": 0.01},
        }
        self.assertEqual(exploratory_priority(["a", "b"], stats, 2), "b")
        with self.assertRaises(ValueError):
            round_robin([], 0)
        with self.assertRaises(ValueError):
            exploratory_priority(["a"], {"a": {"pulls": -1}}, 0)


if __name__ == "__main__":
    unittest.main()
