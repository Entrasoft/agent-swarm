"""Freeze and execute the authorized twenty-run Terra coordination comparison."""
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
import random
import sqlite3
import subprocess
import sys
import uuid

from .cli import read_events, verify_replay
from .ledger import Ledger
from .providers import request_payload
from .runtime import RunConfig, Runtime
from .store import write_json

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_ID = 'terra-comparison-v1-2026-09-09'
AUTHORIZATION_DIR = ROOT/'runs'/'.authorizations'
LIMITS = {'call_limit': 240, 'token_limit': 2_000_000, 'cost_limit': '20.00'}
RUN_LIMITS = {'call_limit': 12, 'token_limit': 100_000, 'cost_limit': '1.00'}
CONDITIONS = ('solo', 'independent', 'fixed', 'adaptive')
SCHEDULE_SEED = 20260909


def source_hashes() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'swarm_lab').glob('*.py'))}


def schedule() -> list[dict]:
    """Generate the declared block order independently of run UUIDs and outcomes."""
    rng = random.Random(SCHEDULE_SEED)
    result = []
    for repetition in range(1, 6):
        conditions = list(CONDITIONS)
        rng.shuffle(conditions)
        for condition in conditions:
            result.append(dict(order=len(result)+1, repetition=repetition, seed=repetition-1,
                               condition=condition, path=f'r{repetition:02d}-{condition}',
                               config_index=len(result)))
    return result


def configs(price: dict) -> list[RunConfig]:
    result = [RunConfig(m=24, agents=1 if row['condition']=='solo' else 4,
                       condition=row['condition'], mode='live', steps=RUN_LIMITS['call_limit'],
                       concurrency=1, seed=row['seed'], allocation='round_robin',
                       max_retries=0, max_output=25000, token_limit=RUN_LIMITS['token_limit'],
                       cost_limit=RUN_LIMITS['cost_limit'], model='gpt-5.6-terra',
                       reasoning_effort='medium', timeout_seconds=120, price=price, allow_live=True)
              for row in schedule()]
    for config in result:
        config.validate()
    return result


def reservation_bounds(configuration: list[RunConfig], price: dict) -> list[dict]:
    """Public framing estimates only; dispatch reserves each actual observation."""
    input_rate = max(Decimal(price[k]) for k in
                     ('input_per_million', 'cached_input_per_million', 'cache_write_per_million'))
    result = []
    for condition in CONDITIONS:
        config = next(c for c in configuration if c.condition == condition)
        observation = dict(m=24, agent_id='agent-0', role='coordinator' if condition in
                           {'fixed', 'adaptive'} else 'searcher', round=11,
                           private_best=list(range(1, 25)), mailbox=[],
                           peers=[f'agent-{i}' for i in range(1, config.agents)],
                           condition=condition, task_id='task-11')
        payload = request_payload(config.model, config.max_output, config.reasoning_effort, observation)
        no_mailbox_bound = len(json.dumps(payload).encode('utf-8')) + 1024
        # A JSON observation admitted by Runtime is <= context_bytes. Encoding it
        # as the request's JSON string at most doubles its ASCII byte length.
        # Keep the entire empty-observation framing too, a deliberate overbound.
        input_bound = (2*config.context_bytes + 1024 + len(json.dumps(request_payload(
                       config.model, config.max_output, config.reasoning_effort, {})).encode('utf-8'))
                       if condition in {'fixed', 'adaptive'} else no_mailbox_bound)
        cost = (input_bound*input_rate + config.max_output*Decimal(price['output_per_million']))/1_000_000
        result.append(dict(condition=condition, input_estimate_bound=input_bound,
                           no_mailbox_input_estimate_bound=no_mailbox_bound,
                           per_call_tokens=input_bound+config.max_output, per_call_cost=str(cost),
                           calls_per_run=12, runs=5))
    return result


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
            db.execute('CREATE TABLE comparison_preparations (campaign_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL)')
            db.execute('INSERT INTO comparison_preparations VALUES (?,?)',
                       (manifest['campaign_id'], _manifest_digest(manifest)))


def _check_frozen_manifest(directory: Path, manifest: dict):
    try:
        with closing(sqlite3.connect(directory/'usage.sqlite3')) as db:
            row = db.execute('SELECT manifest_sha256 FROM comparison_preparations WHERE campaign_id=?',
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
    write_json(directory/'comparison.json', report)
    return report


def prepare(directory: Path, price: dict) -> dict:
    """Preallocate every allowance and freeze all inputs without credentials or API calls."""
    configuration = configs(price)
    protocol = (ROOT/'docs'/'live-comparison-protocol.md').read_text()
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.SubprocessError, OSError):
        revision = 'unavailable'
    rows = [dict(row, run_id=str(uuid.uuid4())) for row in schedule()]
    estimates = reservation_bounds(configuration, price)
    manifest = dict(schema_version=1, authorization_id=AUTHORIZATION_ID,
                    campaign_id='terra-comparison-'+str(uuid.uuid4()), prepared_at=_now(),
                    limits=dict(LIMITS), run_limits=dict(RUN_LIMITS), schedule_seed=SCHEDULE_SEED,
                    runs=rows, configs=[asdict(c) for c in configuration],
                    protocol=protocol, protocol_sha256=hashlib.sha256(protocol.encode()).hexdigest(),
                    source_sha256=source_hashes(), code_revision=revision,
                    reservation_bounds=estimates,
                    full_output_headroom_tokens=sum(e['per_call_tokens']*60 for e in estimates),
                    full_output_headroom_cost=str(sum((Decimal(e['per_call_cost'])*60
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
        raise ValueError('Prepared comparison does not match the authorized limits and stage.')
    config_rows = manifest.get('configs', [])
    if len(config_rows) != 20:
        raise ValueError('Prepared comparison requires exactly twenty configurations.')
    expected = configs(config_rows[0].get('price', {}))
    if config_rows != [asdict(config) for config in expected]:
        raise ValueError('Prepared configurations differ from the approved comparison.')
    rows = manifest.get('runs', [])
    if len(rows) != 20:
        raise ValueError('Prepared comparison requires all twenty scheduled rows.')
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
        suffix = campaign_id.removeprefix('terra-comparison-')
        if campaign_id != 'terra-comparison-'+str(uuid.UUID(suffix)):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid prepared campaign ID.') from None
    protocol = (ROOT/'docs'/'live-comparison-protocol.md').read_text()
    if (manifest.get('source_sha256') != source_hashes() or manifest.get('protocol') != protocol
            or manifest.get('protocol_sha256') != hashlib.sha256(protocol.encode()).hexdigest()):
        raise ValueError('Source or protocol changed after preparation; no requests sent.')
    if manifest.get('reservation_bounds') != reservation_bounds(expected, expected[0].price):
        raise ValueError('Prepared reservation estimates changed.')
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


def execute(directory: Path, *, allow_live: bool = False, provider_factory=None) -> dict:
    """Execute once; ambiguity consumes authorization and requires manual review."""
    if not allow_live:
        raise ValueError('Execution requires explicit --allow-live and owner authorization.')
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    configuration = _validate_manifest(manifest)
    if not (directory/'usage.sqlite3').is_file():
        raise ValueError('Prepared durable ledger is missing; refusing to recreate it.')
    _check_frozen_manifest(directory, manifest)
    rows = [dict(row, status='unstarted') for row in manifest['runs']]
    with Ledger(directory/'usage.sqlite3') as ledger:
        campaign_id = manifest['campaign_id']
        initial = ledger.campaign_summary(campaign_id)
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
                    verify_replay(directory/row['path'])
                    events = read_events(directory/row['path'])
                    row['verification_count'] = sum(e['event_type']=='verification' for e in events)
                    row['provider_outcomes'] = [e['payload']['outcome'] for e in events
                                               if e['event_type']=='provider_result']
                    reason = summary['stopping_reason']
                    stop_reason = (_halt_reason(ledger.campaign_summary(campaign_id))
                                   or _halt_reason(summary['usage'], scope='run'))
                    if stop_reason or reason in {'interrupted', 'worker_failure', 'unresolved_usage'}:
                        stop_reason = stop_reason or reason
                        row.update(status='interrupted', failure=stop_reason)
                    elif reason == 'budget_exhausted':
                        row['status'] = 'budget_stopped'
                    elif reason in {'provider_failure', 'invalid_candidate'}:
                        row.update(status='failed', failure=reason)
                    elif reason in {'solved', 'step_limit'} and summary['usage']['attempts'] == 12:
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
                    stop_reason = 'interrupted_or_unhandled_exception'
                row['finished_at'] = _now()
                status = 'halted' if stop_reason else 'running'
                report = _report(manifest, rows, ledger, directory, status, stop_reason)
                usage = ledger.summary(row['run_id'])
                print(f"{row['order']:02d}/20 {row['path']}: {row['status']}; "
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
    prep = sub.add_parser('prepare', help='Freeze the comparison and allocate budgets without API calls')
    prep.add_argument('--price-file', type=Path, required=True)
    prep.add_argument('--out', type=Path, required=True)
    run = sub.add_parser('execute', help='Execute the prepared comparison once')
    run.add_argument('--allow-live', action='store_true')
    run.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
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
        print(f'Comparison stopped: {type(exc).__name__}. No automatic restart; inspect preserved artifacts.',
              file=sys.stderr)
        return 1
    return 1 if args.command == 'execute' and report['status'] == 'halted' else 0


if __name__ == '__main__':
    raise SystemExit(main())
