"""Proposal preparation cannot authenticate, reserve spend or dispatch a request."""
from contextlib import redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarm_lab import feedback


class FeedbackProposalTests(unittest.TestCase):
    def test_frozen_proposal_is_complete_and_cannot_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'proposal'
            with patch('swarm_lab.providers.get_api_key', side_effect=AssertionError('No credentials')) as key, \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No network')) as network, \
                 patch('swarm_lab.ledger.Ledger', side_effect=AssertionError('No spending ledger')) as ledger:
                manifest = feedback.prepare(directory)
            key.assert_not_called()
            network.assert_not_called()
            ledger.assert_not_called()
            self.assertEqual([p.name for p in directory.iterdir()], ['proposal.json'])
            self.assertEqual(json.loads((directory/'proposal.json').read_text()), manifest)
            self.assertFalse(manifest['execution_authorized'])
            self.assertEqual(manifest['actual_model_calls'], 0)
            self.assertEqual(manifest['limits'], dict(call_limit=72, token_limit=600000, cost_limit='6.00'))
            self.assertEqual([r['arm'] for r in manifest['runs']], [
                'history_feedback', 'private_best_only', 'private_best_only',
                'history_feedback', 'history_feedback', 'private_best_only'])
            for document in manifest['documents'].values():
                self.assertEqual(hashlib.sha256(document['text'].encode()).hexdigest(), document['sha256'])
            for config in feedback.proposed_configs(manifest['configs'][0]['price']):
                self.assertFalse(config.allow_live)
                with self.assertRaisesRegex(ValueError, 'explicit --allow-live'):
                    config.validate()
            # Within each block, the intervention changes only the exposed memory.
            for index in (0, 2, 4):
                left, right = (dict(c) for c in manifest['configs'][index:index+2])
                left.pop('memory_mode')
                right.pop('memory_mode')
                self.assertEqual(left, right)
            with self.assertRaises(FileExistsError):
                feedback.prepare(directory)

    def test_no_execute_command_exists(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                feedback.main(['execute', '--allow-live'])
        self.assertEqual(failure.exception.code, 2)

    def test_reservation_bound_covers_maximum_admitted_observation(self):
        price = json.loads((feedback.ROOT/'configs'/'gpt-5.6-terra-price.json').read_text())
        config = feedback.proposed_configs(price)[0]
        from swarm_lab.providers import request_payload
        observation = {'attempt_history': ['"' * (config.context_bytes//2-100)]}
        self.assertLessEqual(len(json.dumps(observation).encode()), config.context_bytes)
        actual_estimate = len(json.dumps(request_payload(config.model, config.max_output,
                                                       config.reasoning_effort, observation)).encode())+1024
        bound = feedback.reservation_bounds(config)
        self.assertGreaterEqual(bound['input_estimate_bound'], actual_estimate)
        self.assertFalse(bound['full_output_calls_guaranteed'])
        self.assertGreater(bound['twelve_full_output_tokens'], config.token_limit)
