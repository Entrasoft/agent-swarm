import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarm_lab.cli import read_events
from swarm_lab.runtime import RunConfig, Runtime


class RuntimeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'run'

    def test_failed_exploratory_decisions_still_receive_a_pull(self):
        runtime = Runtime(RunConfig(condition='adaptive',allocation='exploratory',
                                    steps=4,max_retries=0), self.path)
        with patch('swarm_lab.runtime.decide',return_value=None):
            result = asyncio.run(runtime.run())
        assignments = [event['recipient'] for event in read_events(self.path)
                       if event['event_type']=='assignment']
        self.assertEqual(assignments,['agent-0','agent-1','agent-2','agent-3'])
        self.assertEqual(result['decisions_completed'],0)
        self.assertEqual([value['pulls'] for value in runtime.stats.values()],[1,1,1,1])

    def test_repeated_source_ids_count_as_one_use(self):
        runtime = Runtime(RunConfig(condition='adaptive'),self.path)
        self.addCleanup(runtime.ledger.close)
        self.addCleanup(runtime.store.close)
        runtime.send(runtime.team[0], {
            'type':'share_artifact','recipient':'agent-1',
            'content':{'candidate':[1,2,4]},
        }, [], 'setup')
        agent = runtime.team[1]
        observation = runtime.observation(agent,'decision')
        source = observation['mailbox'][0]['event_id']
        assignment = runtime.store.emit('assignment',actor='scheduler',recipient=agent.agent_id,
                                        task_id='decision')
        runtime.accept(agent, {'candidate':[1,2,4],'message':None,
                               'used_event_ids':[source,source,True,999]},
                       observation, 'decision', assignment)
        self.assertEqual(runtime.reuse,1)
        used = [event for event in runtime.store.events() if event['event_type']=='artifact_used']
        self.assertEqual(len(used),1)
        self.assertEqual(used[0]['parent_event_ids'],[source])


if __name__ == '__main__':
    unittest.main()
