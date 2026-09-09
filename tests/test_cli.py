import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from swarm_lab.cli import campaign, read_events, verify_replay
from swarm_lab.runtime import RunConfig, Runtime


class CommandSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_invalid_campaign_is_rejected_before_solver_or_output_creation(self):
        cases = [
            {'sizes':'25'}, {'sizes':'0'}, {'sizes':'-1'}, {'steps':0},
            {'steps':10001}, {'sizes':'12,12'}, {'seeds':'0,0'},
        ]
        for index, changes in enumerate(cases):
            with self.subTest(changes=changes):
                args = SimpleNamespace(sizes='12', seeds='0', steps=2,
                                       out=self.base/f'invalid-{index}')
                vars(args).update(changes)
                with patch('swarm_lab.cli.exact_optimum') as oracle:
                    with self.assertRaises(ValueError):
                        campaign(args)
                    oracle.assert_not_called()
                self.assertFalse(args.out.exists())

    def _run(self, **kwargs):
        path = self.base/'run'
        asyncio.run(Runtime(RunConfig(steps=1, agents=1, condition='solo', **kwargs),path).run())
        return path

    def _rewrite_summary(self, path, update, evaluation_update=None):
        summary = json.loads((path/'summary.json').read_text())
        summary.update(update)
        (path/'summary.json').write_text(json.dumps(summary))
        events = read_events(path)
        for event in events:
            if event['event_type'] == 'run_finished':
                event['payload'] = summary
            if event['event_type'] == 'evaluation' and evaluation_update:
                event['payload'].update(evaluation_update)
        (path/'events.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in events))

    def test_replay_rejects_gap_tamper_even_when_finished_summary_matches(self):
        path = self._run()
        self._rewrite_summary(path, {'gap':17})
        with self.assertRaisesRegex(ValueError, 'gap'):
            verify_replay(path)

    def test_replay_rejects_summary_upper_disagreeing_with_evaluation(self):
        path = self._run()
        self._rewrite_summary(path, {'upper_bound':12, 'gap':12-json.loads((path/'summary.json').read_text())['lower_bound']})
        with self.assertRaisesRegex(ValueError, 'bounds disagree'):
            verify_replay(path)

    def test_replay_rejects_false_optimality_even_when_saved_bounds_agree(self):
        path = self._run(mode='scripted')
        self._rewrite_summary(path, {'upper_bound':3,'gap':0,'stopping_reason':'solved'},
                              {'lower_bound':3,'upper_bound':3,'candidate':[1,2,4],'status':'optimal'})
        with self.assertRaisesRegex(ValueError, 'independently checked optimum'):
            verify_replay(path)

    def test_replay_rejects_solved_status_with_nonzero_gap(self):
        path = self._run(mode='scripted')
        self._rewrite_summary(path, {'stopping_reason':'solved'})
        with self.assertRaisesRegex(ValueError, 'Solved status'):
            verify_replay(path)

    def test_replay_accepts_sound_loose_timeout_upper_bound(self):
        path = self._run(oracle_timeout=0)
        result = verify_replay(path)
        self.assertTrue(result['verified'])
        self.assertEqual(result['upper_bound'],12)


if __name__ == '__main__':
    unittest.main()
