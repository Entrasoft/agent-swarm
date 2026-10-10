# Coordination v0.3: Stage 0 and Stage 1 record

The owner approved Stages 0 and 1 of the
[v0.3 proposal](coordination-v03-proposal.md) on 2026-10-10. Both stages are
offline: **no model requests were made and no API spending occurred.** Both
gates passed. Stage 2 and later stages still need separate approval.

## Stage 0: verifier, snapshot and targets

### Verifier

[`swarm_lab/codes.py`](../swarm_lab/codes.py) builds one-generator quasi-cyclic
codes over GF(3) and GF(4) and computes the exact minimum distance d and the
number of weight-d codewords. It enumerates every codeword up to scalar
multiples, with coordinates packed into integers.

It reproduces the known codes named in the proposal
([tests](../tests/test_codes.py)):

| Code | Expected | Computed |
| --- | --- | --- |
| Ternary Golay [11, 6] | d = 5, 132 words | d = 5, 132 words |
| Extended ternary Golay [12, 6] | d = 6, 264 words | d = 6, 264 words |
| Hexacode [6, 3] over GF(4) | d = 4, 45 words | d = 4, 45 words |

It also matches a separate brute-force implementation on 150 random codes.

### Verification limits

Profiled on 2026-10-10 on an Apple M3 Max with Python 3.12.8:

| Field | Largest k verified within about one second | Next k |
| --- | --- | --- |
| GF(3) | k = 14: 0.48 s | k = 15: 1.4 s |
| GF(4) | k = 12: 0.59 s | k = 13: 2.3 s |

### Decisions made in Stage 0

The proposal left these details to Stage 0. Each was fixed and committed before
the snapshot was taken or any target was drawn
([`b420db6`](https://github.com/Entrasoft/agent-swarm/commit/b420db6)):

- **Code family.** A target [n, k] uses ⌈n/k⌉ circulant blocks of size k, with
  the trailing coordinates punctured to reach length n.
- **Length range.** 2k ≤ n ≤ 4k, so every candidate has 2–4 blocks and a
  compact action.
- **AI and recency screen.** An entry is rejected if its construction text
  mentions AI terms, or if it was last modified on or after 2023-01-01. The
  second rule conservatively excludes recent work the page does not label.
- **Draw.** Seed 20261010, six targets, examined in shuffled order.
- **Runtime.** A separate module, [`archive_runtime.py`](../swarm_lab/archive_runtime.py),
  rather than a refactor of `runtime.py`. The v0.3 round-snapshot semantics
  differ from the legacy runtime, and keeping them apart leaves the code behind
  earlier evidence untouched. The `m ≤ 24` limits therefore did not need to
  change.
- **TLS.** The python.org Python build had no CA certificates configured, so
  the snapshot ran with `SSL_CERT_FILE=/etc/ssl/cert.pem`, the macOS system
  bundle. Certificate verification stayed on.

### Snapshot and targets

[`configs/v03/codetables-snapshot.json`](../configs/v03/codetables-snapshot.json)
holds 6,317 table cells from codetables.de, retrieved 2026-10-10 with page
hashes. Of these, 198 entries qualified. The first six drawn all passed the
screen, so none was rejected
([`configs/v03/targets.json`](../configs/v03/targets.json)):

| Field | [n, k] | Best known d (lower–upper) | Blocks | Punctured | Last modified |
| --- | --- | --- | ---: | ---: | --- |
| GF(3) | [56, 14] | 24–28 | 4 | 0 | 2003-09-22 |
| GF(4) | [37, 12] | 16–20 | 4 | 11 | 2001-12-17 |
| GF(3) | [37, 11] | 17–18 | 4 | 7 | 2013-12-09 |
| GF(3) | [50, 14] | 20–24 | 4 | 6 | 2001-12-17 |
| GF(4) | [36, 9] | 19–21 | 4 | 0 | 2002-03-18 |
| GF(4) | [36, 10] | 18–20 | 4 | 4 | 2012-11-28 |

**Gate: passed.** The verifier reproduces every known code, and six targets
qualified, so the fallback task is not needed.

## Stage 1: positive control

The positive control checks that the instrument detects a sharing benefit when
one must exist. Each of four algorithmic agents may change only its own block,
choosing fresh random coefficients on the best code it can see. In the
independent arm an agent sees only its own codes, so its codes never have more
than one nonzero block. In the shared arm agents build on each other's codes.
Both arms had the same simulated token allowance (40,000 per run), and rounds
used the round-snapshot rule.

Run on 2026-10-10 from commit `e88b031`, with no uncommitted source changes,
across 10 seeds × 6 targets × 2 arms = 120 runs. Every run was replayed, with
each verification and observed archive recomputed. Results:
[`examples/v03-positive-control/results.json`](../examples/v03-positive-control/results.json).

| Target | Independent: best d | Shared: best d, range over seeds | Shared: rounds (median) | Independent: rounds (median) |
| --- | ---: | --- | ---: | ---: |
| GF(3) [56, 14] | 1 | 22–23 | 17 | 24 |
| GF(4) [37, 12] | 1 | 15 | 18 | 30 |
| GF(3) [37, 11] | 1 | 14 | 19 | 27 |
| GF(3) [50, 14] | 1 | 18–19 | 17 | 28 |
| GF(4) [36, 9] | 1 | 17–18 | 21 | 28 |
| GF(4) [36, 10] | 1 | 16 | 20 | 29 |

**Gate: passed.** The shared arm beat the independent arm in all 60 seed and
target comparisons, and all 120 runs replayed.

### How to read this

- **The result is by construction.** A code with one nonzero circulant block
  has d = 1, so the independent arm cannot do better. The test shows that the
  archive, provenance and replay machinery register a sharing effect. It is not
  evidence that sharing helps search agents.
- **Token matching works as designed.** Shared observations carry larger codes,
  so the shared arm fit fewer rounds into the same allowance.
- **Structural reuse was recorded.** Shared runs had a median of 47–60 accepted
  codes built on another agent's code, and in every shared run the best code's
  lineage crossed agents. Independent runs had none.
- **No records.** Random coefficients came within one to three of the
  best-known d on every target, but no run matched or beat a record.

## Next

Stage 2, the algorithmic 2×2 with four search strategies, needs the owner's
approval. It also needs the four strategies implemented and committed before it
runs.
