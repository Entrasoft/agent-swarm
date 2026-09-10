"""Independent audit catches false primary metrics, altered costs and lost holds."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.audit_feedback_comparison import audit
from swarm_lab import feedback_campaign
from swarm_lab.providers import ProviderFailure
from tests.test_feedback_campaign import FakeProvider, result, terra_price


class FeedbackAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'campaign'
        for guard in (patch.object(feedback_campaign, 'AUTHORIZATION_DIR', Path(self.temp.name)/'claims'),
                      patch.object(feedback_campaign, '_git_state', return_value=('a'*40, False)),
                      patch('swarm_lab.feedback_campaign.print', create=True),
                      patch('swarm_lab.providers.get_api_key', side_effect=AssertionError('No credentials')),
                      patch('urllib.request.urlopen', side_effect=AssertionError('No network'))):
            guard.start()
            self.addCleanup(guard.stop)

    def run_fixture(self, respond):
        feedback_campaign.prepare(self.directory, terra_price())
        # Runtime records git metadata separately; keep these local fixture
        # identities consistent with the prepared fake revision.
        import subprocess
        original = subprocess.check_output
        def git_output(command, **kwargs):
            if command[:3] == ['git','rev-parse','HEAD']:
                return 'a'*40+'\n'
            if command[:3] == ['git','status','--porcelain']:
                return ''
            return original(command, **kwargs)
        with patch('swarm_lab.runtime.subprocess.check_output', side_effect=git_output):
            return feedback_campaign.execute(self.directory, allow_live=True,
                provider_factory=lambda cfg: FakeProvider(cfg, [], respond))

    def test_independent_math_and_costs_pass_then_primary_forgery_fails(self):
        report = self.run_fixture(lambda obs, n: result(obs, candidate=[1,2,3] if n == 1 else [1,2,4]))
        checked = audit(self.directory)
        self.assertTrue(checked['audit_passed'], checked['failures'])
        self.assertEqual(checked['attempts'], 72)
        self.assertTrue(all(row['unique_valid_candidates'] == 1 for row in checked['runs']))
        report_path = self.directory/'feedback-campaign.json'
        forged = deepcopy(report)
        forged['runs'][0]['unique_valid_candidates'] = 999
        forged['runs'][0]['summary']['unique_valid_candidates'] = 999
        report_path.write_text(json.dumps(forged))
        self.assertFalse(audit(self.directory)['audit_passed'])
        report_path.write_text(json.dumps(report))
        path = self.directory/report['runs'][0]['path']/'summary.json'
        summary = json.loads(path.read_text())
        summary['unique_valid_candidates'] = 9
        path.write_text(json.dumps(summary))
        checked = audit(self.directory)
        self.assertFalse(checked['audit_passed'])
        self.assertTrue(any('primary diversity' in item for item in checked['failures']))

    def test_usage_price_tamper_is_independently_detected(self):
        self.run_fixture(lambda obs, n: result(obs, outcome='invalid_action'))
        self.assertTrue(audit(self.directory)['audit_passed'])
        path = self.directory/'campaign-ledger.json'
        ledger = json.loads(path.read_text())
        ledger['entries'][0]['observed_cost'] = '0.99999'
        path.write_text(json.dumps(ledger))
        checked = audit(self.directory)
        self.assertFalse(checked['audit_passed'])
        self.assertTrue(any('independently calculated cost' in item for item in checked['failures']))

    def test_unknown_charge_and_unstarted_rows_are_preserved_and_lost_hold_fails(self):
        def fail(obs, n):
            raise ProviderFailure('transport_unknown', diagnostics={'failure_category':'transport_timeout'})
        self.run_fixture(fail)
        checked = audit(self.directory)
        self.assertTrue(checked['audit_passed'], checked['failures'])
        self.assertEqual((checked['attempts'], checked['unknown_cost_attempts']), (1,1))
        self.assertEqual([row['unique_valid_candidates'] for row in checked['runs']], [0,None,None,None,None,None])
        summary_path, report_path = self.directory/'campaign-summary.json', self.directory/'feedback-campaign.json'
        summary, report = json.loads(summary_path.read_text()), json.loads(report_path.read_text())
        forged = deepcopy(summary)
        forged.update(calculated_model_cost='0', actual_model_cost='0', billing_status='reconciled')
        summary_path.write_text(json.dumps(forged))
        forged_report = deepcopy(report)
        forged_report['usage'] = forged
        report_path.write_text(json.dumps(forged_report))
        checked = audit(self.directory)
        self.assertFalse(checked['audit_passed'])
        self.assertTrue(any('completeness' in item or 'billing uncertainty' in item for item in checked['failures']))
        summary_path.write_text(json.dumps(summary))
        report_path.write_text(json.dumps(report))
        path = self.directory/'campaign-ledger.json'
        ledger = json.loads(path.read_text())
        ledger['entries'][0]['reserved_cost'] = '0.00001'
        path.write_text(json.dumps(ledger))
        checked = audit(self.directory)
        self.assertFalse(checked['audit_passed'])
        self.assertTrue(any('unknown cost retains hold' in item for item in checked['failures']))
