"""Durable public events and versioned artifacts; no private reasoning storage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


class EventStore:
    def __init__(self, directory: Path, run_id: str):
        self.directory, self.run_id = directory, run_id
        self.started = time.perf_counter()
        self.db = sqlite3.connect(directory / 'events.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT, version INTEGER,
            owner TEXT, body TEXT, PRIMARY KEY(artifact_id,version));
        ''')
        self.export()  # Repair the JSONL projection after any interrupted append.

    def emit(self, event_type: str, actor='runtime', recipient=None, payload=None,
             task_id=None, parents=(), artifact_id=None, artifact_version=None,
             verification_status=None) -> dict:
        event = dict(run_id=self.run_id, timestamp=datetime.now(timezone.utc).isoformat(),
                     elapsed_seconds=time.perf_counter() - self.started, actor=actor,
                     recipient=recipient, event_type=event_type, task_id=task_id,
                     artifact_id=artifact_id, artifact_version=artifact_version,
                     parent_event_ids=list(parents), payload=payload or {},
                     verification_status=verification_status)
        with self.db:
            cur = self.db.execute('INSERT INTO events(body) VALUES (?)', ('{}',))
            event['event_id'] = cur.lastrowid
            self.db.execute('UPDATE events SET body=? WHERE event_id=?',
                            (json.dumps(event), cur.lastrowid))
        with (self.directory / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return event

    def artifact(self, artifact_id: str, owner: str, body: dict) -> int:
        with self.db:
            version = self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM artifacts WHERE artifact_id=?',
                                      (artifact_id,)).fetchone()[0]
            self.db.execute('INSERT INTO artifacts VALUES (?,?,?,?)',
                            (artifact_id, version, owner, json.dumps(body)))
        return version

    def events(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM events ORDER BY event_id')]

    def export(self):
        (self.directory / 'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in self.events()))

    def close(self):
        self.db.close()
