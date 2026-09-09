import itertools
import unittest
from unittest.mock import patch

from swarm_lab.math_task import exact_optimum, forbidden_triples, validate_candidate


def exhaustive_optimum(m):
    # Independent arithmetic formulation: inspect all triples of every subset.
    largest = 0
    for mask in range(1 << m):
        candidate = [index + 1 for index in range(m) if mask & (1 << index)]
        valid = all(a + c != 2 * b for a, b, c in itertools.combinations(candidate, 3))
        if valid:
            largest = max(largest, len(candidate))
    return largest


class MathematicalTaskTests(unittest.TestCase):
    def test_arithmetic_only_not_geometric(self):
        self.assertTrue(validate_candidate(4, [1, 2, 4]).valid)
        bad = validate_candidate(4, [3, 1, 2])
        self.assertFalse(bad.valid)
        self.assertEqual(bad.forbidden_triple, (1, 2, 3))

    def test_untrusted_candidate_types_membership_and_duplicates(self):
        for candidate in ([1, 1], [0], [5], [True], [1.0], ["1"], "12", {}, None):
            with self.subTest(candidate=candidate):
                self.assertFalse(validate_candidate(4, candidate).valid)
        self.assertTrue(validate_candidate(0, []).valid)
        for m in (-1, True, 1.0):
            with self.assertRaises(ValueError):
                validate_candidate(m, [])

    def test_forbidden_triples_complete_without_duplicates(self):
        for m in range(13):
            expected = tuple(triple for triple in itertools.combinations(range(1, m + 1), 3) if triple[0] + triple[2] == 2 * triple[1])
            self.assertEqual(forbidden_triples(m), expected)

    def test_oracle_matches_independent_exhaustion(self):
        for m in range(13):
            with self.subTest(m=m):
                answer = exact_optimum(m)
                self.assertEqual(answer.status, "optimal")
                self.assertEqual(answer.lower_bound, exhaustive_optimum(m))
                self.assertEqual(answer.upper_bound, answer.lower_bound)
                self.assertEqual(len(answer.candidate), answer.lower_bound)
                self.assertTrue(validate_candidate(m, answer.candidate).valid)
                self.assertTrue(answer.solver_version)

    def test_timeout_retains_sound_frontier_bounds(self):
        # Force a deadline after several expansions independently of CPU speed.
        ticks = iter([0.0] * 15 + [2.0] * 10)
        with patch("swarm_lab.math_task.perf_counter", side_effect=lambda: next(ticks)):
            answer = exact_optimum(10, timeout_seconds=1.0)
        optimum = exhaustive_optimum(10)
        self.assertEqual(answer.status, "timed_out")
        self.assertLessEqual(answer.lower_bound, optimum)
        self.assertGreaterEqual(answer.upper_bound, optimum)
        self.assertTrue(validate_candidate(10, answer.candidate).valid)
        self.assertGreater(answer.nodes, 0)

    def test_zero_timeout_is_unknown_not_optimal_for_nonempty_universe(self):
        answer = exact_optimum(12, timeout_seconds=0)
        self.assertEqual((answer.status, answer.lower_bound, answer.upper_bound), ("timed_out", 0, 12))
        for timeout in (-1, float("inf"), float("nan"), True):
            with self.assertRaises(ValueError):
                exact_optimum(4, timeout)


if __name__ == "__main__":
    unittest.main()
