"""Seeded algorithmic search strategies for coordination v0.3, Stage 2.

Four programmed analogues of the strategy instructions in the proposal. Each
takes an observation (target and visible archive) and returns an action naming
a visible base. They never see the evaluator, the table record or any archive
the observation does not contain.

1. local: change a few coefficients in one block of the best visible code.
2. recombine: build a child block by block from two visible codes.
3. algebraic: replace one block with another block times x^s(1 + c x^t),
   reduced modulo x^k - 1, so blocks stay algebraically related.
4. repair: find one minimum-weight codeword of the base and make the single
   coefficient change that most increases that codeword's weight.

These are heuristics written for this test; they make no claim of strength.
"""
from __future__ import annotations

import random

from .codes import Target, field_add, field_mul, minimum_word, qc_generator, rank

STRATEGIES = ('local', 'recombine', 'algebraic', 'repair')


def _target(observation: dict) -> Target:
    t = observation['target']
    return Target(q=t['q'], n=t['n'], k=t['k'], lower=0, upper=0)


def _random_code(target: Target, rng: random.Random) -> list[list[int]]:
    return [[rng.randrange(target.q) for _ in range(target.k)] for _ in range(target.blocks)]


def _copy(polynomials) -> list[list[int]]:
    return [list(poly) for poly in polynomials]


def _pick_base(archive: list[dict], rng: random.Random) -> dict:
    return archive[0] if rng.random() < 0.7 else rng.choice(archive)


def _mutate(target: Target, polynomials, rng: random.Random, changes: int) -> list[list[int]]:
    block = rng.randrange(target.blocks)
    for position in rng.sample(range(target.k), changes):
        current = polynomials[block][position]
        polynomials[block][position] = rng.choice([v for v in range(target.q) if v != current])
    return polynomials


def _action(base: dict | None, polynomials, extra_used=()) -> dict:
    used = ([base['event_id']] if base else []) + [e for e in extra_used if not base or e != base['event_id']]
    return dict(base=base['event_id'] if base else None, polynomials=polynomials, used_event_ids=used)


def local(observation: dict, rng: random.Random) -> dict:
    target, archive = _target(observation), observation['archive']
    if not archive:
        return _action(None, _random_code(target, rng))
    base = _pick_base(archive, rng)
    return _action(base, _mutate(target, _copy(base['polynomials']), rng, rng.randint(1, 3)))


def recombine(observation: dict, rng: random.Random) -> dict:
    target, archive = _target(observation), observation['archive']
    if len(archive) < 2:
        return local(observation, rng)
    first = archive[0]
    second = rng.choice(archive[1:])
    choices = [rng.random() < 0.5 for _ in range(target.blocks)]
    child = [list((first if take_first else second)['polynomials'][b]) for b, take_first in enumerate(choices)]
    if child in (first['polynomials'], second['polynomials']):
        child = _mutate(target, child, rng, 1)
    base, other = (first, second) if sum(choices) * 2 >= target.blocks else (second, first)
    return _action(base, child, [other['event_id']])


def _multiply(q: int, k: int, a: list[int], b: list[int]) -> list[int]:
    product = [0] * k
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                if y:
                    product[(i + j) % k] = field_add(q, product[(i + j) % k], field_mul(q, x, y))
    return product


def algebraic(observation: dict, rng: random.Random) -> dict:
    target, archive = _target(observation), observation['archive']
    if not archive:
        return _action(None, _random_code(target, rng))
    base = archive[0]
    polynomials = _copy(base['polynomials'])
    source, destination = rng.sample(range(target.blocks), 2)
    multiplier = [0] * target.k
    shift = rng.randrange(target.k)
    multiplier[shift] = 1
    second = (shift + rng.randrange(1, target.k)) % target.k
    multiplier[second] = field_add(target.q, multiplier[second], rng.randrange(target.q))
    polynomials[destination] = _multiply(target.q, target.k, polynomials[source], multiplier)
    if polynomials == base['polynomials']:
        polynomials = _mutate(target, polynomials, rng, 1)
    return _action(base, polynomials)


def repair(observation: dict, rng: random.Random) -> dict:
    target, archive = _target(observation), observation['archive']
    if not archive:
        return _action(None, _random_code(target, rng))
    base = archive[0]
    q, k, n = target.q, target.k, target.n
    rows = qc_generator(target, base['polynomials'])
    if rank(q, rows) != k:
        return local(observation, rng)
    message = minimum_word(q, rows)
    word = [0] * n
    for coefficient, row in zip(message, rows):
        if coefficient:
            word = [field_add(q, a, field_mul(q, coefficient, b)) for a, b in zip(word, row)]
    best_gain, options = None, []
    for block in range(target.blocks):
        width = min(k, n - block * k)
        if width <= 0:
            continue
        segment = word[block * k: block * k + width]
        current = sum(1 for value in segment if value)
        for position in range(k):
            for delta in range(1, q):
                # Changing a_block[position] by delta adds delta * m_j at t = position + j (mod k).
                changed = list(segment)
                for j, m in enumerate(message):
                    t = (position + j) % k
                    if m and t < width:
                        changed[t] = field_add(q, changed[t], field_mul(q, delta, m))
                gain = sum(1 for value in changed if value) - current
                if best_gain is None or gain > best_gain:
                    best_gain, options = gain, [(block, position, delta)]
                elif gain == best_gain:
                    options.append((block, position, delta))
    block, position, delta = rng.choice(options)
    polynomials = _copy(base['polynomials'])
    polynomials[block][position] = field_add(q, polynomials[block][position], delta)
    return _action(base, polynomials)


STRATEGY_FUNCTIONS = {'local': local, 'recombine': recombine, 'algebraic': algebraic, 'repair': repair}


def strategy_policy(observation: dict, rng: random.Random) -> dict:
    return STRATEGY_FUNCTIONS[observation['strategy']](observation, rng)
