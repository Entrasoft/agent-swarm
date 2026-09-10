"""Prepare a proposed solo feedback study; this command cannot execute inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import subprocess

from .providers import request_payload
from .runtime import RunConfig
from .store import write_json

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('private_best_only', 'history_feedback')
SCHEDULE_SEED = 20260910
LIMITS = dict(call_limit=72, token_limit=600_000, cost_limit='6.00')
RUN_LIMITS = dict(call_limit=12, token_limit=100_000, cost_limit='1.00')


def schedule() -> list[dict]:
    rng = random.Random(SCHEDULE_SEED)
    rows = []
    for block in range(1, 4):
        arms = list(ARMS)
        rng.shuffle(arms)
        for arm in arms:
            rows.append(dict(order=len(rows)+1, block=block, seed=block-1, arm=arm,
                             path=f'r{block:02d}-{arm}', status='proposed'))
    return rows


def proposed_configs(price: dict) -> list[RunConfig]:
    """Intentionally fail live validation until a separate execution is authorized."""
    return [RunConfig(m=24, agents=1, condition='solo', mode='live', steps=12,
                      concurrency=1, seed=row['seed'], max_retries=0, max_output=25000,
                      token_limit=RUN_LIMITS['token_limit'], cost_limit=RUN_LIMITS['cost_limit'],
                      model='gpt-5.6-terra', reasoning_effort='medium', timeout_seconds=120,
                      decision_protocol='feedback-v0.2', memory_mode=row['arm'], history_limit=8,
                      price=dict(price), allow_live=False) for row in schedule()]


def reservation_bounds(config: RunConfig) -> dict:
    # Each admitted observation is <= context_bytes; embedding its JSON in the
    # request string can at most double that ASCII length. Overbound both arms
    # equally. These estimates are reservations, not measured or forecast spend.
    framing = len(json.dumps(request_payload(config.model, config.max_output,
                                            config.reasoning_effort, {})).encode())
    input_bound = 2*config.context_bytes + framing + 1024
    price = config.price
    input_rate = max(Decimal(price[key]) for key in ('input_per_million',
                     'cached_input_per_million', 'cache_write_per_million'))
    cost = (input_bound*input_rate + config.max_output*Decimal(price['output_per_million'])) / 1_000_000
    return dict(input_estimate_bound=input_bound, per_call_tokens=input_bound+config.max_output,
                per_call_cost=str(cost), twelve_full_output_tokens=12*(input_bound+config.max_output),
                twelve_full_output_cost=str(12*cost),
                full_output_calls_guaranteed=False,
                note='Fixed allowances can stop a run before twelve decisions; reserve each actual observation before dispatch.')


def prepare(directory: Path) -> dict:
    """Freeze public proposal inputs without opening credentials or a usage ledger."""
    price = json.loads((ROOT/'configs'/'gpt-5.6-terra-price.json').read_text())
    configs = proposed_configs(price)
    documents = {}
    for name in ('feedback-v02-protocol.md', 'feedback-v02-budget-proposal.md'):
        body = (ROOT/'docs'/name).read_text()
        documents[name] = dict(text=body, sha256=hashlib.sha256(body.encode()).hexdigest())
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
    except (subprocess.SubprocessError, OSError):
        revision, dirty = 'unavailable', None
    manifest = dict(schema_version=1, study='solo-feedback-v0.2', status='proposal_only',
                    execution_authorized=False, prepared_at=datetime.now(timezone.utc).isoformat(),
                    limits=dict(LIMITS), run_limits=dict(RUN_LIMITS), schedule_seed=SCHEDULE_SEED,
                    runs=schedule(), configs=[asdict(config) for config in configs], documents=documents,
                    code_revision=revision, working_tree_dirty=dirty,
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted((ROOT/'swarm_lab').glob('*.py'))},
                    price_status='Historical reference only; reverify official rates before any future live approval.',
                    reservation_bounds=reservation_bounds(configs[0]),
                    actual_model_calls=0, actual_model_cost='0',
                    note='No execution command or authorization claim is provided. A future approved campaign needs a fresh durable shared ledger and single-execution guard.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/'proposal.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('prepare', help='Freeze a proposal without credentials or API calls')
    command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = prepare(args.out)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Error: {exc}\n')
    print(json.dumps(dict(out=str(args.out), status=manifest['status'], limits=manifest['limits'],
                          actual_model_calls=0, actual_model_cost='0'), indent=2))


if __name__ == '__main__':
    main()
