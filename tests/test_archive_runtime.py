"""Archive runtime for coordination v0.3: isolation, round snapshots and replay."""

import json
from pathlib import Path
import tempfile
import unittest

from swarm_lab.archive_runtime import (Archive, ArchiveConfig, ArchiveRuntime, check_action,
                                       read_events, verify_replay)
from swarm_lab.codes import Target

SMALL = dict(q=3, n=12, k=4, lower=6, upper=6)


def run(directory, arm, **changes):
    config = ArchiveConfig(target=dict(SMALL), arm=arm, token_limit=8_000, **changes)
    return ArchiveRuntime(config, Path(directory)).run()


class ArchiveTests(unittest.TestCase):
    def test_archive_is_bounded_ranked_and_distinct(self):
        archive = Archive(2)
        archive.add(dict(event_id=1, agent='a', polynomials=[[1]], d=3, min_weight_count=5))
        archive.add(dict(event_id=2, agent='b', polynomials=[[2]], d=4, min_weight_count=9))
        archive.add(dict(event_id=3, agent='c', polynomials=[[1]], d=9, min_weight_count=1))  # duplicate code
        archive.add(dict(event_id=4, agent='d', polynomials=[[0, 1]], d=4, min_weight_count=2))
        self.assertEqual([e['event_id'] for e in archive.entries], [4, 2])


class ActionCheckTests(unittest.TestCase):
    def setUp(self):
        self.target = Target(**SMALL)
        self.entry = dict(event_id=7, agent='agent-1', polynomials=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
                          d=3, min_weight_count=4)
        self.observation = dict(archive=[self.entry], slot=None)

    def test_base_must_be_visible(self):
        action = dict(base=99, polynomials=self.entry['polynomials'], used_event_ids=[])
        self.assertIn('not an entry', check_action(action, self.observation, self.target)[0])

    def test_used_ids_must_be_visible(self):
        action = dict(base=None, polynomials=self.entry['polynomials'], used_event_ids=[99])
        self.assertIn('used_event_ids', check_action(action, self.observation, self.target)[0])

    def test_extra_fields_are_rejected(self):
        action = dict(base=None, polynomials=[], used_event_ids=[], note='hi')
        self.assertIn('exactly', check_action(action, self.observation, self.target)[0])

    def test_positive_control_may_change_only_its_slot(self):
        observation = dict(archive=[self.entry], slot=1)
        allowed = [list(p) for p in self.entry['polynomials']]
        allowed[1] = [2, 2, 1, 0]
        self.assertIsNone(check_action(dict(base=7, polynomials=allowed, used_event_ids=[7]),
                                       observation, self.target)[0])
        forbidden = [list(p) for p in allowed]
        forbidden[0] = [0, 0, 0, 1]
        self.assertIn('only its assigned slot', check_action(
            dict(base=7, polynomials=forbidden, used_event_ids=[7]), observation, self.target)[0])


class RuntimeTests(unittest.TestCase):
    def test_independent_agents_never_observe_peer_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            run(directory, 'pc-independent')
            for event in read_events(Path(directory)):
                if event['event_type'] == 'observation':
                    self.assertTrue(all(e['agent'] == event['actor'] for e in event['payload']['archive']))

    def test_shared_agents_observe_peer_codes_after_the_first_round(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = run(directory, 'pc-shared')
            observed = [e for e in read_events(Path(directory)) if e['event_type'] == 'observation']
            self.assertTrue(any(entry['agent'] != e['actor'] for e in observed for entry in e['payload']['archive']))
            self.assertGreater(summary['cross_agent_extensions'], 0)

    def test_round_zero_sees_an_empty_archive_for_everyone(self):
        with tempfile.TemporaryDirectory() as directory:
            run(directory, 'pc-shared')
            first = [e for e in read_events(Path(directory))
                     if e['event_type'] == 'observation' and e['payload']['round'] == 0]
            self.assertEqual(len(first), 4)
            self.assertTrue(all(e['payload']['archive'] == [] for e in first))

    def test_budget_ends_runs_on_whole_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = run(directory, 'pc-shared')
            self.assertEqual(summary['stopping_reason'], 'budget_exhausted')
            self.assertEqual(len(set(summary['decisions'].values())), 1)
            self.assertEqual(summary['actual_model_calls'], 0)

    def test_output_directory_must_be_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'existing').write_text('x')
            with self.assertRaises(ValueError):
                run(directory, 'pc-shared')

    def test_unknown_arm_is_refused(self):
        with self.assertRaises(ValueError):
            ArchiveConfig(target=dict(SMALL), arm='S-D').validate()


class ReplayTests(unittest.TestCase):
    def tamper(self, directory, predicate, change):
        path = Path(directory, 'events.jsonl')
        events = read_events(Path(directory))
        for event in events:
            if predicate(event):
                change(event)
                break
        path.write_text(''.join(json.dumps(e) + '\n' for e in events))

    def test_clean_runs_replay(self):
        for arm in ('pc-independent', 'pc-shared'):
            with tempfile.TemporaryDirectory() as directory:
                run(directory, arm)
                self.assertTrue(verify_replay(Path(directory))['verified'])

    def test_replay_detects_a_falsified_distance(self):
        with tempfile.TemporaryDirectory() as directory:
            run(directory, 'pc-shared')
            self.tamper(directory, lambda e: e['event_type'] == 'verification' and e['payload']['valid'],
                        lambda e: e['payload'].update(d=e['payload']['d'] + 1))
            with self.assertRaisesRegex(ValueError, 'disagrees with recomputation'):
                verify_replay(Path(directory))

    def test_replay_detects_a_leaked_peer_code(self):
        with tempfile.TemporaryDirectory() as directory:
            run(directory, 'pc-independent')
            leak = dict(event_id=1, agent='agent-9', polynomials=[], d=99, min_weight_count=1)
            self.tamper(directory, lambda e: e['event_type'] == 'observation' and e['payload']['round'] == 2,
                        lambda e: e['payload']['archive'].insert(0, leak))
            with self.assertRaisesRegex(ValueError, 'does not match the recomputed archive'):
                verify_replay(Path(directory))


if __name__ == '__main__':
    unittest.main()
