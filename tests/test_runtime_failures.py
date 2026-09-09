"""Concurrent provider failures must preserve telemetry and stop further calls."""

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from swarm_lab.cli import read_events
from swarm_lab.ledger import Ledger
from swarm_lab.providers import ProviderFailure, ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE, RunConfig, Runtime


class CoordinatedFakeProvider:
    """Two real Python worker threads, with no network calls or credentials."""

    def __init__(self, malformed_was_processed, second_fails=False):
        self.both_started = threading.Barrier(2)
        self.malformed_was_processed = malformed_was_processed
        self.second_fails = second_fails
        self.calls = []

    def estimate(self, observation):
        return 100

    def call(self, observation):
        agent = observation["agent_id"]
        self.calls.append(agent)
        if self.calls.count(agent) == 1:
            self.both_started.wait(timeout=3)
        if agent == "agent-0":
            return ProviderResult(None, {"input_tokens": -1, "output_tokens": 0},
                                  request_id="malformed-fixture")
        if not self.malformed_was_processed.wait(timeout=3):
            raise RuntimeError("malformed sibling was not processed")
        if self.second_fails:
            raise ProviderFailure("transport_unknown", "failed-fixture")
        return ProviderResult({"candidate": [1, 2, 4], "message": None, "used_event_ids": []},
                              {"input_tokens": 80, "output_tokens": 20},
                              request_id="valid-fixture")


class RuntimeFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "run"

    def make_runtime(self, second_fails=False):
        price = dict(OFFLINE_PRICE, provider="openai", model="test-model", simulated=False,
                     source_url="https://developers.openai.com/api/docs/pricing",
                     verified_on=time.strftime("%Y-%m-%d"))
        config = RunConfig(mode="live", allow_live=True, agents=3, concurrency=2,
                           condition="independent", steps=6, max_retries=1,
                           model="test-model", price=price)
        malformed_was_processed = threading.Event()
        provider = CoordinatedFakeProvider(malformed_was_processed, second_fails)
        runtime = Runtime(config, self.directory, provider=provider)
        original_settle = runtime.ledger.settle

        def signal_malformed(*args, **kwargs):
            try:
                return original_settle(*args, **kwargs)
            except ValueError:
                # Releasing the delayed thread here guarantees the first usage
                # validation has failed before the sibling response can settle.
                malformed_was_processed.set()
                raise

        runtime.ledger.settle = signal_malformed
        return runtime, provider

    def test_drain_started_sibling_and_persist_usage_before_closing_stores(self):
        runtime, provider = self.make_runtime()
        with self.assertRaisesRegex(ValueError, "input_tokens"):
            asyncio.run(runtime.run())
        self.assertCountEqual(provider.calls, ["agent-0", "agent-1"])
        with Ledger(self.directory / "usage.sqlite3") as restarted:
            entries = {entry["agent"]: entry for entry in restarted.entries(runtime.run_id)}
            summary = restarted.summary(runtime.run_id)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries["agent-1"]["request_id"], "valid-fixture")
        self.assertEqual(entries["agent-1"]["total_tokens"], 100)
        self.assertEqual(entries["agent-1"]["outcome"], "completed")
        self.assertEqual(summary["unknown_attempts"], 1)
        self.assertGreater(entries["agent-0"]["reserved_tokens"], 0)
        exported = json.loads((self.directory / "usage-summary.json").read_text())
        self.assertEqual(exported["total_tokens"], 100)
        self.assertEqual(exported["committed_tokens"], summary["committed_tokens"])
        events = read_events(self.directory)
        completed = next(event for event in events if event["event_type"] == "task_completed")
        interrupted = next(event for event in events if event["event_type"] == "run_interrupted")
        self.assertEqual(completed["actor"], "agent-1")
        self.assertLess(completed["event_id"], interrupted["event_id"])

    def test_no_retry_or_queued_dispatch_after_sibling_failure(self):
        runtime, provider = self.make_runtime(second_fails=True)
        with self.assertRaisesRegex(ValueError, "input_tokens"):
            asyncio.run(runtime.run())
        self.assertCountEqual(provider.calls, ["agent-0", "agent-1"])
        with Ledger(self.directory / "usage.sqlite3") as restarted:
            entries = restarted.entries(runtime.run_id)
        self.assertEqual(len(entries), 2)
        self.assertEqual({entry["attempt"] for entry in entries}, {0})
        failed = next(entry for entry in entries if entry["agent"] == "agent-1")
        self.assertEqual(failed["outcome"], "transport_unknown")
        self.assertIsNone(failed["usage"])
        self.assertGreater(failed["reserved_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
