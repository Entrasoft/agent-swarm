"""Bounded asynchronous orchestration. Workers never receive evaluation state."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
import json
import hashlib
import math
from pathlib import Path
import random
import subprocess
import time
import uuid
from typing import Literal

from .ledger import Ledger
from .math_task import exact_optimum, validate_candidate
from .policies import decide, exploratory_priority
from .providers import OpenAIProvider, ProviderFailure, REASONING_EFFORTS
from .store import EventStore, write_json

PROTOCOL = {'request_help','propose_claim','submit_candidate','challenge_claim','share_artifact','report_result'}
OFFLINE_PRICE = dict(provider='offline-fixture', model='fixture-v1', service_tier='default', currency='USD',
    version='offline-v1', effective_date='2026-09-09', retrieved_date='2026-09-09',
    source_url='offline fixture; not market prices', simulated=True,
    input_per_million='1', cached_input_per_million='0.25', output_per_million='2')


@dataclass
class RunConfig:
    m: int = 12
    agents: int = 4
    condition: Literal['solo','independent','fixed','adaptive'] = 'independent'
    mode: Literal['algorithmic','scripted','live'] = 'algorithmic'
    steps: int = 48  # Total decision calls across the entire team.
    concurrency: int = 4
    seed: int = 0
    allocation: str = 'round_robin'
    token_limit: int = 100_000
    cost_limit: str = '1.00'
    max_output: int = 512
    max_retries: int = 1
    mailbox_limit: int = 16
    message_bytes: int = 4096
    context_bytes: int = 16384
    timeout_seconds: float = 30.0
    oracle_timeout: float = 5.0
    model: str = 'fixture-v1'
    reasoning_effort: str | None = None
    price: dict = field(default_factory=lambda: dict(OFFLINE_PRICE))
    allow_live: bool = False
    # Withhold one message including its provenance descendants for paired experiments.
    withhold_message: int | None = None
    decision_protocol: Literal['legacy', 'feedback-v0.2'] = 'legacy'
    memory_mode: Literal['private_best_only', 'history_feedback'] = 'private_best_only'
    history_limit: int = 8

    def validate(self):
        if self.decision_protocol not in {'legacy', 'feedback-v0.2'}:
            raise ValueError('Unknown decision protocol.')
        if self.memory_mode not in {'private_best_only', 'history_feedback'}:
            raise ValueError('Unknown memory mode.')
        if type(self.history_limit) is not int or not 1 <= self.history_limit <= 32:
            raise ValueError('History limit must be an integer in 1..32.')
        if self.memory_mode == 'history_feedback' and self.decision_protocol != 'feedback-v0.2':
            raise ValueError('Attempt feedback requires the feedback-v0.2 decision protocol.')
        if self.decision_protocol == 'feedback-v0.2' and (
                self.condition != 'solo' or self.agents != 1 or self.concurrency != 1
                or self.max_retries != 0 or self.allocation != 'round_robin'
                or self.withhold_message is not None):
            raise ValueError('Feedback v0.2 requires solo, serial round robin, zero retries and no message intervention.')
        if not 1 <= self.m <= 24 or not 1 <= self.agents <= 32:
            raise ValueError('Require 1 <= m <= 24 and 1 <= agents <= 32.')
        if self.condition not in {'solo','independent','fixed','adaptive'} or self.mode not in {'algorithmic','scripted','live'}:
            raise ValueError('Unknown condition or mode.')
        if (self.condition == 'solo') != (self.agents == 1):
            raise ValueError('Solo requires one agent; team conditions require at least two.')
        if self.allocation not in {'round_robin','exploratory'}:
            raise ValueError('Unknown allocator.')
        if self.condition == 'independent' and self.allocation != 'round_robin':
            raise ValueError('Independent uses outcome-blind round robin to avoid allocation leaks.')
        if not 1 <= self.steps <= 10000 or not 1 <= self.concurrency <= 32:
            raise ValueError('Invalid bounded steps or concurrency.')
        if not 0 <= self.max_retries <= 3 or not 1 <= self.max_output <= 32768:
            raise ValueError('Invalid retry or output limit.')
        try:
            cost_ceiling = Decimal(self.cost_limit)
        except (InvalidOperation, TypeError):
            raise ValueError('Currency ceiling must be a decimal number.') from None
        if self.token_limit < 0 or not cost_ceiling.is_finite() or cost_ceiling < 0:
            raise ValueError('Budget must be finite and nonnegative.')
        if not 1 <= self.mailbox_limit <= 128 or not 64 <= self.message_bytes <= 16384 or not 512 <= self.context_bytes <= 65536:
            raise ValueError('Invalid mailbox, message or context bounds.')
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 120:
            raise ValueError('Provider timeout must be in (0,120].')
        if not math.isfinite(self.oracle_timeout) or not 0 <= self.oracle_timeout <= 60:
            raise ValueError('Oracle timeout must be in [0,60].')
        if self.reasoning_effort is not None and self.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError('Unsupported reasoning effort.')
        if self.mode == 'live':
            if not self.allow_live:
                raise ValueError('Live mode requires explicit --allow-live and a budget.')
            required = {'provider','model','service_tier','currency','version','effective_date','retrieved_date','source_url',
                        'input_per_million','cached_input_per_million','output_per_million'}
            if self.model == 'gpt-5.6-terra' or self.model.startswith('gpt-5.6-terra-'):
                required.add('cache_write_per_million')
            if self.price.keys() - (required | {'simulated', 'verified_on', 'rate_units', 'cache_write_per_million'}):
                raise ValueError('Price snapshots may contain only documented price metadata, never credentials.')
            if not required <= self.price.keys() or self.price.get('simulated', False):
                raise ValueError('Live mode requires a complete, verified non-simulated price snapshot.')
            if self.price['provider'] != 'openai' or self.price['model'] != self.model or self.price['service_tier'] != 'default':
                raise ValueError('Live prices must match OpenAI, exact requested model and default service tier.')
            if self.price['currency'] != 'USD' or not self.price['source_url'].startswith(('https://developers.openai.com/','https://openai.com/','https://platform.openai.com/')):
                raise ValueError('Require USD and an official price source URL.')
            if self.price.get('verified_on') != time.strftime('%Y-%m-%d'):
                raise ValueError('Verify the official model prices today and set verified_on in the snapshot.')
            if self.token_limit <= 0 or Decimal(self.cost_limit) <= 0:
                raise ValueError('Live ceilings must be positive.')
            # Persist the effective setting so reproducible live runs never depend on a model default.
            if self.reasoning_effort is None:
                self.reasoning_effort = 'medium'
        elif self.model != 'fixture-v1' or self.price != OFFLINE_PRICE:
            raise ValueError('Offline modes use clearly simulated fixture-v1 prices.')


@dataclass
class AgentState:
    agent_id: str
    role: str
    rng: random.Random
    private_best: list = field(default_factory=list)
    mailbox: list = field(default_factory=list)
    last_event: int | None = None
    calls: int = 0
    attempt_history: list = field(default_factory=list)


class Runtime:
    def __init__(self, config: RunConfig, directory: Path, provider=None, *,
                 ledger_path: Path | None = None, campaign_id: str | None = None,
                 stop_on_failure: bool = False, run_id: str | None = None):
        config.validate()
        if (ledger_path is None) != (campaign_id is None):
            raise ValueError('Shared ledger path and campaign ID must be supplied together.')
        self.campaign_id = campaign_id
        self.stop_on_failure = stop_on_failure or config.decision_protocol == 'feedback-v0.2'
        self.config, self.directory = config, Path(directory)
        # Authenticate before creating files; never serialize provider configuration or environment.
        self.provider = provider or (OpenAIProvider(config.model, config.max_output, config.timeout_seconds,
                                                   reasoning_effort=config.reasoning_effort)
                                     if config.mode == 'live' else None)
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.iterdir()):
            raise ValueError('Output directory must be empty; use replay for an existing run.')
        if run_id is not None and (not isinstance(run_id, str) or not run_id):
            raise ValueError('A supplied run ID must be a nonempty string.')
        self.run_id = run_id if run_id is not None else str(uuid.uuid4())
        self.ledger = Ledger(ledger_path or self.directory / 'usage.sqlite3')
        try:
            self.ledger.create_run(self.run_id, config.token_limit, config.cost_limit, config.price,
                                   simulated=config.mode != 'live', campaign_id=campaign_id)
            if self.ledger.summary(self.run_id)['attempts']:
                raise ValueError('This run already has attempts; refusing redispatch.')
        except BaseException:
            self.ledger.close()
            raise
        self.store = EventStore(self.directory, self.run_id)
        self.team = [AgentState(f'agent-{i}', 'coordinator' if i == 0 and config.condition in {'fixed','adaptive'} else 'searcher',
                               random.Random(config.seed * 1009 + i)) for i in range(config.agents)]
        self.by_id = {a.agent_id:a for a in self.team}
        self.best, self.seen_candidates, self.delivered_ids = [], set(), set()
        self.stats = {a.agent_id: {'pulls':0,'verified_progress':0,'estimated_cost':0} for a in self.team}
        self.lower_bound, self.upper_bound = 0, config.m
        self.invalid, self.duplicates, self.reuse, self.messages, self.message_size = 0, 0, 0, 0, 0
        self.verification_seconds = 0.0
        self.stop = None
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.workers_completed = 0
        self.withheld_information = set()
        self.message_index = 0

    def observation(self, agent: AgentState, task_id: str) -> dict:
        # Deliberately no global incumbent, oracle, aggregate artifact store, or other agent state.
        mailbox = list(agent.mailbox) if self.config.condition in {'fixed','adaptive'} else []
        result = dict(m=self.config.m, agent_id=agent.agent_id, role=agent.role,
            round=agent.calls, private_best=list(agent.private_best), mailbox=mailbox,
            peers=[a.agent_id for a in self.team if a is not agent],
            condition=self.config.condition, task_id=task_id)
        if self.config.memory_mode == 'history_feedback':
            # Copy public verifier facts only; never copy a verification payload,
            # which also contains evaluator bounds and aggregate state.
            result['attempt_history'] = json.loads(json.dumps(agent.attempt_history))
            while len(json.dumps(result).encode()) > self.config.context_bytes and result['attempt_history']:
                result['attempt_history'].pop(0)
        while len(json.dumps(result).encode()) > self.config.context_bytes and result['mailbox']:
            result['mailbox'].pop(0)
        if len(json.dumps(result).encode()) > self.config.context_bytes:
            raise ValueError('Context bound too small for base observation.')
        return result

    def send(self, agent: AgentState, message: dict, parents: list[int], task_id: str):
        if not isinstance(message, dict):
            self.store.emit('message_rejected', actor=agent.agent_id, payload={'reason':'malformed message'}, parents=parents)
            return
        recipient = message.get('recipient')
        if not isinstance(recipient, str):
            recipient = None
        reason = None
        if self.config.condition in {'solo','independent'}:
            reason = 'condition forbids sharing'
        elif not isinstance(message.get('type'), str) or message.get('type') not in PROTOCOL or recipient not in self.by_id or recipient == agent.agent_id:
            reason = 'invalid protocol or recipient'
        elif self.config.condition == 'fixed' and agent.role != 'coordinator' and recipient != 'agent-0':
            reason = 'fixed routing requires coordinator'
        elif len(json.dumps(message).encode()) > self.config.message_bytes:
            reason = 'message size limit'
        elif len(self.by_id[recipient].mailbox) >= self.config.mailbox_limit:
            reason = 'mailbox full'
        if reason:
            self.store.emit('message_rejected', actor=agent.agent_id, recipient=recipient,
                            payload={'reason':reason}, parents=parents, task_id=task_id)
            return
        sent = self.store.emit('message_sent', actor=agent.agent_id, recipient=recipient,
                               payload=message, parents=parents, task_id=task_id)
        self.message_index += 1
        self.messages += 1
        self.message_size += len(json.dumps(message).encode())
        fingerprint = json.dumps(message.get('content'), sort_keys=True)
        if self.message_index == self.config.withhold_message or fingerprint in self.withheld_information:
            self.withheld_information.add(fingerprint)
            self.store.emit('message_withheld', actor='intervention', recipient=recipient,
                            payload={'message_index':self.message_index}, parents=[sent['event_id']])
            return
        self.deliver(sent)

    def deliver(self, sent: dict):
        if sent['event_id'] in self.delivered_ids:
            return False
        recipient = self.by_id[sent['recipient']]
        if len(recipient.mailbox) >= self.config.mailbox_limit:
            return False
        self.delivered_ids.add(sent['event_id'])
        delivery = self.store.emit('message_delivered', actor=sent['actor'], recipient=sent['recipient'],
                                   payload=sent['payload'], parents=[sent['event_id']])
        recipient.mailbox.append(dict(event_id=delivery['event_id'], actor=sent['actor'],
                                      content=sent['payload'].get('content'), type=sent['payload'].get('type')))
        return True

    def accept(self, agent: AgentState, action, observation: dict, task_id: str, assignment: dict):
        if self.config.decision_protocol == 'feedback-v0.2' and not (
                isinstance(action, dict) and set(action) == {'candidate', 'message', 'used_event_ids'}
                and isinstance(action['candidate'], list)
                and all(type(value) is int for value in action['candidate'])
                and action['message'] is None and action['used_event_ids'] == []):
            self.store.emit('invalid_action', actor=agent.agent_id, task_id=task_id,
                            payload={'reason':'action violates the solo feedback protocol'})
            self.invalid += 1
            return 'protocol_failure'
        if not isinstance(action, dict):
            self.store.emit('invalid_action', actor=agent.agent_id, task_id=task_id, payload={'reason':'action must be an object'})
            self.invalid += 1
            return
        # Claims of use are limited to data actually delivered in this observation.
        visible = {m['event_id'] for m in observation['mailbox']}
        used = action.get('used_event_ids', [])
        used = list(dict.fromkeys(e for e in used if type(e) is int and e in visible)) if isinstance(used, list) else []
        parents = [assignment['event_id']] + used
        for event_id in used:
            self.store.emit('artifact_used', actor=agent.agent_id, parents=[event_id], task_id=task_id,
                            payload={'attribution':'policy-reported use; not a causal claim'})
            self.reuse += 1
        candidate = action.get('candidate', [])
        candidate_event = self.store.emit('candidate_submitted', actor=agent.agent_id, task_id=task_id,
                                          payload={'candidate':candidate}, parents=parents)
        tick = time.perf_counter()
        result = validate_candidate(self.config.m, candidate)
        self.verification_seconds += time.perf_counter() - tick
        artifact_id = agent.agent_id + '/candidate'
        artifact_body = dict(candidate=candidate, assumptions=f'Universe 1..{self.config.m}; no distinct 3-term AP',
                             valid=result.valid, reason=result.reason, parent_event_ids=[candidate_event['event_id']])
        version = self.store.artifact(artifact_id, agent.agent_id, artifact_body)
        progress = 0
        if result.valid:
            candidate = sorted(candidate)
            key = tuple(candidate)
            if key in self.seen_candidates:
                self.duplicates += 1
            self.seen_candidates.add(key)
            if len(candidate) > len(agent.private_best):
                progress = len(candidate) - len(agent.private_best)
                agent.private_best = candidate
            if len(candidate) > self.lower_bound:
                self.best, self.lower_bound = candidate, len(candidate)
        else:
            self.invalid += 1
        verification = self.store.emit('verification', actor='verifier', recipient=agent.agent_id,
            task_id=task_id, parents=[candidate_event['event_id']], artifact_id=artifact_id, artifact_version=version,
            verification_status='valid' if result.valid else 'invalid',
            payload=dict(artifact_body, lower_bound=self.lower_bound, upper_bound=self.upper_bound))
        agent.last_event = verification['event_id']
        if self.config.memory_mode == 'history_feedback':
            omitted = len(json.dumps(candidate).encode()) > 1024
            feedback = dict(decision=agent.calls, candidate=None if omitted else candidate,
                            valid=result.valid, reason=result.reason,
                            forbidden_triple=list(result.forbidden_triple) if result.forbidden_triple else None,
                            verification_event_id=verification['event_id'])
            if omitted:
                feedback['candidate_omitted'] = True
            agent.attempt_history.append(feedback)
            del agent.attempt_history[:-self.config.history_limit]
            self.store.emit('feedback_recorded', actor='verifier', recipient=agent.agent_id,
                            task_id=task_id, parents=[verification['event_id']], payload=feedback)
        self.stats[agent.agent_id]['verified_progress'] += progress
        message = action.get('message')
        if message is not None:
            # Candidate claims travel only after independent local validation.
            content = message.get('content') if isinstance(message,dict) else None
            if isinstance(content,dict) and 'candidate' in content and not validate_candidate(self.config.m, content['candidate']).valid:
                self.invalid += 1
                self.store.emit('claim_rejected', actor=agent.agent_id, payload={'reason':'invalid candidate claim'}, parents=parents)
            else:
                self.send(agent, message, parents+[verification['event_id']], task_id)
        return 'valid' if result.valid else 'invalid_candidate'

    async def work(self, agent: AgentState, step: int):
        async with self.semaphore:
            if self.stop:
                return
            task_id = f'task-{step}'
            assignment = self.store.emit('assignment', actor='scheduler', recipient=agent.agent_id,
                task_id=task_id, payload={'role':agent.role,'lease':'one decision; released on completion or failure'})
            observation = self.observation(agent, task_id)
            for entry in observation['mailbox']:
                self.store.emit('message_read', actor=agent.agent_id, parents=[entry['event_id']], task_id=task_id,
                                payload={'meaning':'included in decision observation'})
            agent.mailbox.clear()
            self.store.emit('observation', actor=agent.agent_id, task_id=task_id, payload=observation)
            for entry in observation.get('attempt_history', []):
                self.store.emit('feedback_read', actor=agent.agent_id, task_id=task_id,
                                parents=[entry['verification_event_id']],
                                payload={'decision':entry['decision'], 'meaning':'included in decision observation'})
            if self.config.mode == 'live':
                estimate = self.provider.estimate(observation)
            else:
                estimate = max(1, len(json.dumps(observation).encode()) // 4)
            action = None
            for attempt in range(self.config.max_retries + 1):
                if self.stop:
                    self.store.emit('task_cancelled', actor=agent.agent_id, task_id=task_id, payload={'reason': self.stop})
                    return
                local_attempt_id = f'{task_id}/attempt-{attempt}'
                attempt_id = (f'{self.run_id}/{local_attempt_id}'
                              if self.campaign_id is not None else local_attempt_id)
                admitted = self.ledger.reserve(self.run_id, attempt_id, agent.agent_id, task_id, task_id, attempt,
                    'coordination' if agent.role == 'coordinator' else 'research', estimate,
                    self.config.max_output, self.config.model,
                    context_estimates={'observation':estimate})
                if not admitted:
                    self.stop = 'budget_exhausted'
                    self.store.emit('task_cancelled', actor=agent.agent_id, task_id=task_id,
                                    payload={'reason':self.stop})
                    return
                outcome, usage, request_id = 'completed', None, None
                client_request_id = str(uuid.uuid4()) if self.config.mode == 'live' else None
                try:
                    if self.config.mode == 'live':
                        self.store.emit('provider_request', actor=agent.agent_id, task_id=task_id,
                                        payload={'attempt_id':attempt_id, 'client_request_id':client_request_id})
                        # A bounded thread call is awaited to completion. Cancelling Python cannot retract provider spend.
                        correlated_call = getattr(self.provider, 'call_with_id', None)
                        if callable(correlated_call):
                            result = await asyncio.to_thread(correlated_call, observation, client_request_id)
                        else:
                            result = await asyncio.to_thread(self.provider.call, observation)
                        action, usage, request_id, outcome = result.action, result.usage, result.request_id, result.outcome
                        if result.service_tier and result.service_tier != 'default':
                            usage = None  # Unexpected billing semantics remain unresolved.
                            outcome, action = 'unexpected_service_tier', None
                        if self.campaign_id is not None or self.config.decision_protocol == 'feedback-v0.2':
                            if result.model != self.config.model:
                                usage = None
                                outcome, action = 'unexpected_model', None
                            elif result.service_tier != 'default':
                                usage = None
                                outcome, action = 'unexpected_service_tier', None
                        self.store.emit('provider_result', actor=agent.agent_id, task_id=task_id,
                            payload={'attempt_id':attempt_id, 'client_request_id':client_request_id,
                                     'request_id':request_id, 'diagnostics':getattr(result, 'diagnostics', {}),
                                     'model':result.model,'service_tier':result.service_tier,'outcome':outcome, 'usage':result.usage})
                        if usage is not None:
                            usage = dict(usage, reported_model=result.model, reported_service_tier=result.service_tier)
                    elif self.config.mode == 'scripted':
                        action = {'candidate':[1,2,4] if self.config.m >= 4 else [1], 'message':None, 'used_event_ids':[]}
                    else:
                        action = decide(observation, agent.rng)
                    if self.config.mode != 'live':
                        usage = {'input_tokens':estimate,'output_tokens':min(self.config.max_output, max(1,len(json.dumps(action))//4)),
                                 'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}
                except ProviderFailure as exc:
                    outcome, request_id = exc.outcome, exc.request_id
                    self.store.emit('provider_failure', actor=agent.agent_id, task_id=task_id,
                                    payload={'attempt_id':attempt_id, 'client_request_id':client_request_id,
                                             'request_id':request_id, 'outcome':outcome,
                                             'diagnostics':getattr(exc, 'diagnostics', {})})
                except asyncio.CancelledError:
                    self.ledger.settle(attempt_id, 'cancelled_unknown', None)
                    self.store.emit('task_cancelled', actor=agent.agent_id, task_id=task_id, payload={'reason':'cancelled_unknown'})
                    raise
                except Exception as exc:
                    outcome = 'worker_error_' + type(exc).__name__
                self.ledger.settle(attempt_id, outcome, usage, request_id=request_id)
                ledger_summary = self.ledger.summary(self.run_id)
                entry = next(e for e in self.ledger.entries(self.run_id) if e['attempt_id'] == attempt_id)
                self.stats[agent.agent_id]['estimated_cost'] += float(entry.get('estimated_cost') or 0)
                self.store.emit('usage', actor=agent.agent_id, task_id=task_id,
                    payload=dict(attempt_id=attempt_id, input_tokens=usage.get('input_tokens') if usage else None,
                        output_tokens=usage.get('output_tokens') if usage else None,
                        cost=entry.get('observed_cost'), simulated=self.config.mode != 'live', outcome=outcome,
                        cached_input_tokens=entry.get('cached_input_tokens'), reasoning_tokens=entry.get('reasoning_tokens'),
                        status=entry.get('status'), currency='USD',
                        committed_cost=ledger_summary.get('committed_cost'), remaining_cost=ledger_summary.get('remaining_cost'),
                        committed_tokens=ledger_summary.get('committed_tokens'), remaining_tokens=ledger_summary.get('remaining_tokens')))
                self.ledger.export(self.run_id, self.directory)
                if self.stop_on_failure and (ledger_summary['unknown_attempts'] or
                                             ledger_summary['unknown_cost_attempts']):
                    self.stop = 'unresolved_usage'
                if action is not None and outcome == 'completed':
                    break
                action = None
                self.store.emit('attempt_failed', actor=agent.agent_id, task_id=task_id,
                                payload={'attempt':attempt,'outcome':outcome,'possible_charge':usage is None})
                if self.stop_on_failure:
                    self.stop = self.stop or 'provider_failure'
                    break
            agent.calls += 1
            self.stats[agent.agent_id]['pulls'] += 1
            if action is not None:
                invalid_before = self.invalid
                accepted = self.accept(agent, action, observation, task_id, assignment)
                if accepted == 'protocol_failure':
                    self.stop = self.stop or 'protocol_failure'
                    action = None
                elif (self.stop_on_failure and self.invalid != invalid_before
                      and self.config.decision_protocol != 'feedback-v0.2'):
                    self.stop = self.stop or 'invalid_candidate'
                if action is not None:
                    self.workers_completed += 1
            self.store.emit('task_completed' if action is not None else 'task_failed', actor=agent.agent_id, task_id=task_id)

    async def guarded_work(self, agent: AgentState, step: int):
        try:
            await self.work(agent, step)
        except BaseException:
            self.stop = 'worker_failure'
            raise

    async def run(self) -> dict:
        started = time.perf_counter()
        cfg = asdict(self.config)
        try:
            revision = subprocess.check_output(['git','rev-parse','HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(['git','status','--porcelain'], text=True))
        except (subprocess.SubprocessError,OSError):
            revision, dirty = 'unavailable', None
        metadata = dict(cfg, run_id=self.run_id, code_revision=revision, working_tree_dirty=dirty,
                        scheduling='offline: serial immediate delivery in agent order; live: concurrency-limited tasks with round barriers',
                        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
                        team=[{'agent_id':a.agent_id,'role':a.role} for a in self.team])
        if self.campaign_id is not None:
            metadata['campaign_id'] = self.campaign_id
        if self.stop_on_failure:
            metadata['stop_on_failure'] = True
        write_json(self.directory/'config.json',metadata)
        self.store.emit('run_started',payload=metadata)
        worker_seconds = 0.0
        try:
            # One owned task per agent per round; bounded by N and concurrency, never an unbounded queue.
            step = 0
            while step < self.config.steps and not self.stop:
                width = min(self.config.agents, self.config.steps-step)
                selected = self.team[:width]
                if self.config.allocation == 'exploratory':
                    chosen = exploratory_priority(list(self.by_id), self.stats, step)
                    selected = [self.by_id[chosen]]
                outcomes = await asyncio.gather(
                    *(self.guarded_work(agent, step+i) for i,agent in enumerate(selected)),
                    return_exceptions=True)
                # Drain every started sibling before closing stores or surfacing an error.
                for outcome in outcomes:
                    if isinstance(outcome, BaseException):
                        raise outcome
                step += len(selected)
            self.stop = self.stop or 'step_limit'
            worker_seconds = time.perf_counter()-started
            # Hidden evaluation happens only after workers stop. No evaluator answer feeds their contexts.
            oracle = await asyncio.to_thread(exact_optimum, self.config.m, self.config.oracle_timeout)
            self.upper_bound = oracle.upper_bound
            gap = self.upper_bound-self.lower_bound
            self.store.emit('evaluation', actor='evaluator', payload=asdict(oracle))
            if gap == 0 and self.stop == 'step_limit':
                self.stop = 'solved'
            optimal_times = [e['elapsed_seconds'] for e in self.store.events() if e['event_type']=='verification'
                             and e['payload'].get('valid') and len(e['payload'].get('candidate',[]))==self.upper_bound]
            usage = self.ledger.summary(self.run_id)
            summary = dict(run_id=self.run_id, mode=self.config.mode, m=self.config.m, agents=self.config.agents,
                condition=self.config.condition, lower_bound=self.lower_bound, upper_bound=self.upper_bound,
                decision_protocol=self.config.decision_protocol, memory_mode=self.config.memory_mode,
                unique_valid_candidates=len(self.seen_candidates),
                decisions_attempted=sum(a.calls for a in self.team),
                gap=gap, best_candidate=self.best, stopping_reason=self.stop, decisions_completed=self.workers_completed,
                elapsed_seconds=time.perf_counter()-started, worker_seconds=worker_seconds,
                oracle=asdict(oracle), verification_seconds=self.verification_seconds,
                time_to_optimal_candidate_seconds=min(optimal_times) if optimal_times else None,
                time_to_verified_optimality_seconds=time.perf_counter()-started if gap==0 else None,
                invalid_claims=self.invalid, duplicate_candidates=self.duplicates, artifact_reuse=self.reuse,
                messages=self.messages, message_bytes=self.message_size, usage=usage,
                actual_model_calls=usage.get('actual_calls',0),
                actual_model_cost='0' if self.config.mode!='live' else usage.get('actual_model_cost'),
                efficiency_note='Algorithmic fixture tokens/cost are simulated; no LLM efficiency conclusion.' if self.config.mode!='live' else 'Provider usage, calculated cost; not a billing statement.')
            self.store.emit('run_finished',payload=summary)
            write_json(self.directory/'summary.json',summary)
            self.ledger.export(self.run_id,self.directory)
            return summary
        except BaseException as exc:
            self.store.emit('run_interrupted', payload={'reason':type(exc).__name__})
            write_json(self.directory/'summary.json',dict(run_id=self.run_id,stopping_reason='interrupted',
                lower_bound=self.lower_bound,upper_bound=self.upper_bound,usage=self.ledger.summary(self.run_id)))
            self.ledger.export(self.run_id,self.directory)
            raise
        finally:
            self.store.close()
            self.ledger.close()
