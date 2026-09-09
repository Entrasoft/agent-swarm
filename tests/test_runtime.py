import asyncio
from dataclasses import asdict
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from swarm_lab.cli import verify_replay, read_events
from swarm_lab.providers import ProviderResult, ProviderFailure
from swarm_lab.runtime import RunConfig, Runtime, OFFLINE_PRICE


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def run_case(self, name='case', **kwargs):
        path=self.base/name
        result=asyncio.run(Runtime(RunConfig(**kwargs),path).run())
        return result,read_events(path)

    def test_offline_quickstart_and_replay_agree(self):
        result,events=self.run_case(steps=24)
        self.assertEqual(result['lower_bound'],6)
        self.assertEqual(result['gap'],0)
        self.assertEqual(result['actual_model_calls'],0)
        self.assertEqual(result['actual_model_cost'],'0')
        self.assertTrue(verify_replay(self.base/'case')['verified'])
        self.assertEqual(len([e for e in events if e['event_type']=='task_completed']),24)
        self.assertEqual(len([e for e in events if e['event_type']=='usage']),24)
        self.assertLess(next(e['event_id'] for e in events if e['event_type']=='evaluation'),events[-1]['event_id'])

    def test_independent_observations_never_contain_other_findings(self):
        result,events=self.run_case(steps=12)
        private={f'agent-{i}':[] for i in range(4)}
        for event in events:
            if event['event_type']=='observation':
                value=event['payload']
                self.assertEqual(value['mailbox'],[])
                self.assertEqual(value['private_best'],private[event['actor']])
                self.assertEqual(set(value),{'m','agent_id','role','round','private_best','mailbox','peers','condition','task_id'})
            if event['event_type']=='verification' and event['payload']['valid']:
                candidate=event['payload']['candidate']
                if len(candidate)>len(private[event['recipient']]):
                    private[event['recipient']]=candidate
        self.assertEqual(result['messages'],0)

    def test_invalid_claims_cannot_change_bounds_or_travel(self):
        bad={'candidate':[1,2,3], 'message':{'type':'propose_claim','recipient':'agent-1',
             'content':{'candidate':[1,2,3]}}, 'used_event_ids':[]}
        with patch('swarm_lab.runtime.decide',return_value=bad):
            result,events=self.run_case(condition='adaptive',steps=4)
        self.assertEqual(result['lower_bound'],0)
        self.assertEqual(result['invalid_claims'],8)
        self.assertFalse(any(e['event_type']=='message_delivered' for e in events))

    def test_fixed_routes_and_replay_provenance(self):
        _,events=self.run_case(condition='fixed',steps=12)
        for e in events:
            if e['event_type']=='message_sent' and e['actor']!='agent-0':
                self.assertEqual(e['recipient'],'agent-0')
        self.assertTrue(verify_replay(self.base/'case')['verified'])
        self.assertTrue(any(e['event_type']=='artifact_used' for e in events))

    def test_budget_exhaustion_saves_run_and_cancels_owned_work(self):
        result,events=self.run_case(token_limit=1,steps=40)
        self.assertEqual(result['stopping_reason'],'budget_exhausted')
        self.assertEqual(result['decisions_completed'],0)
        self.assertTrue(any(e['event_type']=='task_cancelled' for e in events))
        self.assertTrue(verify_replay(self.base/'case')['verified'])

    def test_zero_oracle_timeout_does_not_prove_model_optimality(self):
        result,_=self.run_case(oracle_timeout=0,steps=8)
        self.assertEqual(result['upper_bound'],12)
        self.assertGreater(result['gap'],0)
        self.assertEqual(result['stopping_reason'],'step_limit')

    def test_duplicate_delivery_and_size_visibility_rules(self):
        runtime=Runtime(RunConfig(condition='adaptive'),self.base/'case')
        self.addCleanup(runtime.ledger.close)
        self.addCleanup(runtime.store.close)
        sent=runtime.store.emit('message_sent',actor='agent-0',recipient='agent-1',
                               payload={'type':'share_artifact','content':{'candidate':[1,2,4]}})
        self.assertTrue(runtime.deliver(sent))
        self.assertFalse(runtime.deliver(sent))
        self.assertEqual(len(runtime.by_id['agent-1'].mailbox),1)
        runtime.send(runtime.team[0],{'type':'share_artifact','recipient':'agent-1','content':'x'*5000},[],'x')
        self.assertEqual(len(runtime.by_id['agent-1'].mailbox),1)

    def test_exploratory_allocation_eventually_visits_each_agent(self):
        _,events=self.run_case(allocation='exploratory',condition='adaptive',steps=12)
        visited={e['recipient'] for e in events if e['event_type']=='assignment'}
        self.assertEqual(visited, {f'agent-{i}' for i in range(4)})

    def test_live_requires_explicit_configuration(self):
        with self.assertRaises(ValueError):
            RunConfig(mode='live').validate()
        with self.assertRaises(ValueError):
            RunConfig(condition='independent',allocation='exploratory').validate()

    def test_scripted_mode_is_labeled_and_never_calls_provider(self):
        result,events=self.run_case(mode='scripted',steps=4)
        self.assertEqual(result['mode'],'scripted')
        self.assertEqual(result['actual_model_calls'],0)
        self.assertEqual(result['lower_bound'],3)

    def test_retry_attempts_share_budget_and_unknown_charges_remain(self):
        class FakeProvider:
            count=0
            def estimate(self,observation): return 100
            def call(self,observation):
                self.count+=1
                if self.count==1: raise ProviderFailure('transport_unknown')
                return ProviderResult({'candidate':[1,2,4],'message':None,'used_event_ids':[]},
                    {'input_tokens':80,'output_tokens':20,'input_tokens_details':{'cached_tokens':0}},'request-fixture')
        price=dict(OFFLINE_PRICE,provider='openai',model='test-model',simulated=False,
                   source_url='https://developers.openai.com/api/docs/pricing',verified_on=time.strftime('%Y-%m-%d'))
        config=RunConfig(mode='live',allow_live=True,agents=1,condition='solo',steps=1,model='test-model',price=price)
        fake=FakeProvider()
        result=asyncio.run(Runtime(config,self.base/'case',provider=fake).run())
        self.assertEqual(fake.count,2)
        self.assertEqual(result['usage']['actual_calls'],2)
        self.assertEqual(result['usage']['unknown_attempts'],1)
        self.assertEqual(result['usage']['total_tokens'],100)
        self.assertGreater(result['usage']['committed_tokens'],100)


if __name__=='__main__': unittest.main()
