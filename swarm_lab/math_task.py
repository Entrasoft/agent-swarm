"""Trusted arithmetic-progression validation and an evaluation-only exact solver.

The runtime may use ``exact_optimum`` for hidden evaluation. Agent observations
must contain neither this solver nor its result.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from time import perf_counter
from typing import Iterable


SOLVER_VERSION = "stdlib-ap-branch-and-bound/1"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str
    forbidden_triple: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class OracleResult:
    status: str
    lower_bound: int
    upper_bound: int
    candidate: list[int]
    elapsed_seconds: float
    nodes: int
    solver_version: str = SOLVER_VERSION


def _check_m(m: int) -> None:
    if type(m) is not int or m < 0:
        raise ValueError("m must be a nonnegative integer")


def forbidden_triples(m: int) -> tuple[tuple[int, int, int], ...]:
    """Enumerate each distinct three-term arithmetic progression exactly once."""
    _check_m(m)
    return tuple(
        (a, b, 2 * b - a)
        for a in range(1, m + 1)
        for b in range(a + 1, (m + a) // 2 + 1)
    )


def validate_candidate(m: int, candidate: Iterable[int]) -> ValidationResult:
    """Check types, membership, uniqueness, and arithmetic progressions.

    Booleans and integral floats are rejected: JSON ``true`` is not the integer
    1 in this protocol. Geometric progressions are intentionally allowed.
    """
    _check_m(m)
    if isinstance(candidate, (str, bytes, dict)):
        return ValidationResult(False, "candidate must be a sequence of integers")
    try:
        values = list(candidate)
    except TypeError:
        return ValidationResult(False, "candidate must be a sequence of integers")
    if any(type(value) is not int for value in values):
        return ValidationResult(False, "candidate members must be integers")
    if any(value < 1 or value > m for value in values):
        return ValidationResult(False, f"candidate members must be in 1..{m}")
    members = set(values)
    if len(members) != len(values):
        return ValidationResult(False, "candidate contains duplicate members")
    ordered = sorted(members)
    for index, a in enumerate(ordered):
        for b in ordered[index + 1 :]:
            c = 2 * b - a
            if c in members:
                return ValidationResult(False, "candidate contains a forbidden arithmetic progression", (a, b, c))
    return ValidationResult(True, "valid")


def exact_optimum(m: int, timeout_seconds: float = 5.0) -> OracleResult:
    """Deterministic branch-and-bound with sound bounds even on timeout.

    A stack node represents a feasible selected set and still-available members.
    Selecting v removes every remaining member that would complete a forbidden
    triple with v and a previously selected member. Include/exclude branching
    covers all feasible sets; selected-count + available-count is an upper bound
    on every completion. The maximum bound over the unfinished frontier remains
    sound if the deadline interrupts the search.
    """
    _check_m(m)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("timeout_seconds must be a finite nonnegative number")
    if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
        raise ValueError("timeout_seconds must be a finite nonnegative number")
    started = perf_counter()
    deadline = started + timeout_seconds
    best = 0
    best_count = 0
    nodes = 0
    # Each state is (selected bit mask, available bit mask).
    frontier = [(0, (1 << m) - 1)]
    timed_out = False
    while frontier:
        if perf_counter() >= deadline:
            timed_out = True
            break
        selected, available = frontier.pop()
        nodes += 1
        selected_count = selected.bit_count()
        if selected_count > best_count:
            best, best_count = selected, selected_count
        if selected_count + available.bit_count() <= best_count:
            continue
        bit = available & -available
        value = bit.bit_length()  # Values start at 1, bit positions at 0.
        remainder = available ^ bit
        # Excluding value leaves the same selected set and a smaller universe.
        frontier.append((selected, remainder))
        blocked = 0
        previous = selected
        while previous:
            other_bit = previous & -previous
            other = other_bit.bit_length()
            previous ^= other_bit
            for completion in (2 * value - other, 2 * other - value):
                if 1 <= completion <= m:
                    blocked |= 1 << (completion - 1)
            if (value + other) % 2 == 0:
                completion = (value + other) // 2
                blocked |= 1 << (completion - 1)
        # LIFO processes inclusion first; this usually finds a lower bound early.
        frontier.append((selected | bit, remainder & ~blocked))
    upper = best_count
    if timed_out:
        upper = max(
            [best_count]
            + [selected.bit_count() + available.bit_count() for selected, available in frontier]
        )
    # Frontier bounds can themselves prove optimality at the deadline.
    status = "optimal" if upper == best_count else "timed_out"
    return OracleResult(
        status=status,
        lower_bound=best_count,
        upper_bound=upper,
        candidate=[value for value in range(1, m + 1) if best & (1 << (value - 1))],
        elapsed_seconds=perf_counter() - started,
        nodes=nodes,
    )
