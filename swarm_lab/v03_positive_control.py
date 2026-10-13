"""Coordination v0.3, Stage 1: offline positive control.

Runs the slot-restricted algorithmic agents in a private-archive arm and a
team-archive arm on every frozen target for seeds 0-9, replays every run, and
evaluates the gate from docs/coordination-v03-proposal.md: the shared arm must
beat the independent arm, ranked by (d, fewer minimum-weight codewords), on
every target in every seed. No model is called.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from .archive_runtime import ArchiveConfig, ArchiveRuntime, verify_replay
from .store import write_json

SEEDS = tuple(range(10))
ARMS = ('pc-independent', 'pc-shared')


def run_one(job: tuple) -> dict:
    target, arm, seed, directory = job
    config = ArchiveConfig(target={key: target[key] for key in ('q', 'n', 'k', 'lower', 'upper')},
                           arm=arm, seed=seed)
    summary = ArchiveRuntime(config, Path(directory)).run()
    replay = verify_replay(Path(directory))
    best = summary['best']
    return dict(target=config.target, arm=arm, seed=seed, path=str(Path(directory).name),
                d=best['d'] if best else None,
                min_weight_count=best['min_weight_count'] if best else None,
                rounds=summary['rounds'], decisions=summary['decisions'], valid=summary['valid'],
                invalid=summary['invalid'], cross_agent_extensions=summary['cross_agent_extensions'],
                best_lineage_crosses_agents=summary['best_lineage_crosses_agents'],
                beats_record=summary['beats_record'], simulated_tokens=summary['simulated_tokens'],
                replay_verified=replay['verified'])


def rank(row: dict) -> tuple:
    return (-1, 0) if row['d'] is None else (row['d'], -row['min_weight_count'])


def gate(rows: list[dict], targets: list[dict]) -> dict:
    comparisons = []
    for seed in SEEDS:
        for target in targets:
            key = (target['q'], target['n'], target['k'])
            pair = {row['arm']: row for row in rows if row['seed'] == seed
                    and (row['target']['q'], row['target']['n'], row['target']['k']) == key}
            comparisons.append(dict(seed=seed, target=list(key),
                                    shared=[pair['pc-shared']['d'], pair['pc-shared']['min_weight_count']],
                                    independent=[pair['pc-independent']['d'],
                                                 pair['pc-independent']['min_weight_count']],
                                    shared_wins=rank(pair['pc-shared']) > rank(pair['pc-independent'])))
    wins = sum(c['shared_wins'] for c in comparisons)
    return dict(rule='shared beats independent on every target in every seed',
                comparisons=len(comparisons), shared_wins=wins,
                passed=wins == len(comparisons) and all(r['replay_verified'] for r in rows),
                detail=comparisons)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='swarm_lab.v03_positive_control', description=__doc__)
    parser.add_argument('--targets', type=Path, default=Path('configs/v03/targets.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        parser.exit(2, 'Error: output directory must be empty.\n')
    targets = json.loads(args.targets.read_text())['targets']
    jobs = [(target, arm, seed, args.out / f"q{target['q']}-n{target['n']}-k{target['k']}-{arm}-s{seed}")
            for seed in SEEDS for target in targets for arm in ARMS]
    started = datetime.now(timezone.utc).isoformat()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--', 'swarm_lab'], text=True))
    except (subprocess.SubprocessError, OSError):
        revision, dirty = 'unavailable', None
    result = dict(stage='v0.3 Stage 1 positive control', started=started,
                  finished=datetime.now(timezone.utc).isoformat(), code_revision=revision,
                  source_dirty=dirty, targets_file=str(args.targets), seeds=list(SEEDS),
                  actual_model_calls=0, actual_model_cost='0',
                  gate=gate(rows, targets), runs=rows)
    write_json(args.out / 'results.json', result)
    print(json.dumps({key: result['gate'][key] for key in ('rule', 'comparisons', 'shared_wins', 'passed')},
                     indent=2))


if __name__ == '__main__':
    main()
