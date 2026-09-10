"""Freeze and execute the separately authorized six-run Terra feedback pilot."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

from .cli import read_events, verify_replay
from .feedback import (ARMS, LIMITS, RUN_LIMITS, SCHEDULE_SEED,
                       proposed_configs, reservation_bounds as proposed_reservation_bounds,
                       schedule as proposed_schedule)
from .ledger import Ledger
from .runtime import RunConfig, Runtime
from .store import write_json

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_ID = 'terra-feedback-v02-2026-09-09'
AUTHORIZATION_DIR = ROOT/'runs'/'.authorizations'
DOCUMENTS = ('feedback-v02-protocol.md', 'feedback-v02-budget-proposal.md',
             'feedback-v02-execution.md')


def source_hashes() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'swarm_lab').glob('*.py'))}


def schedule() -> list[dict]:
    """Preserve the proposed order; add only the execution configuration index."""
    return [dict({key: value for key, value in row.items() if key != 'status'},
                 config_index=index) for index, row in enumerate(proposed_schedule())]


def configs(price: dict) -> list[RunConfig]:
    result = proposed_configs(price)
    for config in result:
        config.allow_live = True
        config.validate()
    return result


def reservation_bounds(configuration: list[RunConfig], price: dict) -> list[dict]:
    """Both arms retain the proposal's equal conservative input overbound."""
    if any(config.price != price for config in configuration):
        raise ValueError('All configurations must share the frozen price snapshot.')
    return [dict(proposed_reservation_bounds(next(config for config in configuration
                                                if config.memory_mode == arm)),
                 arm=arm, calls_per_run=RUN_LIMITS['call_limit'], runs=3) for arm in ARMS]


def _documents() -> dict:
    result = {}
    for name in DOCUMENTS:
        body = (ROOT/'docs'/name).read_text()
        result[name] = dict(text=body, sha256=hashlib.sha256(body.encode()).hexdigest())
    return result


def _git_state() -> tuple[str, bool | None]:
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT,
                                            text=True, stderr=subprocess.DEVNULL))
    except (subprocess.SubprocessError, OSError):
        return 'unavailable', None
    return revision, dirty


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_digest(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _freeze_manifest(directory: Path, manifest: dict):
    # This separate durable receipt binds even descriptive manifest fields and
    # run UUIDs to preparation. It is an integrity guard, not an adversarial vault.
    with closing(sqlite3.connect(directory/'usage.sqlite3')) as db:
        db.execute('PRAGMA synchronous=FULL')
        with db:
            db.execute('CREATE TABLE feedback_preparations (campaign_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL)')
            db.execute('INSERT INTO feedback_preparations VALUES (?,?)',
                       (manifest['campaign_id'], _manifest_digest(manifest)))


def _check_frozen_manifest(directory: Path, manifest: dict):
    try:
        with closing(sqlite3.connect(directory/'usage.sqlite3')) as db:
            row = db.execute('SELECT manifest_sha256 FROM feedback_preparations WHERE campaign_id=?',
                             (manifest['campaign_id'],)).fetchone()
    except sqlite3.DatabaseError:
        raise ValueError('Prepared manifest receipt is missing or damaged.') from None
    if row is None or row[0] != _manifest_digest(manifest):
        raise ValueError('Manifest differs from its durable preparation receipt.')


def _report(manifest: dict, rows: list[dict], ledger: Ledger, directory: Path,
            status: str, stop_reason: str | None) -> dict:
    ledger.export_campaign(manifest['campaign_id'], directory)
    report = dict(schema_version=1, authorization_id=AUTHORIZATION_ID,
                  campaign_id=manifest['campaign_id'], status=status, stop_reason=stop_reason,
                  runs=rows, usage=ledger.campaign_summary(manifest['campaign_id']))
    write_json(directory/'feedback-campaign.json', report)
    return report


def prepare(directory: Path, price: dict) -> dict:
    """Preallocate every allowance and freeze all inputs without credentials or API calls."""
    configuration = configs(price)
    documents = _documents()
    protocol = documents['feedback-v02-protocol.md']['text']
    revision, dirty = _git_state()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Preparation requires an identifiable committed source revision.')
    rows = [dict(row, run_id=str(uuid.uuid4())) for row in schedule()]
    estimates = reservation_bounds(configuration, price)
    manifest = dict(schema_version=1, authorization_id=AUTHORIZATION_ID,
                    campaign_id='terra-feedback-v02-'+str(uuid.uuid4()), prepared_at=_now(),
                    limits=dict(LIMITS), run_limits=dict(RUN_LIMITS), schedule_seed=SCHEDULE_SEED,
                    runs=rows, configs=[asdict(c) for c in configuration],
                    documents=documents,
                    protocol=protocol, protocol_sha256=hashlib.sha256(protocol.encode()).hexdigest(),
                    source_sha256=source_hashes(), code_revision=revision, working_tree_dirty=dirty,
                    reservation_bounds=estimates,
                    full_output_headroom_tokens=sum(e['per_call_tokens']*36 for e in estimates),
                    full_output_headroom_cost=str(sum((Decimal(e['per_call_cost'])*36
                                                       for e in estimates), Decimal(0))),
                    note='All counts are ceilings. Every dispatch must fit its fixed run allowance and the shared campaign allowance.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/'manifest.json', manifest)
    with Ledger(directory/'usage.sqlite3') as ledger:
        ledger.create_campaign(manifest['campaign_id'], **LIMITS, price=price, simulated=False)
        for row, config in zip(rows, configuration):
            ledger.create_run(row['run_id'], config.token_limit, config.cost_limit, price,
                              simulated=False, campaign_id=manifest['campaign_id'])
        _freeze_manifest(directory, manifest)
        _report(manifest, [dict(row, status='unstarted') for row in rows], ledger,
                directory, 'prepared', None)
    return manifest


def _validate_manifest(manifest: dict) -> list[RunConfig]:
    if (manifest.get('schema_version') != 1 or manifest.get('authorization_id') != AUTHORIZATION_ID
            or manifest.get('limits') != LIMITS or manifest.get('run_limits') != RUN_LIMITS
            or manifest.get('schedule_seed') != SCHEDULE_SEED):
        raise ValueError('Prepared feedback campaign does not match the authorized limits and stage.')
    config_rows = manifest.get('configs', [])
    if len(config_rows) != 6:
        raise ValueError('Prepared feedback campaign requires exactly six configurations.')
    expected = configs(config_rows[0].get('price', {}))
    if config_rows != [asdict(config) for config in expected]:
        raise ValueError('Prepared configurations differ from the approved feedback campaign.')
    rows = manifest.get('runs', [])
    if len(rows) != 6:
        raise ValueError('Prepared feedback campaign requires all six scheduled rows.')
    identifiers = set()
    for row, planned in zip(rows, schedule()):
        run_id = row.get('run_id')
        try:
            if str(uuid.UUID(run_id)) != run_id or run_id in identifiers:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Run IDs must be unique UUIDs.') from None
        identifiers.add(run_id)
        if row != dict(planned, run_id=run_id):
            raise ValueError('Prepared execution order or run paths changed.')
    campaign_id = manifest.get('campaign_id', '')
    try:
        suffix = campaign_id.removeprefix('terra-feedback-v02-')
        if campaign_id != 'terra-feedback-v02-'+str(uuid.UUID(suffix)):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid prepared campaign ID.') from None
    documents = _documents()
    protocol = documents['feedback-v02-protocol.md']['text']
    if (manifest.get('source_sha256') != source_hashes() or manifest.get('documents') != documents
            or manifest.get('protocol') != protocol
            or manifest.get('protocol_sha256') != hashlib.sha256(protocol.encode()).hexdigest()):
        raise ValueError('Source or protocol changed after preparation; no requests sent.')
    estimates = reservation_bounds(expected, expected[0].price)
    if (manifest.get('reservation_bounds') != estimates
            or manifest.get('full_output_headroom_tokens') != sum(e['per_call_tokens']*36 for e in estimates)
            or manifest.get('full_output_headroom_cost') != str(sum(
                (Decimal(e['per_call_cost'])*36 for e in estimates), Decimal(0)))):
        raise ValueError('Prepared reservation estimates changed.')
    if (not isinstance(manifest.get('code_revision'), str)
            or not re.fullmatch(r'[0-9a-f]{40}', manifest['code_revision'])
            or type(manifest.get('working_tree_dirty')) is not bool):
        raise ValueError('Prepared source revision metadata is invalid.')
    return expected


def _claim(path: Path, payload: dict):
    with path.open('x') as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())


def _halt_reason(usage: dict, *, scope: str = 'aggregate') -> str | None:
    if usage['pending_attempts'] or usage['unknown_attempts'] or usage['unknown_cost_attempts']:
        return 'unresolved_usage_or_dispatch'
    if (usage.get('call_overshoot', 0) or usage['token_overshoot']
            or Decimal(usage['cost_overshoot']) > 0):
        return scope+'_ceiling_exceeded'
    return None


def _record_evidence(row: dict, directory: Path) -> None:
    """Retain trace counts and replay status for complete and partial runs alike."""
    events = read_events(directory/row['path'])
    verifications = [event['payload'] for event in events if event['event_type'] == 'verification']
    valid = [payload for payload in verifications if payload['valid']]
    row.update(verification_count=len(verifications), valid_candidate_count=len(valid),
               unique_valid_candidates=len({tuple(sorted(payload['candidate'])) for payload in valid}),
               invalid_mathematical_candidates=len(verifications)-len(valid),
               protocol_failures=sum(event['event_type'] == 'invalid_action' for event in events),
               provider_outcomes=[event['payload']['outcome'] for event in events
                                  if event['event_type'] in {'provider_result', 'provider_failure'}])
    row['replay'] = verify_replay(directory/row['path'])


def execute(directory: Path, *, allow_live: bool = False, provider_factory=None) -> dict:
    """Execute once; ambiguity consumes authorization and requires manual review."""
    if not allow_live:
        raise ValueError('Execution requires explicit --allow-live and owner authorization.')
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    configuration = _validate_manifest(manifest)
    # Test factories supply local fixtures. A real dispatch must come from the
    # exact committed, clean checkout captured during preparation.
    if provider_factory is None:
        revision, dirty = _git_state()
        if (manifest['working_tree_dirty'] is not False or dirty is not False
                or revision != manifest['code_revision']):
            raise ValueError('Live execution requires the unchanged clean committed preparation checkout.')
    if not (directory/'usage.sqlite3').is_file():
        raise ValueError('Prepared durable ledger is missing; refusing to recreate it.')
    _check_frozen_manifest(directory, manifest)
    rows = [dict(row, status='unstarted') for row in manifest['runs']]
    with Ledger(directory/'usage.sqlite3') as ledger:
        campaign_id = manifest['campaign_id']
        try:
            initial = ledger.campaign_summary(campaign_id)
        except (KeyError, sqlite3.DatabaseError):
            raise ValueError('Prepared campaign allocations are missing or damaged.') from None
        if initial['attempts'] or set(initial['run_ids']) != {row['run_id'] for row in rows}:
            raise ValueError('Prepared campaign has attempts or changed allocations; refusing redispatch.')
        # Idempotent creation checks compare stored prices and budgets, never reset them.
        ledger.create_campaign(campaign_id, **LIMITS, price=configuration[0].price, simulated=False)
        for row, config in zip(rows, configuration):
            ledger.create_run(row['run_id'], config.token_limit, config.cost_limit, config.price,
                              simulated=False, campaign_id=campaign_id)
            if (directory/row['path']).exists():
                raise ValueError('A planned run path already exists; refusing unsafe reuse.')
        AUTHORIZATION_DIR.mkdir(parents=True, exist_ok=True)
        claim = dict(authorization_id=AUTHORIZATION_ID, campaign_id=campaign_id,
                     output_directory=str(directory.resolve()), automatic_resume=False)
        _claim(AUTHORIZATION_DIR/(AUTHORIZATION_ID+'.json'), claim)
        _claim(directory/'execution-started.json', claim)
        status, stop_reason = 'running', None
        report = _report(manifest, rows, ledger, directory, status, stop_reason)
        try:
            for row, config in zip(rows, configuration):
                row.update(status='running', started_at=_now())
                _report(manifest, rows, ledger, directory, status, stop_reason)
                try:
                    provider = provider_factory(config) if provider_factory else None
                    runtime = Runtime(config, directory/row['path'], provider=provider,
                                      ledger_path=directory/'usage.sqlite3', campaign_id=campaign_id,
                                      stop_on_failure=True, run_id=row['run_id'])
                    summary = asyncio.run(runtime.run())
                    row['summary'] = summary
                    _record_evidence(row, directory)
                    reason = summary['stopping_reason']
                    stop_reason = (_halt_reason(ledger.campaign_summary(campaign_id))
                                   or _halt_reason(summary['usage'], scope='run'))
                    if stop_reason or reason in {'interrupted', 'worker_failure', 'unresolved_usage'}:
                        stop_reason = stop_reason or reason
                        row.update(status='interrupted', failure=stop_reason)
                    elif reason == 'budget_exhausted':
                        row['status'] = 'budget_stopped'
                    elif reason in {'provider_failure', 'protocol_failure'}:
                        row.update(status='failed', failure=reason)
                    elif (reason in {'solved', 'step_limit'}
                          and summary['usage']['attempts'] == RUN_LIMITS['call_limit']):
                        row['status'] = 'completed'
                    else:
                        row.update(status='interrupted', failure='unexpected_run_outcome')
                        stop_reason = 'unexpected_run_outcome'
                except BaseException as exc:
                    # Never serialize exception messages, request bodies or provider internals.
                    row.update(status='interrupted', failure=type(exc).__name__)
                    summary_path = directory/row['path']/'summary.json'
                    if summary_path.is_file():
                        try:
                            row['summary'] = json.loads(summary_path.read_text())
                        except (OSError, ValueError):
                            pass
                    try:
                        _record_evidence(row, directory)
                    except Exception as replay_exc:
                        row['replay'] = dict(verified=False, failure=type(replay_exc).__name__)
                    stop_reason = 'interrupted_or_unhandled_exception'
                row['finished_at'] = _now()
                status = 'halted' if stop_reason else 'running'
                report = _report(manifest, rows, ledger, directory, status, stop_reason)
                usage = ledger.summary(row['run_id'])
                print(f"{row['order']:02d}/06 {row['path']}: {row['status']}; "
                      f"calls={usage['actual_calls']} tokens={usage['total_tokens']} "
                      f"calculated_USD={usage['calculated_model_cost']}", flush=True)
                if stop_reason:
                    break
            if not stop_reason:
                status = 'completed'
        except BaseException as exc:
            status, stop_reason = 'halted', 'interrupted_or_unhandled_exception'
            for row in rows:
                if row['status'] == 'running':
                    row.update(status='interrupted', failure=type(exc).__name__, finished_at=_now())
        finally:
            report = _report(manifest, rows, ledger, directory, status, stop_reason)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare', help='Freeze the approved feedback pilot and allocate budgets without API calls')
    prep.add_argument('--price-file', type=Path, required=True)
    prep.add_argument('--out', type=Path, required=True)
    run = sub.add_parser('execute', help='Execute the prepared feedback pilot once')
    run.add_argument('--allow-live', action='store_true')
    run.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            revision, dirty = _git_state()
            if dirty is not False or not re.fullmatch(r'[0-9a-f]{40}', revision):
                raise ValueError('Live campaign preparation requires a clean committed checkout.')
            manifest = prepare(args.out, json.loads(args.price_file.read_text()))
            result = {key: manifest[key] for key in ('campaign_id', 'limits', 'run_limits',
                                                    'reservation_bounds')}
        else:
            report = execute(args.out, allow_live=args.allow_live)
            result = dict(status=report['status'], stop_reason=report['stop_reason'],
                          actual_calls=report['usage']['actual_calls'],
                          total_tokens=report['usage']['total_tokens'],
                          calculated_model_cost=report['usage']['calculated_model_cost'])
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f'Feedback pilot stopped: {type(exc).__name__}. No automatic restart; inspect preserved artifacts.',
              file=sys.stderr)
        return 1
    return 1 if args.command == 'execute' and report['status'] == 'halted' else 0


if __name__ == '__main__':
    raise SystemExit(main())
