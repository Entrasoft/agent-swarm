# Experiment protocol v1 — offline engineering campaign

Prepared 2026-09-09. Freeze this document in Git before running or examining the
comparative campaign. Mathematical correctness checks and deterministic solver
profiling preceded this protocol; neither was a team-condition comparison.
Record any subsequent change as an amendment with its reason and whether
comparative outcomes had already been inspected.

The question is whether communication improves verified search quality enough
to justify its overhead. This first campaign tests algorithmic workers and the
measurement machinery. It cannot establish an advantage for LLM collaboration.

## Task and hidden evaluation

For each integer m, find a largest subset of {1,...,m} containing no distinct
a < b < c with a+c=2b. Only arithmetic progressions are forbidden. The trusted
validator checks types, membership, duplicates and progression triples.

Workers receive m, their role, private incumbent, permitted mailbox, peer IDs,
condition and task ID. The exact solver and global incumbent are absent from
worker observations. The deterministic branch-and-bound oracle runs after the
worker phase. Its optimum or sound timeout upper bound U is compared against the
best worker candidate's independently verified size L. The evaluator's candidate
does not improve the workers' reported L. A run is solved only if U=L; otherwise
retain the gap and stopping reason. An oracle timeout is retained, not dropped.

## Frozen matrix

Use m in {10,12,18,24} and seeds {0,1,2}. For every (m,seed), run all seven rows:

| Condition | N | Decision roles | Communication |
| --- | ---: | --- | --- |
| solo | 1 | 1 searcher | None |
| independent | 4 | 4 searchers | None |
| independent | 10 | 10 searchers | None |
| fixed | 4 | 1 coordinator + 3 searchers | Searchers to coordinator; coordinator rotates through searchers |
| fixed | 10 | 1 coordinator + 9 searchers | Same fixed routing |
| adaptive | 4 | 1 coordinator + 3 searchers | Seeded heuristics choose recipients and timing |
| adaptive | 10 | 1 coordinator + 9 searchers | Same adaptive policy |

This yields 84 algorithmic runs. N includes the coordinator. The deterministic
scheduler and verifier are outside N. Each decision role runs the same greedy
candidate construction and perturbation code; role affects routing. Distinct
private contexts are not a claim of statistically independent reasoning.

Every run uses 48 total decision opportunities across the entire team, including
the coordinator; round-robin allocation; concurrency ceiling 4; simulated token
ceiling 100,000; simulated currency ceiling USD 1.00; output reservation 512
fixture tokens; at most one automatic retry; mailbox limit 16; message limit
4,096 bytes; context limit 16,384 bytes; and oracle timeout 5 seconds. Retain a
run that hits a ceiling early. These are matched decision ceilings, not matched
real inference tokens, dollars, CPU time or wall time. The final partial round
may give the earliest agent IDs one extra call; report per-agent counts.

The runtime bounds concurrent tasks and advances in rounds. Within a round,
concurrency-limited batches can observe messages committed by earlier batches.
Offline scheduling is repeatable for fixed code and configuration. Record the
scheduling description and concurrency limit with results. A future live run
must also record completion order because provider latency changes message
availability. Do not compare different concurrency settings as if only routing
had changed.

Include the independent deterministic-solver result and measured solve time for
each m. The hidden evaluator already executes the same solver per run; report
its timings separately from worker search and storage costs. Initial profiling
found these instances fast for the exact solver. Larger or different tasks
require an explicitly documented later protocol; do not silently replace them
after a disappointing result.

## Outcomes and accounting

Primary outcome is final verified gap U-L by condition and m. Also report solved
counts with the number attempted, final L, and all stopping reasons. Retain failed
and interrupted runs in the attempt denominator and report absent quality values
as missing, not zero. If a campaign runner fails before producing a full summary,
preserve the directory and record the failed attempt explicitly.

Secondary outcomes are time to the first candidate later confirmed optimal,
time to verified optimality including hidden evaluation, worker elapsed time,
validator time, oracle time, completed decisions, invalid candidate/claim count,
duplicate candidate submissions, peer-message count and bytes, and reported
artifact reuse. Message delivery, inclusion in an observation, policy-reported
use and causal benefit are separate quantities. Reuse is provenance evidence.

Report simulated input/output tokens, cache/reasoning subsets when available,
calculated fixture cost, reservations and unresolved attempts. Offline values
are fixture accounting: actual model calls and marginal API spend are zero.
Local CPU, storage and elapsed time remain real resource use. Fixture rates are
versioned as offline-v1, dated 2026-09-09; they are not market prices. Context
size divided by four is only an estimate. No offline token-normalized result is
evidence of LLM efficiency.

For a later live campaign, include every provider attempt once, including retries,
coordination and unsuccessful runs. Report estimated, provider-observed and
billing-reconciled status separately. Missing usage remains unknown with its
reservation retained. Coordination share refers to coordinator call purpose;
peer content included in searcher calls is not exactly attributable unless the
provider exposes that breakdown. Local message delivery adds no provider charge.

Define progress per million tokens as verified improvement divided by total
campaign input-plus-output tokens, multiplied by one million. Define cost per
verified solution as total campaign cost, including failures, divided by solved
run count. With no successes it is undefined; with unpriced or unresolved spend,
label the result incomplete. Cache and reasoning subsets are not added to their
inclusive parent totals. Time-to-optimality is undefined for unsolved runs;
report their censoring or failure reasons alongside successes. Quality-versus-
cost curves must say whether the cost axis is simulated or observed.

## Analysis and limitations

Publish per-seed observations and condition-level ranges/medians by m. With three
seeds, avoid significance claims or broad generalization. Pair descriptive
comparisons by m and seed, while recognizing that message traffic changes RNG
consumption and the realized search path. Compare fixed with adaptive at the
same N to control team composition. This comparison changes programmed recipient
and timing choices together; it does not isolate recipient choice alone.

The independent condition must use outcome-blind scheduling and must not expose
shared incumbents, artifacts, summaries or coordinator messages to workers.
Infrastructure telemetry belongs to the experimenter. Do not infer cooperation
from a denser graph or a larger message count. Do not describe hand-written
adaptive rules as emergent organization. The exploratory allocator is excluded
from this primary matrix; evaluate it later as a separate amended comparison.

Archive config, code revision and dirty-tree marker, seed, role roster, price
snapshot, events, artifact versions, per-attempt ledger and summary. Record
runtime/platform details with the campaign. Do not tune after inspecting the
matrix and present the new outcomes as this preregistered comparison.

## Message intervention: proposed extension, not a current causal test

The current withholding option suppresses one numbered message and repeated
identical content. It is a diagnostic filter. It is not a checkpoint/fork
experiment: it does not restore agent state, replay exact RNG states, suppress
all semantic descendants or prevent paraphrased information from leaking.

A sound extension must checkpoint every private state, mailbox, pending task,
RNG state, artifact visibility and remaining token/currency reservation immediately
before a selected delivery. Fork that checkpoint into delivery and withholding
branches, use comparable remaining budgets, and keep the selected information
out of alternate messages, artifacts and summaries. Decide beforehand whether
later independent rediscovery is permitted and distinguish it from leakage.
Repeat paired continuations over instances and seeds, include unsuccessful
branches and compare verified outcomes. Until this exists, traces can suggest
influence but cannot establish the benefit of a particular message.

## Paid experiments

No paid matrix is authorized by this offline protocol. A next live pilot requires
an explicitly selected available model, same-day verified official price snapshot,
supported secret configuration, and a concrete total token/currency ceiling
approved by the owner. Do not infer permission to spend from permission to create
or merge repository changes. Predeclare its conditions and stopping rules before
calls; never substitute scripted output for failed live inference.

## Amendment A — scheduling clarification after initial outcome inspection

Recorded 2026-09-09 after the first 84-run campaign was inspected. The original
protocol snapshot is preserved in that campaign's `matrix.json`; the preceding
sections remain unchanged so the discrepancy is inspectable.

The implementation used serial execution of algorithmic decisions, with immediate
message delivery before the next agent's observation, even when concurrency was
set to 4. Its offline decision path contained no suspension point. Consequently,
the earlier description of concurrency-limited observation batches was incorrect
for offline mode. Nominal rounds bound and allocate tasks, but do not provide an
observation snapshot barrier. The concurrency setting gates actual overlapping
live provider calls; live completion order may change information availability.

The inspected initial campaign solved 63 of 84 runs: all m=10,12,18 runs reached
the oracle optimum, while all m=24 runs ended with gap 1. Every condition showed
that same solved/gap pattern. This amendment discloses the implementation's
actual scheduling; it does not alter the candidate search or message-routing
rules in response to those outcomes.

A final validation rerun after review and reporting fixes will use the same
serial offline semantics and matrix, recording its current code revision and
this amended protocol snapshot. It is a validation rerun after outcome inspection,
not an independent preregistered replication. Preserve both campaign records and
identify which supplies published tables. A future experiment with shared
observation snapshots would require a separate protocol and comparison.
