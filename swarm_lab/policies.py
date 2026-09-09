"""Seeded algorithmic workers and transparent experimental allocation.

These policies exercise the protocol without model calls. Their routing and
specialization are programmed heuristics and are not evidence of emergence.
The only mathematical service used here is feasibility validation, not an oracle.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence

from .math_task import validate_candidate


def _greedy(m: int, seed: list[int], rng: random.Random) -> list[int]:
    selected = set(seed)
    remaining = [value for value in range(1, m + 1) if value not in selected]
    rng.shuffle(remaining)
    for value in remaining:
        if validate_candidate(m, [*selected, value]).valid:
            selected.add(value)
    return sorted(selected)


def _message_candidate(m: int, event: Mapping[str, Any]) -> list[int] | None:
    content = event.get("content", {})
    candidate = content.get("candidate") if isinstance(content, dict) else None
    if candidate is None:
        candidate = event.get("candidate")
    if not isinstance(candidate, list) or not validate_candidate(m, candidate).valid:
        return None
    return sorted(candidate)


def decide(observation: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Propose one candidate and at most one point-to-point message.

    ``used_event_ids`` records which peer candidate actually seeded this search.
    Reading a mailbox alone never populates it. Provenance records use, not a
    claim that the peer message improved the verified outcome.
    """
    m = observation["m"]
    private = observation.get("private_best", [])
    if not isinstance(private, list) or not validate_candidate(m, private).valid:
        private = []
    best = sorted(private)
    condition = observation.get("condition", "solo")
    role = observation.get("role", "searcher")
    round_number = observation.get("round", 0)
    peers = [peer for peer in observation.get("peers", []) if peer != observation["agent_id"]]
    messages = observation.get("mailbox", []) if condition in {"fixed", "adaptive"} else []
    used_event_ids: list[str | int] = []
    sender_quality: dict[str, int] = {}
    selected_event: dict[str, Any] | None = None
    for event in messages:
        if not isinstance(event, dict):
            continue
        candidate = _message_candidate(m, event)
        if candidate is None:
            continue
        sender = event.get("actor", event.get("source"))
        if isinstance(sender, str):
            sender_quality[sender] = max(sender_quality.get(sender, 0), len(candidate))
        if len(candidate) > len(best):
            best = candidate
            selected_event = event
    # Some restarts deliberately ignore incumbents; others perturb a feasible
    # seed. Never return a worse candidate than the privately known lower bound.
    seed = best.copy()
    if seed and rng.random() < 0.30:
        seed = []
    elif seed:
        removals = rng.randint(1, max(1, len(seed) // 2))
        for value in rng.sample(seed, removals):
            seed.remove(value)
    trial = _greedy(m, seed, rng)
    # Even on a restart, a superior peer result participates in result selection.
    if selected_event is not None and type(selected_event.get("event_id")) in (str, int):
        used_event_ids.append(selected_event["event_id"])
    candidate = trial if len(trial) > len(best) else best
    outgoing = None
    if peers and condition in {"fixed", "adaptive"}:
        improved = len(candidate) > len(private)
        if condition == "fixed":
            recipient = (
                peers[round_number % len(peers)]
                if role == "coordinator"
                else observation.get("coordinator_id", peers[0])
            )
            message_type = "share_artifact" if role == "coordinator" else "report_result"
            should_send = True
        else:
            # More useful candidates trigger sharing. Periodic requests preserve
            # some exploration when no local improvement has been verified.
            should_send = improved or bool(used_event_ids) or round_number % 4 == 0
            if role == "coordinator":
                # Send help to a peer whose reported candidate is smallest;
                # unobserved peers get priority and ties use the seeded RNG.
                lowest = min(sender_quality.get(peer, -1) for peer in peers)
                recipient = rng.choice([peer for peer in peers if sender_quality.get(peer, -1) == lowest])
            elif not improved and sender_quality:
                available = [peer for peer in peers if peer in sender_quality]
                recipient = max(available, key=lambda peer: sender_quality[peer]) if available else rng.choice(peers)
            else:
                recipient = rng.choice(peers)
            message_type = "share_artifact" if improved else "request_help"
        if should_send and recipient in peers:
            outgoing = {
                "type": message_type,
                "recipient": recipient,
                "content": {
                    "candidate": candidate,
                    "assumptions": f"Universe 1..{m}; distinct three-term arithmetic progressions forbidden.",
                    "search_strategy": "seeded randomized greedy perturbation",
                },
            }
    return {"candidate": candidate, "message": outgoing, "used_event_ids": used_event_ids}


def round_robin(agent_ids: Sequence[str], step: int) -> str:
    """Fixed allocation baseline; preserve the configured agent order."""
    if not agent_ids:
        raise ValueError("at least one agent is required")
    if type(step) is not int or step < 0:
        raise ValueError("step must be a nonnegative integer")
    return agent_ids[step % len(agent_ids)]


def exploratory_priority(
    agent_ids: Sequence[str],
    stats: Mapping[str, Mapping[str, float]],
    step: int,
    exploration: float = 1.0,
) -> str:
    """Experimental progress-per-estimated-cost allocation with exploration.

    Statistics are cumulative ``verified_progress``, ``estimated_cost`` and
    ``pulls``. Every agent receives one initial opportunity. Thereafter the score
    is (mean progress + exploration * sqrt(log(step+2)/pulls)) / mean cost.
    A mean cost of 1 is assumed only when cost is zero or omitted (offline work
    units); positive costs must share a common unit. This heuristic has no
    claimed bandit guarantees.
    """
    round_robin(agent_ids, step)  # Validate the common arguments.
    if not math.isfinite(exploration) or exploration < 0:
        raise ValueError("exploration must be finite and nonnegative")
    scores: dict[str, float] = {}
    for agent in agent_ids:
        record = stats.get(agent, {})
        pulls = record.get("pulls", 0)
        progress = record.get("verified_progress", 0.0)
        cost = record.get("estimated_cost", 0.0)
        if any(not math.isfinite(value) or value < 0 for value in (pulls, progress, cost)):
            raise ValueError("allocation statistics must be finite and nonnegative")
        if pulls == 0:
            return agent
        bonus = exploration * math.sqrt(math.log(step + 2) / pulls)
        mean_cost = cost / pulls if cost > 0 else 1.0
        scores[agent] = (progress / pulls + bonus) / mean_cost
    return max(agent_ids, key=lambda agent: scores[agent])
