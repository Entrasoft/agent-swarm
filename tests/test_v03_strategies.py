"""Stage 2 search strategies and strategy arms for coordination v0.3."""

from pathlib import Path
import random
import tempfile
import unittest

from swarm_lab.archive_runtime import (ArchiveConfig, ArchiveRuntime, check_action, read_events,
                                       strategy_of, verify_replay)
from swarm_lab.codes import Target, evaluate, field_add, field_mul, minimum_word, qc_generator
from swarm_lab.v03_strategies import STRATEGIES, STRATEGY_FUNCTIONS
from tests.test_codes import naive_minimum_distance

SMALL = dict(q=3, n=12, k=4, lower=6, upper=6)


def word_weight(q, rows, message):
    word = [0] * len(rows[0])
    for coefficient, row in zip(message, rows):
        word = [field_add(q, a, field_mul(q, coefficient, b)) for a, b in zip(word, row)]
    return sum(1 for value in word if value)


def observation(target, archive, strategy):
    return dict(target=dict(q=target.q, n=target.n, k=target.k, blocks=target.blocks,
                            punctured=target.punctured),
                agent_id='agent-0', round=1, slot=None, strategy=strategy, archive=archive)


class MinimumWordTests(unittest.TestCase):
    def test_returned_word_has_minimum_weight(self):
        rng = random.Random(3)
        for _ in range(40):
            q = rng.choice((3, 4))
            target = Target(q=q, n=rng.randint(9, 15), k=4, lower=0, upper=0)
            polys = [[rng.randrange(q) for _ in range(4)] for _ in range(target.blocks)]
            result = evaluate(target, polys)
            if not result.valid:
                continue
            rows = qc_generator(target, polys)
            self.assertEqual(word_weight(q, rows, minimum_word(q, rows)), naive_minimum_distance(q, rows)[0])


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.target = Target(q=4, n=14, k=5, lower=0, upper=0)
        rng = random.Random(5)
        self.archive = []
        while len(self.archive) < 3:
            polys = [[rng.randrange(4) for _ in range(5)] for _ in range(3)]
            result = evaluate(self.target, polys)
            if result.valid:
                self.archive.append(dict(event_id=10 + len(self.archive), agent=f'agent-{len(self.archive)}',
                                         polynomials=polys, d=result.d, min_weight_count=result.min_weight_count))

    def test_every_strategy_returns_a_well_formed_action_on_a_visible_base(self):
        for name in STRATEGIES:
            for seed in range(5):
                obs = observation(self.target, self.archive, name)
                action = STRATEGY_FUNCTIONS[name](obs, random.Random(seed))
                self.assertIsNone(check_action(action, obs, self.target)[0], name)
                self.assertNotEqual(action['polynomials'],
                                    next(e['polynomials'] for e in self.archive if e['event_id'] == action['base']))

    def test_every_strategy_starts_from_scratch_on_an_empty_archive(self):
        for name in STRATEGIES:
            action = STRATEGY_FUNCTIONS[name](observation(self.target, [], name), random.Random(0))
            self.assertIsNone(action['base'])
            self.assertEqual(len(action['polynomials']), self.target.blocks)

    def test_recombination_names_both_parents(self):
        action = STRATEGY_FUNCTIONS['recombine'](observation(self.target, self.archive, 'recombine'),
                                                 random.Random(1))
        self.assertEqual(len(action['used_event_ids']), 2)

    def test_repair_raises_the_weight_of_the_targeted_word(self):
        base = self.archive[0]
        rows = qc_generator(self.target, base['polynomials'])
        message = minimum_word(4, rows)
        before = word_weight(4, rows, message)
        action = STRATEGY_FUNCTIONS['repair'](observation(self.target, [base], 'repair'), random.Random(2))
        after = word_weight(4, qc_generator(self.target, action['polynomials']), message)
        self.assertGreaterEqual(after, before)


class StrategyArmTests(unittest.TestCase):
    def test_assignment(self):
        self.assertEqual([strategy_of('diverse', i, 7) for i in range(4)], list(STRATEGIES))
        self.assertEqual({strategy_of('homogeneous', i, 6) for i in range(4)}, {STRATEGIES[2]})
        self.assertIsNone(strategy_of('slots', 0, 0))

    def test_policy_and_arm_must_agree(self):
        with self.assertRaises(ValueError):
            ArchiveConfig(target=dict(SMALL), arm='S-D').validate()  # default policy is positive control
        with self.assertRaises(ValueError):
            ArchiveConfig(target=dict(SMALL), arm='solo', policy='strategies').validate()  # solo needs one agent

    def test_all_strategy_arms_run_and_replay(self):
        for arm, agents in (('I-H', 4), ('I-D', 4), ('S-H', 4), ('S-D', 4), ('solo', 1)):
            with tempfile.TemporaryDirectory() as directory:
                config = ArchiveConfig(target=dict(SMALL), arm=arm, policy='strategies', agents=agents,
                                       seed=3, token_limit=8_000)
                summary = ArchiveRuntime(config, Path(directory)).run()
                self.assertIsNotNone(summary['best'], arm)
                self.assertTrue(verify_replay(Path(directory))['verified'], arm)
                if arm.startswith('I') or arm == 'solo':
                    for event in read_events(Path(directory)):
                        if event['event_type'] == 'observation':
                            self.assertTrue(all(e['agent'] == event['actor'] for e in event['payload']['archive']))


if __name__ == '__main__':
    unittest.main()
