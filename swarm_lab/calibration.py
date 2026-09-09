"""Prepare and execute the explicitly bounded two-size Terra calibration."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .cli import read_events, verify_replay
from .ledger import Ledger
from .providers import request_payload
from .runtime import RunConfig, Runtime
from .store import write_json

SIZES = (18, 24)
LIMITS = {'call_limit': 6, 'token_limit': 100000, 'cost_limit': '2.00'}
ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_ID = 'terra-calibration-v1-2026-09-09'
AUTHORIZATION_DIR = ROOT/'runs'/'.authorizations'


def source_hashes() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'swarm_lab').glob('*.py'))}


def configs(price: dict) -> list[RunConfig]:
    result = [RunConfig(m=m, agents=1, condition='solo', mode='live', steps=3,
                        concurrency=1, max_retries=0, max_output=25000,
                        token_limit=LIMITS['token_limit'], cost_limit=LIMITS['cost_limit'],
                        model='gpt-5.6-terra', reasoning_effort='medium', timeout_seconds=120,
                        price=price, allow_live=True) for m in SIZES]
    for config in result:
        config.validate()
    return result


def prepare(directory: Path, price: dict) -> dict:
    """Freeze the matrix and protocol without loading a key or sending requests."""
    configuration = configs(price)
    protocol = (ROOT/'docs'/'calibration-protocol.md').read_text()
    estimates = []
    for config in configuration:
        # A full universe is a conservative incumbent-length bound, not a candidate
        # suggested to the model. Only sizes are used to estimate request framing.
        observation = dict(m=config.m, agent_id='agent-0', role='searcher', round=2,
                           private_best=list(range(1, config.m+1)), mailbox=[], peers=[],
                           condition='solo', task_id='task-2')
        payload = request_payload(config.model, config.max_output, config.reasoning_effort, observation)
        input_bound = len(json.dumps(payload).encode('utf-8')) + 1024
        input_rate = max(Decimal(price[k]) for k in
                         ('input_per_million', 'cached_input_per_million', 'cache_write_per_million'))
        cost = (input_bound*input_rate + config.max_output*Decimal(price['output_per_million']))/1000000
        estimates.append(dict(m=config.m, input_estimate_bound=input_bound,
                              per_call_tokens=input_bound+config.max_output,
                              per_call_cost=str(cost), calls=3))
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.SubprocessError, OSError):
        revision = 'unavailable'
    manifest = dict(schema_version=1, authorization_id=AUTHORIZATION_ID,
                    campaign_id='terra-calibration-'+str(uuid.uuid4()),
                    limits=dict(LIMITS), configs=[asdict(c) for c in configuration],
                    protocol=protocol, protocol_sha256=hashlib.sha256(protocol.encode()).hexdigest(),
                    source_sha256=source_hashes(), code_revision=revision,
                    reservation_bounds=estimates,
                    full_output_headroom_tokens=sum(e['per_call_tokens']*3 for e in estimates),
                    full_output_headroom_cost=str(sum((Decimal(e['per_call_cost'])*3
                                                       for e in estimates), Decimal(0))),
                    note='Six calls are an upper limit, not guaranteed: every dispatch must fit both shared ceilings.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/'manifest.json', manifest)
    with Ledger(directory/'usage.sqlite3') as ledger:
        ledger.create_campaign(manifest['campaign_id'], **LIMITS, price=price, simulated=False)
        ledger.export_campaign(manifest['campaign_id'], directory)
    return manifest


def select_difficulty(rows: list[dict]) -> dict:
    """Apply the predeclared rule; incomplete or failed evidence cannot select m."""
    def inconclusive(reason):
        return dict(status='inconclusive', selected_m=None, reason=reason)
    if len(rows) != 2 or [row.get('m') for row in rows] != list(SIZES):
        return inconclusive('Both planned sizes are required in the fixed order.')
    eligible = []
    for row in rows:
        summary = row.get('summary', {})
        usage = summary.get('usage', {})
        if (row.get('failure') or summary.get('decisions_completed') != 3
                or summary.get('invalid_claims') != 0
                or summary.get('oracle', {}).get('status') != 'optimal'
                or row.get('provider_outcomes') != ['completed']*3
                or row.get('verification_count') != 3
                or usage.get('attempts') != 3 or usage.get('unknown_attempts') != 0
                or usage.get('unknown_cost_attempts') != 0
                or summary.get('stopping_reason') not in {'solved', 'step_limit'}):
            return inconclusive('A planned run was incomplete, invalid, failed, or had unresolved usage.')
        first = row.get('first_candidate_size')
        if type(first) is not int or first > summary['upper_bound']:
            return inconclusive('The first decision has no valid, consistent candidate.')
        if first < summary['upper_bound']:
            eligible.append(row['m'])
    if eligible:
        return dict(status='eligible', selected_m=max(eligible),
                    reason='Prefer m=24 when not first-call optimal, otherwise m=18; this is single-run calibration.')
    return dict(status='saturated', selected_m=None,
                reason='Both first decisions reached the exact optimum; no quality headroom demonstrated.')


def execute(directory: Path, *, allow_live: bool = False, provider_factory=None) -> dict:
    """Run a prepared calibration once. Crashes require inspection, never replayed dispatch."""
    if not allow_live:
        raise ValueError('Execution requires explicit --allow-live and owner authorization.')
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest.get('limits') != LIMITS or manifest.get('schema_version') != 1:
        raise ValueError('Prepared calibration limits or schema do not match this runner.')
    if manifest.get('authorization_id') != AUTHORIZATION_ID:
        raise ValueError('Prepared calibration does not match this authorized stage.')
    config_rows = manifest.get('configs', [])
    if len(config_rows) != 2:
        raise ValueError('Prepared calibration requires exactly two configurations.')
    price = config_rows[0].get('price', {})
    expected = configs(price)  # Includes same-day model and price validation.
    if config_rows != [asdict(c) for c in expected]:
        raise ValueError('Prepared matrix differs from the approved fixed calibration.')
    protocol = (ROOT/'docs'/'calibration-protocol.md').read_text()
    if (manifest.get('source_sha256') != source_hashes()
            or manifest.get('protocol') != protocol
            or manifest.get('protocol_sha256') != hashlib.sha256(protocol.encode()).hexdigest()):
        raise ValueError('Source or protocol changed after preparation; no requests sent.')
    # The repository-level claim spans all output directories for this approval.
    # O_EXCL claims ownership across processes and persists after crashes. These
    # local guards cannot prevent deliberate deletion or copies to another host.
    AUTHORIZATION_DIR.mkdir(parents=True, exist_ok=True)
    with (AUTHORIZATION_DIR/(AUTHORIZATION_ID+'.json')).open('x') as handle:
        json.dump({'authorization_id':AUTHORIZATION_ID, 'campaign_id':manifest['campaign_id'],
                   'output_directory':str(directory.resolve()), 'automatic_resume':False}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    # Never remove either marker or recreate the ledger to repeat authorization.
    marker = directory/'execution-started.json'
    with marker.open('x') as handle:
        json.dump({'campaign_id':manifest['campaign_id'], 'automatic_resume':False}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    rows = []
    campaign_id = manifest['campaign_id']
    with Ledger(directory/'usage.sqlite3') as ledger:
        ledger.create_campaign(campaign_id, **LIMITS, price=price, simulated=False)
        if ledger.campaign_summary(campaign_id)['attempts']:
            raise ValueError('Prepared campaign already has attempts; refusing redispatch.')
        try:
            for config in expected:
                name = f'm{config.m}-solo'
                if rows and rows[-1].get('failure'):
                    rows.append(dict(m=config.m, path=name, failure='not_started_after_failure'))
                    continue
                row = dict(m=config.m, path=name)
                rows.append(row)
                try:
                    provider = provider_factory(config) if provider_factory else None
                    runtime = Runtime(config, directory/name, provider=provider,
                                      ledger_path=directory/'usage.sqlite3', campaign_id=campaign_id,
                                      stop_on_failure=True)
                    summary = asyncio.run(runtime.run())
                    row['summary'] = summary
                    verify_replay(directory/name)
                    events = read_events(directory/name)
                    verifications = [e for e in events if e['event_type']=='verification']
                    row['verification_count'] = len(verifications)
                    first = next((e for e in verifications if e['task_id']=='task-0'), None)
                    row['first_candidate_size'] = (len(first['payload']['candidate'])
                                                   if first and first['payload']['valid'] else None)
                    row['provider_outcomes'] = [e['payload']['outcome'] for e in events
                                                if e['event_type']=='provider_result']
                    usage = summary['usage']
                    if (summary['decisions_completed'] != 3 or summary['invalid_claims']
                            or summary['oracle']['status'] != 'optimal'
                            or usage['unknown_attempts'] or usage['unknown_cost_attempts']
                            or row['provider_outcomes'] != ['completed']*3):
                        row['failure'] = 'incomplete_or_invalid_run'
                except Exception as exc:
                    # Error classes are public; provider error bodies may contain secrets.
                    row['failure'] = type(exc).__name__
                ledger.export_campaign(campaign_id, directory)
                write_json(directory/'calibration.json', dict(campaign_id=campaign_id, runs=rows,
                    usage=ledger.campaign_summary(campaign_id), selection=select_difficulty(rows)))
        finally:
            ledger.export_campaign(campaign_id, directory)
            report = dict(campaign_id=campaign_id, runs=rows,
                          usage=ledger.campaign_summary(campaign_id), selection=select_difficulty(rows))
            write_json(directory/'calibration.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare', help='Freeze settings and shared budget without API calls')
    prep.add_argument('--price-file', type=Path, required=True)
    prep.add_argument('--out', type=Path, required=True)
    run = sub.add_parser('execute', help='Execute the prepared calibration once')
    run.add_argument('--allow-live', action='store_true')
    run.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            manifest = prepare(args.out, json.loads(args.price_file.read_text()))
            result = {k:manifest[k] for k in ('campaign_id','limits','reservation_bounds',
                                             'full_output_headroom_tokens','full_output_headroom_cost')}
        else:
            report = execute(args.out, allow_live=args.allow_live)
            result = dict(selection=report['selection'], actual_calls=report['usage']['actual_calls'],
                          total_tokens=report['usage']['total_tokens'],
                          calculated_model_cost=report['usage']['calculated_model_cost'],
                          outcomes=[{'m':row['m'],'gap':row.get('summary',{}).get('gap'),
                                     'failure':row.get('failure')} for row in report['runs']])
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f'Calibration stopped: {type(exc).__name__}. No automatic restart; inspect preserved artifacts.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
