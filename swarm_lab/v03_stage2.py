"""Coordination v0.3, Stage 2: offline algorithmic 2x2 plus solo.

Runs the five arms (I-H, I-D, S-H, S-D, solo) with the four seeded search
strategies on every frozen target for seeds 0-29, at the same simulated token
allowance per run, and replays every run. No model is called.

Gate, fixed before the run: for each seed, S-D wins the seed when it beats I-H,
ranked by (d, fewer minimum-weight codewords), strictly on at least 4 of the 6
targets. The gate passes when S-D wins at least 20 of the 30 seeds. The
mechanism contrast (S-D - I-D) - (S-H - I-H) is reported descriptively.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess

from .archive_runtime import ArchiveConfig, ArchiveRuntime, verify_replay
from .store import write_json

SEEDS = tuple(range(30))
ARM_AGENTS = {'I-H': 4, 'I-D': 4, 'S-H': 4, 'S-D': 4, 'solo': 1}
TOKEN_LIMIT = 40_000
TARGETS_TO_WIN_SEED = 4
SEEDS_TO_PASS = 20


def target_key(target: dict) -> tuple:
    return (target['q'], target['n'], target['k'])


def run_one(job: tuple) -> dict:
    target, arm, seed, directory = job
    config = ArchiveConfig(target={key: target[key] for key in ('q', 'n', 'k', 'lower', 'upper')},
                           arm=arm, policy='strategies', agents=ARM_AGENTS[arm], seed=seed,
                           token_limit=TOKEN_LIMIT)
    summary = ArchiveRuntime(config, Path(directory)).run()
    replay = verify_replay(Path(directory))
    best = summary['best']
    return dict(target=config.target, arm=arm, seed=seed, path=Path(directory).name,
                d=best['d'] if best else None,
                min_weight_count=best['min_weight_count'] if best else None,
                rounds=summary['rounds'], decisions=sum(summary['decisions'].values()),
                valid=summary['valid'], invalid=summary['invalid'],
                cross_agent_extensions=summary['cross_agent_extensions'],
                best_lineage_crosses_agents=summary['best_lineage_crosses_agents'],
                beats_record=summary['beats_record'], matches_record=bool(best and best['d'] == config.target['lower']),
                simulated_tokens=summary['simulated_tokens'], replay_verified=replay['verified'])


def rank(row: dict) -> tuple:
    return (-1, 0) if row['d'] is None else (row['d'], -row['min_weight_count'])


def analyse(rows: list[dict], targets: list[dict]) -> dict:
    index = {(target_key(r['target']), r['arm'], r['seed']): r for r in rows}
    keys = [target_key(t) for t in targets]
    seeds = []
    for seed in SEEDS:
        wins = [key for key in keys if rank(index[(key, 'S-D', seed)]) > rank(index[(key, 'I-H', seed)])]
        seeds.append(dict(seed=seed, targets_won=len(wins), won=len(wins) >= TARGETS_TO_WIN_SEED))
    seed_wins = sum(s['won'] for s in seeds)
    per_target = []
    for key in keys:
        median = {arm: statistics.median(index[(key, arm, s)]['d'] for s in SEEDS) for arm in ARM_AGENTS}
        pairs = [(rank(index[(key, 'S-D', s)]), rank(index[(key, 'I-H', s)])) for s in SEEDS]
        per_target.append(dict(
            target=list(key), lower=next(t['lower'] for t in targets if target_key(t) == key),
            median_d=median,
            sd_vs_ih=dict(wins=sum(a > b for a, b in pairs), ties=sum(a == b for a, b in pairs),
                          losses=sum(a < b for a, b in pairs)),
            mechanism_contrast_median_d=(median['S-D'] - median['I-D']) - (median['S-H'] - median['I-H']),
            matches_record={arm: sum(index[(key, arm, s)]['matches_record'] for s in SEEDS) for arm in ARM_AGENTS},
            beats_record={arm: sum(index[(key, arm, s)]['beats_record'] for s in SEEDS) for arm in ARM_AGENTS},
            median_cross_agent_extensions={arm: statistics.median(index[(key, arm, s)]['cross_agent_extensions']
                                                                 for s in SEEDS) for arm in ('S-H', 'S-D')}))
    return dict(rule=(f'S-D beats I-H strictly on at least {TARGETS_TO_WIN_SEED} of {len(keys)} targets '
                      f'in at least {SEEDS_TO_PASS} of {len(SEEDS)} seeds'),
                seeds_won=seed_wins, seeds=len(SEEDS),
                passed=seed_wins >= SEEDS_TO_PASS and all(r['replay_verified'] for r in rows),
                seed_detail=seeds, per_target=per_target,
                any_record_beaten=any(r['beats_record'] for r in rows))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='swarm_lab.v03_stage2', description=__doc__)
    parser.add_argument('--targets', type=Path, default=Path('configs/v03/targets.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        parser.exit(2, 'Error: output directory must be empty.\n')
    targets = json.loads(args.targets.read_text())['targets']
    jobs = [(target, arm, seed, args.out / f"q{target['q']}-n{target['n']}-k{target['k']}-{arm}-s{seed}")
            for seed in SEEDS for target in targets for arm in ARM_AGENTS]
    started = datetime.now(timezone.utc).isoformat()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs, chunksize=1))
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--', 'swarm_lab'], text=True))
    except (subprocess.SubprocessError, OSError):
        revision, dirty = 'unavailable', None
    result = dict(stage='v0.3 Stage 2 algorithmic 2x2', started=started,
                  finished=datetime.now(timezone.utc).isoformat(), code_revision=revision,
                  source_dirty=dirty, targets_file=str(args.targets), seeds=list(SEEDS),
                  token_limit=TOKEN_LIMIT, actual_model_calls=0, actual_model_cost='0',
                  gate=analyse(rows, targets), runs=rows)
    write_json(args.out / 'results.json', result)
    gate = result['gate']
    print(json.dumps(dict(rule=gate['rule'], seeds_won=gate['seeds_won'], passed=gate['passed'],
                          any_record_beaten=gate['any_record_beaten']), indent=2))


if __name__ == '__main__':
    main()
