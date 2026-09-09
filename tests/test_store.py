import json
from pathlib import Path
import tempfile
import unittest
from swarm_lab.store import EventStore


class StoreTests(unittest.TestCase):
    def test_restart_repairs_interrupted_projection_and_keeps_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            store=EventStore(path,'test-run')
            event=store.emit('candidate_submitted',actor='agent-0',payload={'candidate':[1,2,4]})
            self.assertEqual(store.artifact('candidate','agent-0',{'event':event['event_id']}),1)
            store.close()
            with (path/'events.jsonl').open('a') as f: f.write('{broken')
            store=EventStore(path,'test-run')
            self.assertEqual(store.artifact('candidate','agent-0',{'candidate':[1,2,4]}),2)
            self.assertEqual(len(store.events()),1)
            self.assertEqual(json.loads((path/'events.jsonl').read_text())['event_id'],1)
            store.close()
