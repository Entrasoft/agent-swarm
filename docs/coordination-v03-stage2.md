# Coordination v0.3: Stage 2 record

The owner approved Stage 2 of the [v0.3 proposal](coordination-v03-proposal.md)
on 2026-10-12. It ran offline with seeded algorithmic agents: **no model
requests and no API spending.**

**The gate failed.** The sharing team with mixed strategies (S-D) beat the
best-of-N baseline (I-H) on at least 4 of 6 targets in **11 of 30 seeds**; the
gate required 20. Under the proposal's rule, a failed gate ends the proposal
with a reported result. Stages 3 and 4 do not proceed under this approval.

## What ran

- **Strategies.** Four seeded heuristics in
  [`v03_strategies.py`](../swarm_lab/v03_strategies.py):
  - **local:** change one to three coefficients in one block;
  - **recombine:** build a child block by block from two archived codes;
  - **algebraic:** replace a block with another block times x^s(1 + c·x^t);
  - **repair:** find a minimum-weight codeword and make the single coefficient
    change that most raises its weight.
- **Arms.** I-H, I-D, S-H and S-D with four agents each, plus solo with one
  agent.
  - Mixed-strategy (D) arms give agent i strategy i.
  - Same-strategy (H) arms and solo use strategy (seed mod 4) for every agent.
    That gives each strategy 7 or 8 of the 30 seeds.
- **Budget.** 40,000 simulated tokens per run, in whole rounds where every
  agent sees the archive as it stood when the round began.
- **Scale.** 5 arms × 6 targets × 30 seeds = 900 runs, from commit
  [`577dc47`](https://github.com/Entrasoft/agent-swarm/commit/577dc47) with no
  uncommitted source changes. That is 71,568 decisions in total.
- **Replay.** All 900 runs replayed, with every verification and observed
  archive recomputed.
- **Run time.** 2026-10-13, 02:23–04:02 UTC. Other load on the machine made it
  slower than profiled; seeded runs are unaffected by load.
- **Gate rule.** Fixed in code before the run: a seed is a win for S-D when it
  beats I-H strictly, ranked by (d, fewer minimum-weight codewords), on at least
  4 of the 6 targets.

Results: [`examples/v03-stage2/results.json`](../examples/v03-stage2/results.json).

## Gate

Targets won by S-D in each seed, seeds 0–29:

`1 2 5 5 2 2 6 5 2 1 5 4 2 1 6 2 2 2 6 4 3 2 6 3 2 3 6 2 2 1`

That is 11 seeds with at least 4 wins. **Gate: failed.**

## Per target

The median best d was the same in every arm on every target:

| Target | Record d | Median best d, all arms | S-D vs I-H: wins / ties / losses |
| --- | ---: | ---: | --- |
| GF(3) [56, 14] | 24 | 22 | 17 / 8 / 5 |
| GF(4) [37, 12] | 16 | 15 | 20 / 2 / 8 |
| GF(3) [37, 11] | 17 | 14 | 14 / 3 / 13 |
| GF(3) [50, 14] | 20 | 18 | 13 / 10 / 7 |
| GF(4) [36, 9] | 19 | 18 | 16 / 2 / 12 |
| GF(4) [36, 10] | 18 | 16 | 15 / 2 / 13 |

**No run beat a record.** One I-H run, seed 20 on GF(3) [56, 14], matched the
record d = 24, with 2,380 minimum-weight codewords. The table does not report
how many minimum-weight words the record code has, so it cannot be ranked
against it.

## Exploratory analysis

These comparisons were not pre-registered and are not corrected for multiple
testing. They describe where the small S-D advantage came from; they do not
change the gate result.

Pooled over all 180 seed and target pairs, with a win meaning a higher d or, at
equal d, fewer minimum-weight codewords:

| Comparison | d higher / lower | Same d, fewer / more min-weight words | Exact ties | One-sided sign test p |
| --- | --- | --- | ---: | ---: |
| S-D vs I-H (help) | 38 / 11 | 57 / 47 | 27 | 0.002 |
| I-D vs I-H (diversity alone) | 36 / 5 | 55 / 55 | 29 | 0.007 |
| S-H vs I-H (sharing alone) | 14 / 22 | 35 / 54 | 55 | 0.99 |
| S-D vs I-D (sharing, given diversity) | 14 / 16 | 64 / 55 | 31 | 0.31 |
| S-D vs S-H (diversity, given sharing) | 46 / 14 | 63 / 43 | 14 | < 0.001 |
| Solo vs I-H (depth vs breadth) | 14 / 42 | 35 / 48 | 41 | > 0.99 |

What this suggests:

- **Diversity, not sharing, drove S-D's edge.** Mixed strategies beat a single
  strategy with or without sharing. Adding sharing to a mixed team changed
  little, and adding it to a same-strategy team made results slightly worse.
- **The advantage was mostly in the tiebreak.** Medians of d were identical in
  every arm. Most S-D wins came from fewer minimum-weight codewords at the same
  d.
- **Breadth beat depth.** Four independent agents beat one agent given the same
  total budget.
- **Reuse occurred without benefit.** Shared runs had a median of 45–57 codes
  built on another agent's code, yet sharing did not improve results. This is
  the distinction the publication notes draw between observable reuse and
  improved verified outcomes.

These patterns come from programmed heuristics. They say nothing directly about
model agents. They do show that, on these targets and with this archive design,
even programmed agents did not gain from sharing.

## Limits

- **Assigned strategies.** The heuristics are simple. Stronger search, such as
  longer runs or larger moves, might change the picture.
- **The 40,000-token budget allows about 18–22 rounds per team**, or 72–88
  decisions. Sharing may need longer runs to compound.
- **A top-8 archive** can concentrate every agent on the same best code, which
  is the over-migration effect reported in prior work. The homogeneous result
  is consistent with that.
- **Uneven strategy rotation.** Same-strategy arms used each strategy in 7 or 8
  seeds, not exactly equally.

## Status

Per the proposal, the failed gate ends v0.3 with this reported result. Stages
3 and 4 are not authorized by the current approvals, and no paid stage has run.
Any redesign, for example a different sharing rule, longer runs or a new task,
would need a new proposal with its own gates, written knowing these results.
