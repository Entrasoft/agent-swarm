# Terra live comparison: preserved partial results

The comparison stopped after **95 attempted calls across ten of twenty planned
runs** because one request had an unknown transport outcome and no usage
telemetry. Five runs completed twelve decisions, four ended on known failures,
one was interrupted, and ten never started. None of the ten attempted runs
found the exact optimum of ten: their best verified candidate sizes were eight
or nine. This partial sample does not establish a coordination advantage,
equivalence between configurations, or relative failure rates.

The known usage subtotal is **156,639 tokens and USD 1.499658 calculated cost**.
One unresolved attempt retains **28,075 tokens and USD 0.3076875** in reservations.
Actual total usage and calculated cost remain unknown; billing is unreconciled.
The campaign halted under its declared rule, with no retries or replacement
calls. Resolving that usage alone does not authorize another campaign or a
continuation.

## Frozen design and execution

The owner approved at most 240 calls, USD 20 and 2,000,000 tokens, divided into
twenty equal allowances of twelve calls, USD 1 and 100,000 tokens. The
[protocol](live-comparison-protocol.md) and implementation were committed at
[`4a30a2519491f355c60bcaa19799ab14010e71ab`](https://github.com/Entrasoft/agent-swarm/commit/4a30a2519491f355c60bcaa19799ab14010e71ab)
before inference. The [manifest](../examples/terra-comparison/manifest.json)
records campaign `terra-comparison-7542010a-114a-4067-8e1a-e133c36f66f1`,
the full protocol, source hashes, fixed allowances, randomized schedule and
price snapshot. Preparation was recorded at 2026-09-09 23:01:22 UTC. The
first run started at 23:01:45.710 UTC; the last run's halt was finalized at
23:42:48.180 UTC that day.

Each run sought the largest subset of integers 1 through 24 containing no three
distinct numbers in arithmetic progression. All conditions used m=24,
`gpt-5.6-terra`, medium reasoning, default service tier,
concurrency one, 25,000 maximum output tokens, a configured 120-second timeout
and zero retries. Solo had one searcher; independent had four isolated
searchers; fixed and adaptive each had one coordinator plus three searchers.
Fixed permitted star routing; adaptive permitted peer routing. Coordinators
submitted candidates and consumed the same decision allowances as searchers.
Sequential observations incorporated only that agent's private best and
permitted delivered messages. The hidden exact evaluator ran after each worker
phase and could not improve the reported worker result.

The [separate calibration](terra-calibration-results.md) selected m=24. All six
calibration calls and outcomes, including the three at m=24, are excluded here,
as is the earlier integration pilot.
Repetition IDs organize the planned blocks; they do not control provider
sampling or establish independent, paired deterministic draws.

## All conditions and all planned runs

The quality distributions below use only attempted runs with measured quality:
three solo, three independent, two fixed and two adaptive. Every condition still
has five planned rows. A completed run means its twelve-decision allowance was
used without an earlier failure; it does not mean the mathematical task was
solved. No run stopped for a token or currency budget admission failure.

| Condition | Attempted / planned | Completed / failed / interrupted / unstarted | Solved / attempted | L median [range] | Known tokens | Known calculated USD |
| --- | ---: | --- | ---: | --- | ---: | ---: |
| Solo | 3 / 5 | 1 / 1 / 1 / 2 | 0 / 3 | 9 [8–9] | 39,706† | 0.386382† |
| Independent | 3 / 5 | 3 / 0 / 0 / 2 | 0 / 3 | 9 [8–9] | 54,437 | 0.514824 |
| Fixed | 2 / 5 | 0 / 2 / 0 / 3 | 0 / 2 | 9 [9–9] | 30,968 | 0.299966 |
| Adaptive | 2 / 5 | 1 / 1 / 0 / 3 | 0 / 2 | 8.5 [8–9] | 31,528 | 0.298486 |

A dagger (†) marks an incomplete subtotal, excluding the unknown amount for the
last solo request. Failures remain in every usage subtotal. Cost per verified
solution is undefined because there were zero solutions; solo and campaign
cost accounting are additionally incomplete. The smaller observed totals for
some conditions partly reflect fewer attempts and early failures, so they are
not evidence of superior efficiency.

`L` is the best independently valid worker candidate size, `U` is the verified
upper bound, and gap is `U − L`. Every measured U is ten. All measured solved
values are false; unstarted quality and solved values are missing. Dashes below
retain missing run observations instead of assigning zero quality or cost.

| Order | Run | Status | Attempts / completed decisions | L / U / gap | Known tokens | Known calculated USD |
| ---: | --- | --- | ---: | --- | ---: | ---: |
| 1 | [r01-independent](../examples/terra-comparison/r01-independent/summary.json) | completed | 12 / 12 | 9 / 10 / 1 | 22,342 | 0.221924 |
| 2 | [r01-fixed](../examples/terra-comparison/r01-fixed/summary.json) | failed | 10 / 9 | 9 / 10 / 1 | 20,596 | 0.201822 |
| 3 | [r01-adaptive](../examples/terra-comparison/r01-adaptive/summary.json) | failed | 6 / 6 | 8 / 10 / 2 | 14,725 | 0.149910 |
| 4 | [r01-solo](../examples/terra-comparison/r01-solo/summary.json) | failed | 3 / 3 | 9 / 10 / 1 | 4,980 | 0.048620 |
| 5 | [r02-fixed](../examples/terra-comparison/r02-fixed/summary.json) | failed | 6 / 6 | 9 / 10 / 1 | 10,372 | 0.098144 |
| 6 | [r02-adaptive](../examples/terra-comparison/r02-adaptive/summary.json) | completed | 12 / 12 | 9 / 10 / 1 | 16,803 | 0.148576 |
| 7 | [r02-independent](../examples/terra-comparison/r02-independent/summary.json) | completed | 12 / 12 | 8 / 10 / 2 | 14,409 | 0.126788 |
| 8 | [r02-solo](../examples/terra-comparison/r02-solo/summary.json) | completed | 12 / 12 | 8 / 10 / 2 | 17,886 | 0.169622 |
| 9 | [r03-independent](../examples/terra-comparison/r03-independent/summary.json) | completed | 12 / 12 | 9 / 10 / 1 | 17,686 | 0.166112 |
| 10 | [r03-solo](../examples/terra-comparison/r03-solo/summary.json) | interrupted | 10 / 9 | 9 / 10 / 1 | 16,840† | 0.168140† |
| 11 | r03-adaptive | unstarted | — | — | — | — |
| 12 | r03-fixed | unstarted | — | — | — | — |
| 13 | r04-solo | unstarted | — | — | — | — |
| 14 | r04-adaptive | unstarted | — | — | — | — |
| 15 | r04-fixed | unstarted | — | — | — | — |
| 16 | r04-independent | unstarted | — | — | — | — |
| 17 | r05-fixed | unstarted | — | — | — | — |
| 18 | r05-solo | unstarted | — | — | — | — |
| 19 | r05-independent | unstarted | — | — | — | — |
| 20 | r05-adaptive | unstarted | — | — | — | — |

The first two repetition blocks contain an attempt in every condition, with
unequal completed decisions because of failures. In block three, independent
completed and solo was interrupted; fixed and adaptive never started. Blocks
four and five never started. There was no transfer of unused allowances,
completion of selected partial blocks, or substitution of runs. The
[per-run CSV](../examples/terra-comparison/report/runs.csv) preserves additional
fields, including timing, candidate duplication, per-agent allocation and
accounting completeness.

## Failures, validation and call distribution

The first fixed run's tenth response was classified `invalid_action`, with
known usage, and ended that run. The first adaptive run, first solo run and
second fixed run each ended after a candidate failed the arithmetic-progression
validator. The adaptive and fixed failures also included invalid
candidate-bearing message claims, rejected before delivery. These three invalid
candidates plus two rejected message claims explain the runtime's five
`invalid_claims`; they are not five independent invalid candidates.

In `r03-solo`, the tenth attempt ended as `transport_unknown`, with no input,
output or cost telemetry. The saved category does not identify a definite
provider cause or establish that the configured timeout caused the failure.
The campaign stopped globally and retained the reservation. Its nine earlier
valid candidates remain available, including a best size of nine and gap one.
The unresolved ledger identity is
`1338ab4b-a025-464e-94b2-c59a69527188/task-9/attempt-0`; no provider request ID
was returned. Its observation was recorded at 23:32:03.563 UTC and the unknown
outcome at 23:42:48.132 UTC on 2026-09-09. These timestamps locate the saved
records for later reconciliation; they do not establish active request latency.

Across the campaign, 94 attempts had known provider usage. There were 93
completed decisions with verification events, of which **90 candidates were
valid and three invalid**; one known-usage response had no accepted action.
The remaining attempt had unknown usage. The 74 duplicate valid submissions
are counted within runs. No call produced a verified optimal candidate, so both
time-to-optimal-candidate and time-to-verified-optimality remain undefined.

| Run | Calls by agent ID 0, 1, 2, 3 | Invalid candidate events | Rejected candidate message claims | Duplicate valid candidates | Worker seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| r01-independent | 3, 3, 3, 3 | 0 | 0 | 9 | 286.365 |
| r01-fixed | 3, 3, 2, 2 | 0 | 0 | 7 | 239.543 |
| r01-adaptive | 2, 2, 1, 1 | 1 | 1 | 4 | 180.049 |
| r01-solo | 3 | 1 | 0 | 1 | 58.205 |
| r02-fixed | 2, 2, 1, 1 | 1 | 1 | 3 | 114.864 |
| r02-adaptive | 3, 3, 3, 3 | 0 | 0 | 10 | 176.863 |
| r02-independent | 3, 3, 3, 3 | 0 | 0 | 11 | 148.977 |
| r02-solo | 12 | 0 | 0 | 11 | 199.924 |
| r03-independent | 3, 3, 3, 3 | 0 | 0 | 10 | 201.463 |
| r03-solo | 10 | 0 | 0 | 8 | 320.943 |

Four-agent runs dispatched in agent-ID order. The partial rounds therefore gave
earlier IDs more calls; agent 0 was the coordinator in fixed and adaptive. Solo
rows have only agent 0. Worker durations are recorded monotonic measurements;
wall-clock timestamps are preserved separately. In the interrupted run those
clocks advanced by different amounts, so its wall-clock gap should not be
interpreted as measured active API latency.

## Usage and conventional solver baseline

| Accounting quantity | Tokens | USD |
| --- | ---: | ---: |
| Known provider usage and calculated cost | 156,639 | 1.499658 |
| Reservation retained for unknown attempt | 28,075 | 0.3076875 |
| Committed for admission: known plus reserved | 184,714 | 1.8073455 |
| Authorized whole-stage ceiling | 2,000,000 | 20.0000000 |

The reservation is conservative admission accounting, not observed consumption
or a bill. The known token subtotal consists of 38,001 input and 118,638 output
tokens. The 112,695 reported reasoning tokens are already included in output;
cache reads and writes were both reported as zero on the 94 known attempts.
Every known returned model and tier matched the frozen configuration.

The [campaign ledger](../examples/terra-comparison/campaign-ledger.json) includes
all 95 attempt reservations and outcomes. Its sum of historical reservation
estimates is larger than the spending ceiling because each settled request
releases its headroom; that historical sum is not cumulative spend or the
current commitment. No per-run or aggregate overage was recorded. The unknown
attempt could have consumed resources, so the observed subtotal is not a
complete usage total or a reconciled billing charge.

The deterministic branch-and-bound evaluator established U=10 for every
attempted run in 4.89–9.53 milliseconds, with an 8.47-millisecond median. A
separate enumeration in the independent audit found 96,847 valid subsets and
exactly two maximum sets of size ten. This tiny problem is easy for the
conventional solver. The experiment concerns model coordination under the
chosen observations and budgets; it offers no evidence that a swarm outperforms
an appropriate conventional algorithm.

## Communication and the public trace

| Condition | Delivered messages | Message bytes | Policy-reported uses | Coordinator calls | Coordinator tokens | Coordinator calculated USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Solo | 0 | 0 | 0 | 0 | 0 | 0 |
| Independent | 0 | 0 | 0 | 0 | 0 | 0 |
| Fixed | 11 | 3,092 | 7 | 5 | 4,557 | 0.026134 |
| Adaptive | 16 | 3,764 | 13 | 5 | 4,662 | 0.028404 |

All 27 accepted messages were delivered. One attempted independent-worker
message was rejected because that condition forbade sharing; it delivered no
peer content. The twenty recorded uses are model-reported references to events
actually present in the receiving observations. Coordinator usage totals 9,219
tokens and USD 0.054538, about 3.64% of the known campaign cost. It is a subset
of the totals above. Peer-message content carried in searcher inputs is also
charged, but the logs cannot attribute an exact causal cost to that content.

The [annotated public trace](../examples/terra-comparison/report/trace-annotations.md)
uses the frozen selection rule: the earliest scheduled adaptive run with a
delivered message, its first delivery, the receiver's next observation containing
it, and a valid candidate in that same decision task. In `r01-adaptive`, event 9
delivered the coordinator's size-eight baseline to agent 1. Event 13 included it
in that searcher's observation; event 16 recorded reported use. Event 18
verified the same size-eight candidate, leaving L unchanged at eight. This is
visible provenance and temporal order, not evidence that the message caused
an improvement. No private reasoning text was collected.

## Quality versus recorded resource use

![Verified worker quality versus cumulative known provider tokens](../examples/terra-comparison/report/quality-vs-tokens.png)

![Verified worker quality versus cumulative calculated cost](../examples/terra-comparison/report/quality-vs-cost.png)

Panels share resource-axis scales. Curves stop at their actual endpoints;
completed and failed/interrupted endpoints have different markers. The
interrupted solo endpoint shows only its known subtotal and is labeled
incomplete. Its reserved headroom is not plotted as consumed resources.
Unstarted runs have no curves. The underlying
[curve data](../examples/terra-comparison/report/curves.json) retain verification
event IDs and accounting completeness.

## Evidence checks and limits

All ten started traces passed [replay verification](../examples/terra-comparison/report/replay-verification.json).
The [independent local audit](../examples/terra-comparison/report/independent-audit-local.json)
passed 3,831 checks against public artifacts, the raw SQLite ledger and the
local manifest receipt. The [public-artifact audit](../examples/terra-comparison/report/independent-audit-public.json)
passed 3,802 checks without the unpublished SQLite files or local receipt.
The audit separately records 93 candidate verifications, 90 valid candidates
and three invalid candidates.

The [public evidence package](../examples/terra-comparison/README.md) preserves
all twenty planned rows, raw public traces, ledger exports, analysis and charts.
Raw JSON and JSONL bytes match the local campaign; CSV line endings are
normalized to LF with unchanged parsed cells. A checksum manifest covers the
published package. Charts and this report use saved evidence only, with no
additional inference.

This is a halted descriptive case study on one calibrated instance and one
model setting. Different role composition confounds independent-versus-coordinated
comparisons; fixed-versus-adaptive shares the roster but has only two attempted
runs each, all fixed runs failing early. Missing blocks, unequal actual
resources and early failures prevent a reliable ranking. The reproducible
finding is that none of the attempted runs solved the task, and the accounting
system preserved uncertainty and stopped as specified. The frozen protocol
remains unchanged. Any later continuation requires fresh authorization and a
disclosed amendment; deleting a claim or using another output directory must
not reset this authorization.
