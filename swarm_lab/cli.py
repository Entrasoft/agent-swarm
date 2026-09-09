"""Offline-first commands; campaigns cannot dispatch paid calls."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys

from .math_task import exact_optimum, validate_candidate
from .providers import REASONING_EFFORTS
from .runtime import RunConfig, Runtime
from .store import write_json


def read_events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines() if line.strip()]


def verify_replay(directory: Path) -> dict:
    events = read_events(directory)
    config = json.loads((directory/'config.json').read_text())
    summary = json.loads((directory/'summary.json').read_text())
    seen, lower = set(), 0
    for event in events:
        identity = event['event_id']
        if type(identity) is not int or identity in seen or identity != len(seen)+1:
            raise ValueError('Duplicate or nonsequential event ID')
        if any(parent not in seen for parent in event['parent_event_ids']):
            raise ValueError('Invalid provenance parent')
        seen.add(identity)
        if event['event_type'] == 'verification':
            payload = event['payload']
            valid = validate_candidate(config['m'],payload['candidate']).valid
            if valid != payload['valid']:
                raise ValueError('Verification disagrees with replay')
            if valid:
                lower = max(lower,len(payload['candidate']))
            if lower != payload['lower_bound']:
                raise ValueError('Recorded lower bound disagrees with events')
    if lower != summary['lower_bound']:
        raise ValueError('Summary lower bound disagrees with replay')
    finished = [e for e in events if e['event_type']=='run_finished']
    if finished and finished[-1]['payload'] != summary:
        raise ValueError('Summary differs from run_finished event')
    m = config['m']
    if type(m) is not int or not 1 <= m <= 24:
        raise ValueError('Replay verification supports 1 <= m <= 24')
    upper = summary.get('upper_bound')
    if type(upper) is not int or not lower <= upper <= m:
        raise ValueError('Summary upper bound is outside feasible bounds')
    evaluations = [e for e in events if e['event_type']=='evaluation']
    if finished and len(evaluations) != 1:
        raise ValueError('Completed run requires exactly one hidden evaluation')
    if evaluations:
        evaluation = evaluations[-1]['payload']
        oracle_lower, oracle_upper = evaluation.get('lower_bound'), evaluation.get('upper_bound')
        if (type(oracle_lower) is not int or type(oracle_upper) is not int
                or not 0 <= oracle_lower <= oracle_upper <= m or oracle_upper != upper):
            raise ValueError('Evaluation and summary bounds disagree')
        oracle_candidate = evaluation.get('candidate')
        if (not validate_candidate(m, oracle_candidate).valid
                or len(oracle_candidate) != oracle_lower):
            raise ValueError('Evaluation candidate does not establish its lower bound')
        if evaluation.get('status') not in {'optimal','timed_out'}:
            raise ValueError('Unknown evaluation status')
        if evaluation['status'] == 'optimal' and oracle_lower != oracle_upper:
            raise ValueError('Optimal evaluation must have equal bounds')
        # This is a mathematical consistency check, not log authentication.
        # Recompute independently of saved evaluator values at these tiny sizes.
        checked = exact_optimum(m)
        if checked.status != 'optimal':
            raise ValueError('Replay oracle timed out; upper bound could not be independently checked')
        if upper < checked.lower_bound:
            raise ValueError('Saved upper bound is below the independently checked optimum')
    elif upper != m:
        raise ValueError('A run without evaluation must retain the initial upper bound m')
    if finished or 'gap' in summary:
        if type(summary.get('gap')) is not int or summary['gap'] != upper-lower:
            raise ValueError('Summary gap disagrees with verified bounds')
    if summary.get('stopping_reason') == 'solved' and (not evaluations or lower != upper):
        raise ValueError('Solved status requires equal independently verified bounds')
    return {'verified':True,'events':len(events),'lower_bound':lower,'upper_bound':upper,
            'complete':bool(finished),'mode':config['mode']}


def campaign(args):
    conditions = [(1,'solo'),(4,'independent'),(4,'fixed'),(4,'adaptive'),
                  (10,'independent'),(10,'fixed'),(10,'adaptive')]
    sizes = [int(x) for x in args.sizes.split(',')]
    seeds = [int(x) for x in args.seeds.split(',')]
    if not sizes or not seeds or len(sizes)*len(seeds)*len(conditions)>100:
        raise ValueError('Campaign limited to 100 runs')
    if any(not 1 <= m <= 24 for m in sizes):
        raise ValueError('Campaign requires 1 <= m <= 24; profile before extending')
    if type(args.steps) is not int or not 1 <= args.steps <= 10000:
        raise ValueError('Campaign steps must be in 1..10000')
    if len(set(sizes)) != len(sizes) or len(set(seeds)) != len(seeds):
        raise ValueError('Campaign sizes and seeds must be unique')
    directory = args.out
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError('Campaign output directory must be empty')
    protocol_path = Path(__file__).resolve().parents[1]/'docs'/'experiment-protocol.md'
    protocol = protocol_path.read_text() if protocol_path.exists() else 'No external protocol supplied'
    prereg = dict(sizes=sizes,seeds=seeds,conditions=conditions,steps=args.steps,
                 comparison='matched decision ceiling; algorithmic simulated accounting',
                 protocol_sha256=hashlib.sha256(protocol.encode()).hexdigest(),protocol=protocol)
    write_json(directory/'matrix.json',prereg)  # Freeze before the first comparative run.
    results = []
    baselines = []
    for m in sizes:
        baselines.append(dict(m=m,**asdict(exact_optimum(m))))
        for seed in seeds:
            for agents,condition in conditions:
                name=f'm{m}-n{agents}-{condition}-s{seed}'
                try:
                    result=asyncio.run(Runtime(RunConfig(m=m,agents=agents,condition=condition,
                        seed=seed,steps=args.steps),directory/name).run())
                    verify_replay(directory/name)
                    result['path']=name
                    results.append(result)
                except Exception as exc:
                    results.append(dict(m=m,agents=agents,condition=condition,path=name,
                                        failure=type(exc).__name__,gap=None))
    successes=sum(r.get('gap')==0 for r in results)
    totals = dict(runs=len(results),successes=successes,failures=sum('failure' in r for r in results),
                  actual_model_calls=0,actual_model_cost='0',
                  api_cost_per_success='0' if successes else None,
                  efficiency_note='No model calls. Zero marginal API cost excludes local compute; simulated tokens cannot establish LLM efficiency.')
    grouped=[]
    for m in sizes:
        for agents,condition in conditions:
            rows=[r for r in results if r['m']==m and r['agents']==agents and r['condition']==condition]
            complete=[r for r in rows if 'failure' not in r]
            gaps=[r['gap'] for r in complete]
            grouped.append(dict(m=m,agents=agents,condition=condition,runs=len(rows),successes=sum(g==0 for g in gaps),
                gaps=gaps,median_gap=statistics.median(gaps) if gaps else None,
                median_worker_seconds=statistics.median(r['worker_seconds'] for r in complete) if complete else None))
    report=dict(matrix=prereg,totals=totals,groups=grouped,deterministic_baselines=baselines,results=results)
    write_json(directory/'campaign.json',report)
    print(json.dumps({'out':str(directory),**totals},indent=2))


def main(argv=None):
    parser=argparse.ArgumentParser(prog='swarm-lab',description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run',help='Run a bounded experiment (algorithmic by default)')
    run.add_argument('--m',type=int,default=12)
    run.add_argument('--agents',type=int,default=4)
    run.add_argument('--condition',choices=['solo','independent','fixed','adaptive'],default='independent')
    run.add_argument('--mode',choices=['algorithmic','scripted','live'],default='algorithmic')
    run.add_argument('--steps',type=int,default=48)
    run.add_argument('--concurrency',type=int,default=4)
    run.add_argument('--seed',type=int,default=0)
    run.add_argument('--allocation',choices=['round_robin','exploratory'],default='round_robin')
    run.add_argument('--token-limit',type=int)
    run.add_argument('--cost-limit')
    run.add_argument('--model')
    run.add_argument('--reasoning-effort', choices=REASONING_EFFORTS,
                     help='Reasoning setting for live requests (live default: medium)')
    run.add_argument('--price-file',type=Path)
    run.add_argument('--max-output',type=int,default=512)
    run.add_argument('--max-retries',type=int,default=1)
    run.add_argument('--timeout',type=float,default=30,
                     help='Provider request timeout in seconds, at most 120 (default: 30)')
    run.add_argument('--oracle-timeout',type=float,default=5)
    run.add_argument('--allow-live',action='store_true')
    run.add_argument('--out',type=Path,required=True)
    replay=sub.add_parser('replay',help='Inspect recorded events without model calls')
    replay.add_argument('directory',type=Path)
    replay.add_argument('--verify',action='store_true')
    display=sub.add_parser('view',help='Open the local Tk desktop event viewer')
    display.add_argument('directory',type=Path)
    bench=sub.add_parser('benchmark',help='Bounded offline-only predefined campaign')
    bench.add_argument('--sizes',default='10,12,18,24')
    bench.add_argument('--seeds',default='0,1,2')
    bench.add_argument('--steps',type=int,default=48)
    bench.add_argument('--out',type=Path,required=True)
    oracle=sub.add_parser('oracle',help='Experimenter-only deterministic baseline')
    oracle.add_argument('--m',type=int,default=12)
    oracle.add_argument('--timeout',type=float,default=5)
    args=parser.parse_args(argv)
    try:
        if args.command=='run':
            if args.mode=='live' and (not args.model or args.token_limit is None or args.cost_limit is None or args.price_file is None):
                raise ValueError('Live mode requires --model, --token-limit, --cost-limit, --price-file and --allow-live.')
            config=RunConfig(m=args.m,agents=args.agents,condition=args.condition,mode=args.mode,steps=args.steps,
                concurrency=args.concurrency,seed=args.seed,allocation=args.allocation,
                token_limit=args.token_limit if args.token_limit is not None else 100000,
                cost_limit=args.cost_limit if args.cost_limit is not None else '1',
                model=args.model or 'fixture-v1',max_output=args.max_output,max_retries=args.max_retries,
                reasoning_effort=args.reasoning_effort,timeout_seconds=args.timeout,
                oracle_timeout=args.oracle_timeout,allow_live=args.allow_live)
            if args.price_file:
                config.price=json.loads(args.price_file.read_text())
            result=asyncio.run(Runtime(config,args.out).run())
            print(json.dumps({k:result[k] for k in ('run_id','mode','lower_bound','upper_bound','gap','stopping_reason','actual_model_calls','actual_model_cost')},indent=2))
            print('Artifacts:',args.out)
        elif args.command=='replay':
            result=verify_replay(args.directory) if args.verify else json.loads((args.directory/'summary.json').read_text())
            print(json.dumps(result,indent=2))
        elif args.command=='view':
            from .display import launch
            launch(args.directory)
        elif args.command=='benchmark':
            campaign(args)
        elif args.command=='oracle':
            if not 1<=args.m<=24:
                raise ValueError('CLI oracle supports 1 <= m <= 24; profile before extending.')
            print(json.dumps(asdict(exact_optimum(args.m,args.timeout)),indent=2))
    except (ValueError,OSError,RuntimeError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__=='__main__':
    main()
