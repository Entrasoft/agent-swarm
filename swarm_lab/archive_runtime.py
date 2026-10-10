"""Coordination v0.3 runtime: round-snapshot decisions over a verified-code archive.

Each round, every agent receives an observation built from the archive as it
stood when the round began, and returns one action naming a base archive entry
and a full set of quasi-cyclic polynomials. Actions are verified after the round
and only then enter the archives. Shared arms observe the team archive; private
arms observe only their own verified codes, in the same shape. The runtime, not
the agent, records which archive entry each candidate was built from.

This module runs offline policies only. Live batch transport belongs to Stage 3
and is not implemented here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import random
import uuid

from .codes import CodeResult, Target, evaluate
from .ledger import Ledger, _cost
from .runtime import OFFLINE_PRICE
from .store import EventStore, write_json

ARMS = {
    # name: (team-wide archive, strategy assignment)
    'pc-independent': (False, 'slots'),
    'pc-shared': (True, 'slots'),
}
POLICIES = ('positive_control',)


@dataclass
class ArchiveConfig:
    target: dict
    arm: str
    policy: str = 'positive_control'
    agents: int = 4
    seed: int = 0
    token_limit: int = 40_000
    cost_limit: str = '1'
    max_output: int = 512
    archive_size: int = 8
    max_rounds: int = 200
    price: dict = field(default_factory=lambda: dict(OFFLINE_PRICE))

    def validate(self) -> Target:
        if self.arm not in ARMS:
            raise ValueError(f'unknown arm {self.arm!r}')
        if self.policy not in POLICIES:
            raise ValueError(f'unknown policy {self.policy!r}')
        if not 1 <= self.agents <= 8 or not 1 <= self.archive_size <= 32:
            raise ValueError('agents must be in 1..8 and archive_size in 1..32')
        if self.token_limit <= 0 or not 1 <= self.max_rounds <= 10_000:
            raise ValueError('token_limit must be positive and max_rounds in 1..10000')
        if self.price != OFFLINE_PRICE:
            raise ValueError('offline v0.3 runs use the simulated fixture price')
        keys = {'q', 'n', 'k', 'lower', 'upper'}
        if not keys <= self.target.keys():
            raise ValueError('target needs q, n, k, lower and upper')
        return Target(**{key: self.target[key] for key in keys})


def rank_key(entry: dict) -> tuple:
    """Archive order: larger d, then fewer minimum-weight codewords, then earlier."""
    return (-entry['d'], entry['min_weight_count'], entry['event_id'])


class Archive:
    """Top verified codes, distinct by polynomials. Shared by runtime and replay."""

    def __init__(self, size: int):
        self.size, self.entries = size, []

    def add(self, entry: dict) -> None:
        if any(existing['polynomials'] == entry['polynomials'] for existing in self.entries):
            return
        self.entries = sorted(self.entries + [entry], key=rank_key)[:self.size]

    def snapshot(self) -> list[dict]:
        return [dict(entry) for entry in self.entries]


def slot_of(agent_index: int, target: Target) -> int:
    return agent_index % target.blocks


def positive_control_policy(observation: dict, rng: random.Random) -> dict:
    """Set only this agent's slot to fresh random coefficients on the best visible base."""
    q, k, blocks = (observation['target'][key] for key in ('q', 'k', 'blocks'))
    slot = observation['slot']
    base = observation['archive'][0] if observation['archive'] else None
    polynomials = [list(poly) for poly in base['polynomials']] if base else [[0] * k for _ in range(blocks)]
    polynomials[slot] = [rng.randrange(q) for _ in range(k)]
    if not any(polynomials[slot]):
        polynomials[slot][0] = 1
    return dict(base=base['event_id'] if base else None, polynomials=polynomials,
                used_event_ids=[base['event_id']] if base else [])


POLICY_FUNCTIONS = {'positive_control': positive_control_policy}


def check_action(action, observation: dict, target: Target) -> tuple[str | None, dict | None]:
    """Structural checks before verification. Returns (reason, base entry)."""
    if not isinstance(action, dict) or set(action) != {'base', 'polynomials', 'used_event_ids'}:
        return 'action must have exactly base, polynomials and used_event_ids', None
    visible = {entry['event_id']: entry for entry in observation['archive']}
    base_id = action['base']
    if base_id is not None and (type(base_id) is not int or base_id not in visible):
        return 'base is not an entry in this observation', None
    used = action['used_event_ids']
    if not isinstance(used, list) or any(type(e) is not int or e not in visible for e in used):
        return 'used_event_ids must name entries in this observation', None
    base = visible.get(base_id)
    if observation.get('slot') is not None and isinstance(action['polynomials'], list):
        reference = base['polynomials'] if base else [[0] * target.k for _ in range(target.blocks)]
        if (len(action['polynomials']) != target.blocks
                or any(action['polynomials'][b] != reference[b]
                       for b in range(target.blocks) if b != observation['slot'])):
            return 'positive control may change only its assigned slot', base
    return None, base


def changed_coefficients(polynomials, base: dict | None) -> int | None:
    if base is None or not isinstance(polynomials, list):
        return None
    return sum(a != b for new, old in zip(polynomials, base['polynomials'])
               for a, b in zip(new, old))


class ArchiveRuntime:
    def __init__(self, config: ArchiveConfig, directory: Path, *, run_id: str | None = None):
        self.target = config.validate()
        self.config, self.directory = config, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.iterdir()):
            raise ValueError('Output directory must be empty.')
        self.run_id = run_id or str(uuid.uuid4())
        self.shared, self.strategy = ARMS[config.arm]
        self.agent_ids = [f'agent-{i}' for i in range(config.agents)]
        self.rngs = {agent: random.Random(config.seed * 1009 + i) for i, agent in enumerate(self.agent_ids)}
        self.team = Archive(config.archive_size)
        self.private = {agent: Archive(config.archive_size) for agent in self.agent_ids}
        self.ledger = Ledger(self.directory / 'usage.sqlite3')
        self.ledger.create_run(self.run_id, config.token_limit, config.cost_limit, config.price, simulated=True)
        self.store = EventStore(self.directory, self.run_id)
        self.best: dict | None = None
        self.lineage: dict[int, dict] = {}

    def observation(self, agent_index: int, round_number: int) -> dict:
        agent = self.agent_ids[agent_index]
        archive = self.team if self.shared else self.private[agent]
        target = self.target
        return dict(target=dict(q=target.q, n=target.n, k=target.k, blocks=target.blocks,
                                punctured=target.punctured),
                    agent_id=agent, round=round_number,
                    slot=slot_of(agent_index, target) if self.strategy == 'slots' else None,
                    archive=archive.snapshot())

    def round_fits(self, estimates: list[int]) -> bool:
        summary = self.ledger.summary(self.run_id)
        tokens = sum(estimate + self.config.max_output for estimate in estimates)
        cost = sum(_cost(self.config.price, estimate, self.config.max_output, reservation=True)
                   for estimate in estimates)
        return tokens <= summary['remaining_tokens'] and cost <= Decimal(summary['remaining_cost'])

    def run(self) -> dict:
        config, target = self.config, self.target
        write_json(self.directory / 'config.json', dict(asdict(config), run_id=self.run_id,
                   target_blocks=target.blocks, target_punctured=target.punctured,
                   scheduling='round snapshot: all agents in a round observe the archive as of round start'))
        self.store.emit('run_started', payload=dict(arm=config.arm, target=config.target, seed=config.seed))
        stopping, round_number, decisions = 'round_limit', 0, Counter()
        policy = POLICY_FUNCTIONS[config.policy]
        try:
            while round_number < config.max_rounds:
                observations = [self.observation(i, round_number) for i in range(config.agents)]
                estimates = [max(1, len(json.dumps(obs).encode()) // 4) for obs in observations]
                if not self.round_fits(estimates):
                    stopping = 'budget_exhausted'
                    break
                started = self.store.emit('round_started', payload=dict(
                    round=round_number, team_archive=[e['event_id'] for e in self.team.entries]))
                pending = []
                for index, (obs, estimate) in enumerate(zip(observations, estimates)):
                    agent, task = self.agent_ids[index], f'r{round_number}-{self.agent_ids[index]}'
                    attempt = f'{task}/attempt-0'
                    if not self.ledger.reserve(self.run_id, attempt, agent, task, task, 0, 'research',
                                               estimate, config.max_output, config.price['model']):
                        raise RuntimeError('round reservation failed after the round fit check')
                    seen = self.store.emit('observation', actor=agent, task_id=task, payload=obs,
                                           parents=[started['event_id']])
                    action = policy(obs, self.rngs[agent])
                    usage = dict(input_tokens=estimate,
                                 output_tokens=min(config.max_output, max(1, len(json.dumps(action)) // 4)),
                                 input_tokens_details=dict(cached_tokens=0),
                                 output_tokens_details=dict(reasoning_tokens=0))
                    self.ledger.settle(attempt, 'completed', usage)
                    ledger = self.ledger.summary(self.run_id)
                    self.store.emit('usage', actor=agent, task_id=task, payload=dict(
                        attempt_id=attempt, input_tokens=usage['input_tokens'],
                        output_tokens=usage['output_tokens'], simulated=True,
                        committed_tokens=ledger['committed_tokens'], remaining_tokens=ledger['remaining_tokens'],
                        committed_cost=ledger['committed_cost'], remaining_cost=ledger['remaining_cost']))
                    decisions[agent] += 1
                    pending.append((index, agent, task, obs, seen, action))
                verified = []
                for index, agent, task, obs, seen, action in pending:
                    reason, base = check_action(action, obs, target)
                    parents = [seen['event_id']] + ([base['event_id']] if base else [])
                    submitted = self.store.emit('candidate_submitted', actor=agent, task_id=task,
                                                payload=action, parents=parents)
                    result = CodeResult(False, reason) if reason else evaluate(target, action['polynomials'])
                    base_agent = base['agent'] if base else None
                    payload = dict(result.to_dict(), base=base['event_id'] if base else None,
                                   base_agent=base_agent,
                                   cross_agent=base_agent is not None and base_agent != agent,
                                   changed_coefficients=changed_coefficients(action.get('polynomials')
                                                                             if isinstance(action, dict) else None, base))
                    event = self.store.emit('verification', actor='verifier', recipient=agent, task_id=task,
                                            parents=[submitted['event_id']], payload=payload,
                                            verification_status='valid' if result.valid else 'invalid')
                    if result.valid:
                        entry = dict(event_id=event['event_id'], agent=agent, polynomials=action['polynomials'],
                                     d=result.d, min_weight_count=result.min_weight_count)
                        self.lineage[event['event_id']] = dict(agent=agent, base=payload['base'])
                        verified.append(entry)
                for entry in verified:
                    self.team.add(entry)
                    self.private[entry['agent']].add(entry)
                    if self.best is None or rank_key(entry) < rank_key(self.best):
                        self.best = entry
                self.store.emit('archive_updated', payload=dict(
                    round=round_number, team=[e['event_id'] for e in self.team.entries],
                    private={a: [e['event_id'] for e in arc.entries] for a, arc in self.private.items()}))
                round_number += 1
            summary = self.summary(stopping, round_number, decisions)
            self.store.emit('run_finished', payload=summary)
            write_json(self.directory / 'summary.json', summary)
            self.ledger.export(self.run_id, self.directory)
            return summary
        finally:
            self.store.close()
            self.ledger.close()

    def best_lineage_crosses_agents(self) -> bool:
        node = self.best['event_id'] if self.best else None
        while node is not None and node in self.lineage:
            parent = self.lineage[node]['base']
            if parent is not None and self.lineage.get(parent, {}).get('agent') != self.lineage[node]['agent']:
                return True
            node = parent
        return False

    def summary(self, stopping: str, rounds: int, decisions: Counter) -> dict:
        events = self.store.events()
        checks = [e['payload'] for e in events if e['event_type'] == 'verification']
        usage = self.ledger.summary(self.run_id)
        best = self.best
        return dict(
            run_id=self.run_id, arm=self.config.arm, policy=self.config.policy, seed=self.config.seed,
            target=self.config.target, rounds=rounds, stopping_reason=stopping,
            decisions=dict(decisions), valid=sum(c['valid'] for c in checks),
            invalid=sum(not c['valid'] for c in checks),
            invalid_reasons=dict(Counter(c['reason'] for c in checks if not c['valid'])),
            best=dict(event_id=best['event_id'], agent=best['agent'], d=best['d'],
                      min_weight_count=best['min_weight_count'], polynomials=best['polynomials']) if best else None,
            beats_record=bool(best and best['d'] > self.config.target['lower']),
            cross_agent_extensions=sum(c['valid'] and c['cross_agent'] for c in checks),
            best_lineage_crosses_agents=self.best_lineage_crosses_agents(),
            simulated_tokens=usage['total_tokens'], simulated_cost=usage['known_cost'],
            actual_model_calls=0, actual_model_cost='0')


def read_events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (Path(directory) / 'events.jsonl').read_text().splitlines() if line.strip()]


def verify_replay(directory: Path) -> dict:
    """Recompute every verification and every observed archive from the event log."""
    directory = Path(directory)
    config = json.loads((directory / 'config.json').read_text())
    summary = json.loads((directory / 'summary.json').read_text())
    events = read_events(directory)
    target = Target(**{key: config['target'][key] for key in ('q', 'n', 'k', 'lower', 'upper')})
    shared, strategy = ARMS[config['arm']]
    agents = [f'agent-{i}' for i in range(config['agents'])]
    team = Archive(config['archive_size'])
    private = {agent: Archive(config['archive_size']) for agent in agents}
    by_id, submissions, observations, round_valid = {}, {}, {}, []
    best = None
    for expected_id, event in enumerate(events, start=1):
        if event['event_id'] != expected_id:
            raise ValueError('event IDs are not sequential')
        if any(parent not in by_id for parent in event['parent_event_ids']):
            raise ValueError('event refers to a later or missing parent')
        by_id[event['event_id']] = event
        kind = event['event_type']
        if kind == 'observation':
            agent = event['actor']
            archive = team if shared else private[agent]
            if event['payload']['archive'] != archive.snapshot():
                raise ValueError(f'observation {event["event_id"]} does not match the recomputed archive')
            if not shared and any(e['agent'] != agent for e in event['payload']['archive']):
                raise ValueError('a private archive contains another agent\'s code')
            expected_slot = slot_of(agents.index(agent), target) if strategy == 'slots' else None
            if event['payload']['slot'] != expected_slot:
                raise ValueError('observation slot does not match the arm')
            observations[event['task_id']] = event['payload']
        elif kind == 'candidate_submitted':
            submissions[event['event_id']] = event
        elif kind == 'verification':
            submitted = submissions[event['parent_event_ids'][0]]
            observation = observations[submitted['task_id']]
            reason, base = check_action(submitted['payload'], observation, target)
            result = CodeResult(False, reason) if reason else evaluate(target, submitted['payload']['polynomials'])
            recorded = event['payload']
            if (recorded['valid'], recorded['reason'], recorded['d'], recorded['min_weight_count']) != (
                    result.valid, result.reason, result.d, result.min_weight_count):
                raise ValueError(f'verification {event["event_id"]} disagrees with recomputation')
            if recorded['base'] != (base['event_id'] if base else None):
                raise ValueError('recorded base disagrees with the submission')
            if result.valid:
                round_valid.append(dict(event_id=event['event_id'], agent=submitted['actor'],
                                        polynomials=submitted['payload']['polynomials'],
                                        d=result.d, min_weight_count=result.min_weight_count))
        elif kind == 'archive_updated':
            for entry in round_valid:
                team.add(entry)
                private[entry['agent']].add(entry)
                if best is None or rank_key(entry) < rank_key(best):
                    best = entry
            round_valid = []
            if event['payload']['team'] != [e['event_id'] for e in team.entries]:
                raise ValueError('recorded team archive disagrees with recomputation')
    recorded_best = summary['best']
    if (best is None) != (recorded_best is None) or (
            best and (best['event_id'], best['d'], best['min_weight_count']) !=
            (recorded_best['event_id'], recorded_best['d'], recorded_best['min_weight_count'])):
        raise ValueError('summary best code disagrees with replay')
    return dict(verified=True, events=len(events), best_d=best['d'] if best else None)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='swarm_lab.archive_runtime', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    replay = sub.add_parser('replay', help='Recompute and check a saved run')
    replay.add_argument('directory', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(verify_replay(args.directory), indent=2))


if __name__ == '__main__':
    main()
