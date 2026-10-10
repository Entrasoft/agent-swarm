"""Exact code verification for coordination v0.3, checked against known codes."""

import itertools
import random
import unittest

from swarm_lab.codes import (CodeResult, Target, better, evaluate, field_add, field_mul,
                             minimum_distance, qc_generator, rank)
from swarm_lab.codes import _planes

W, W2 = 2, 3  # GF(4) elements w and w^2 = w + 1


def naive_minimum_distance(q, rows):
    """Independent check: expand every message with plain field arithmetic."""
    n, best, count = len(rows[0]), None, 0
    for message in itertools.product(range(q), repeat=len(rows)):
        if not any(message):
            continue
        word = [0] * n
        for coefficient, row in zip(message, rows):
            word = [field_add(q, a, field_mul(q, coefficient, b)) for a, b in zip(word, row)]
        weight = sum(1 for value in word if value)
        if best is None or weight < best:
            best, count = weight, 1
        elif weight == best:
            count += 1
    return best, count


def ternary_golay_rows():
    generator = [2, 0, 1, 2, 1, 1]  # 2 + x^2 + 2x^3 + x^4 + x^5 divides x^11 - 1 over GF(3)
    return [[0] * shift + generator + [0] * (5 - shift) for shift in range(6)]


class FieldTests(unittest.TestCase):
    def test_bit_sliced_gf3_addition_matches_the_field(self):
        for x, y in itertools.product(range(3), repeat=2):
            x1, x2 = _planes([x])
            y1, y2 = _planes([y])
            t = (x1 | y2) ^ (x2 | y1)
            z1, z2 = (x2 | y2) ^ t, (x1 | y1) ^ t
            self.assertFalse(z1 and z2)
            self.assertEqual(1 if z1 else 2 if z2 else 0, (x + y) % 3)

    def test_gf4_multiplication_uses_w_squared_equals_w_plus_one(self):
        self.assertEqual(field_mul(4, W, W), W2)
        self.assertEqual(field_add(4, W, 1), W2)
        self.assertEqual(field_mul(4, W, W2), 1)


class KnownCodeTests(unittest.TestCase):
    def test_ternary_golay_code(self):
        self.assertEqual(minimum_distance(3, ternary_golay_rows()), (5, 132))

    def test_extended_ternary_golay_code(self):
        rows = [row + [(-sum(row)) % 3] for row in ternary_golay_rows()]
        self.assertEqual(minimum_distance(3, rows), (6, 264))

    def test_hexacode(self):
        rows = [[1, 0, 0, 1, W, W], [0, 1, 0, W, 1, W], [0, 0, 1, W, W, 1]]
        self.assertEqual(minimum_distance(4, rows), (4, 45))

    def test_random_codes_match_brute_force(self):
        rng = random.Random(1)
        checked = 0
        while checked < 150:
            q = rng.choice((3, 4))
            k = rng.randint(1, 5)
            n = rng.randint(k, 12)
            rows = [[rng.randrange(q) for _ in range(n)] for _ in range(k)]
            if rank(q, rows) != k:
                continue
            self.assertEqual(minimum_distance(q, rows), naive_minimum_distance(q, rows))
            checked += 1

    def test_rank_deficient_matrix_is_refused(self):
        with self.assertRaises(ValueError):
            minimum_distance(3, [[1, 2, 0], [2, 1, 0]])


class QuasiCyclicTests(unittest.TestCase):
    def test_target_block_count_and_puncturing(self):
        target = Target(q=3, n=22, k=8, lower=9, upper=10)
        self.assertEqual((target.blocks, target.punctured), (3, 2))

    def test_generator_rows_are_shifted_blocks_truncated_to_length(self):
        target = Target(q=3, n=5, k=3, lower=0, upper=0)
        rows = qc_generator(target, [[1, 2, 0], [0, 0, 1]])
        self.assertEqual(rows, [[1, 2, 0, 0, 0], [0, 1, 2, 1, 0], [2, 0, 1, 0, 1]])

    def test_evaluate_matches_brute_force_on_a_small_target(self):
        target = Target(q=4, n=10, k=4, lower=0, upper=0)
        polys = [[1, W, 0, 1], [W2, 1, 1, 0], [1, 1, 0, W]]
        result = evaluate(target, polys)
        expected = naive_minimum_distance(4, qc_generator(target, polys))
        self.assertEqual((result.d, result.min_weight_count), expected)

    def test_malformed_candidates_are_rejected_without_evaluation(self):
        target = Target(q=3, n=12, k=4, lower=0, upper=0)
        self.assertFalse(evaluate(target, [[1, 0, 0, 0]] * 2).valid)
        self.assertFalse(evaluate(target, [[1, 0, 0]] * 3).valid)
        self.assertFalse(evaluate(target, [[1, 0, 0, 3]] * 3).valid)
        self.assertFalse(evaluate(target, [[True, 0, 0, 0]] * 3).valid)
        self.assertFalse(evaluate(target, 'not a list').valid)

    def test_rank_deficient_candidate_is_invalid(self):
        target = Target(q=3, n=8, k=4, lower=0, upper=0)
        result = evaluate(target, [[1, 1, 1, 1], [0, 0, 0, 0]])  # 1+x+x^2+x^3 shares factors with x^4-1
        self.assertEqual(result.reason, 'generator matrix is rank deficient')

    def test_ranking_prefers_distance_then_fewer_minimum_weight_words(self):
        self.assertTrue(better(CodeResult(True, None, 6, 10), CodeResult(True, None, 5, 1)))
        self.assertTrue(better(CodeResult(True, None, 6, 10), CodeResult(True, None, 6, 12)))
        self.assertFalse(better(CodeResult(True, None, 6, 12), CodeResult(True, None, 6, 12)))
        self.assertFalse(better(CodeResult(False, 'x'), None))


if __name__ == '__main__':
    unittest.main()
