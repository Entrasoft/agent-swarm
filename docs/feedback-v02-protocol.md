# v0.2 solo feedback qualification protocol

**Status: proposed; offline preparation approved, paid inference not authorized.**
This protocol specifies a new study. It does not resume the halted v1 comparison,
reuse an earlier authorization or release an unresolved reservation. Commit the
protocol, implementation and complete proposed schedule before requesting approval
for paid execution. The historical price snapshot is a planning reference; a new
dated snapshot must be verified and frozen before live dispatch. Any later
amendment must identify whether new study outcomes had already been inspected.

## Question and motivation

Can a solo worker use a small record of its own attempts and trusted validation
feedback to search beyond repeated candidates? The next scientific step depends
on having a search loop that can receive and act on feedback. This qualification
study checks that loop before a later experiment on the value of peer messages.

The [halted comparison](live-comparison-results.md) recorded 74 duplicate
submissions among 90 valid candidates. The completed solo run submitted one
unique valid candidate twelve times, ending at size eight against a hidden exact
optimum of ten. These observations motivate this intervention; they do not prove
that missing history caused repetition. The earlier runtime supplied a private
best and transient messages, without a record of unsuccessful attempts or an
explicit validation response. Under the v1 protocol an invalid mathematical
candidate ended the run, so that protocol could not measure subsequent repair.

The intervention combines **attempt memory and validator feedback**. This small
study cannot distinguish their individual effects. It also changes the handling
of invalid mathematics relative to v1. Both new arms receive that same handling;
v1 runs are historical context and are not additional control observations.

## Arms and fixed settings

| Setting | Baseline: `private_best_only` | Treatment: `history_feedback` |
| --- | --- | --- |
| Worker roster | One solo searcher | One solo searcher |
| Persistent worker information | Own verified private best | Own verified private best plus bounded own-attempt history and validation feedback |
| History bound | No attempt history in observations | At most eight most recent entries, further trimmed to fit the byte cap |
| Peer messages or other workers' results | None | None |
| Invalid mathematical candidate | Uses the scheduled decision; continue if the next request is admissible | Uses the scheduled decision; continue if the next request is admissible |
| Maximum decision calls per run | 12 | 12 |
| Per-run ceilings | 100,000 tokens and USD 1 | 100,000 tokens and USD 1 |

Use the existing frozen system prompt and strict action schema in both arms.
Keep all settings equal except the declared observation history. Both runs use
`decision_protocol="feedback-v0.2"`; only `memory_mode` changes. The treatment
adds the `attempt_history` observation field. Do not give one arm extra search
heuristics or change its system instructions. Use `m=24`, `gpt-5.6-terra`, medium
reasoning, the default service tier, a 25,000-token maximum output allowance including reasoning,
a 120-second request timeout, concurrency one and zero retries. The complete
observation has a 16,384-byte cap. No oracle, filesystem, network, arbitrary-code
or auxiliary model tools are available to the worker.

All runs begin with an empty private best and empty history. There is no transfer
of calibration candidates, v1 candidates, other runs' attempts, shared incumbents
or evaluator findings. A new request receives only its constructed observation;
there is no hidden conversation chain. The evaluator runs after the worker
phase. Its optimum, witness and bounds never appear in worker observations, and
recognizing a candidate as optimal does not stop the scheduled worker phase.

### Feedback contract

Each treatment entry describes one of that worker's earlier candidate
submissions, its one-based scheduled `decision`, and the deterministic
validator's result. Fields are `candidate`, `valid`, `reason`, `forbidden_triple`
and `verification_event_id`, with `candidate_omitted` when applicable. Valid
candidates are normalized by sorting their members. The observation builder
must never expose another worker's candidate or an evaluator artifact. Feedback
contains validity and a validator-generated reason. An arithmetic-progression
failure includes the first violating triple found by the validator's deterministic
ascending traversal, with `a < b < c` and `a + c = 2*b`. Range and duplicate
member failures receive their corresponding reason and no invented triple.
A valid candidate receives a valid result; it is not labeled globally optimal.

History is a bounded record, not an extra answer generator. If a submitted
candidate's JSON exceeds 1,024 bytes, store `candidate=null` and
`candidate_omitted=true` in its history entry while retaining the validator
result and any mathematical witness. Do not supply an abbreviated candidate as
though it were the original. Retain at most eight entries, discard the oldest
first, then discard further oldest whole entries if needed to keep the serialized
observation within 16,384 bytes. Do not replace dropped entries with a
model-generated summary. An irreducible observation overflow is an infrastructure
failure. Log enough provenance to reconstruct the entries and omissions
actually visible on each call. The baseline receives no equivalent attempt
records through event IDs, scheduling, feedback messages or shared artifacts.

Enforce the action contract locally: the action has exactly the schema's keys,
`candidate` is a list of integers excluding booleans, `message` is null and
`used_event_ids` is an empty list in this solo protocol. A non-null message or
invented used event is a protocol failure even when the provider schema permits
that shape in other experiments. Schema-invalid actions stop the run rather
than reaching mathematical repair. Range, duplicate-member and arithmetic-
progression failures of a structurally valid candidate consume the decision and
can receive treatment feedback. The validator's type checks remain necessary
for offline tests and defense in depth; they do not mean such malformed actions
pass the live action contract.

## Proposed matrix and schedule

Use three paired blocks, with both arms in each block: **six planned runs and at
most 72 attempted calls**. Blocks organize nearby executions; they are not
identical provider draws or matched latent states. Runtime seeds 0, 1 and 2 label
the three blocks and do not guarantee reproducible provider sampling.

Generate the order with Python `random.Random(20260910)`, shuffling a fresh list
`["private_best_only", "history_feedback"]` once for each block:

| Block | Runtime seed | First run | Second run |
| ---: | ---: | --- | --- |
| 1 | 0 | `history_feedback` | `private_best_only` |
| 2 | 1 | `private_best_only` | `history_feedback` |
| 3 | 2 | `history_feedback` | `private_best_only` |

Freeze all six run identities, their allowances, their exact configurations and
this order before inference. Execute one complete scheduled run at a time. Do
not reorder runs in response to results, transfer underspend, replace failures,
add calls to finish a promising candidate or repeat the matrix in another output
directory. No optional rerun is authorized by this protocol.

## Admission, failures and accounting

The proposed campaign ceilings are **72 attempted calls, 600,000 total tokens
and USD 6**, with six equal per-run allowances of twelve calls, 100,000 tokens
and USD 1. Every paid generation attempt belongs to both ceilings. There are no
auxiliary model grading or summarization calls. These are maxima, not spending
targets or guarantees that twelve decisions can complete in every run.

Before dispatch, atomically reserve conservative input and maximum-output
headroom against the run and campaign. If the next reservation does not fit,
stop the run without dispatch and retain its budget-stop row. Do not reduce
output headroom after inspecting results. Reasoning tokens are already part of
output; cache reads and writes are input subsets and must not be added twice.
History-bearing input is charged to the treatment's same allowance. Equal
ceilings do not imply equal actual spending or equal amounts of task text.

An action that satisfies the schema but submits invalid mathematics consumes
one decision and is logged as invalid. Neither arm gains a replacement call;
both can proceed at the next scheduled decision. The treatment can then receive
that attempt's feedback if retained by the fixed history rule. Valid duplicate
candidates likewise consume a decision. They are not transport retries.

A known-usage provider, refusal, incomplete-response, schema or routing/protocol
failure ends that run without retry. Continue later scheduled runs only while
accounting remains known and admission checks pass. Unknown usage, uncertain
dispatch, an interrupted request, an unexpected returned model or tier, or a
run/campaign overage halts the whole campaign and retains unresolved reservations.
An infrastructure failure that prevents reliable run accounting also halts the
campaign. An unfinished block is retained. Fresh authorization and a disclosed
amendment are required for any continuation; elapsed time or unspent allowance
is not permission to resume.

Record a client correlation ID before dispatch and retain the provider request
ID when available. Record bounded, sanitized diagnostic categories sufficient
to distinguish failures where the response supplies evidence: HTTP/transport
category, response status, refusal or content kind, incomplete reason and action
parsing/schema failure. Missing information remains unknown; a client ID is
not a returned provider receipt or a guarantee that a failed request did not
execute. Do not archive credentials, authorization headers, raw error bodies or
private reasoning. Diagnostic improvements do not retrospectively identify the
cause of the unresolved v1 request.

## Outcomes and analysis fixed before execution

The **primary descriptive outcome** is the number of distinct valid candidate
sets submitted within each run's twelve scheduled decision opportunities.
Normalize a valid candidate by sorting its members and deduplicate across the
whole run, not just the eight-entry history. A valid empty set counts if actually
submitted; the initial empty private state does not. A started run with no valid
candidate has zero unique valid submissions. Unstarted runs have no outcome and
remain explicitly unstarted, rather than receiving an invented score.

Report all six planned rows, including failures, budget stops, interruptions and
unstarted rows. A stopped run's observed count is its result under the fixed
allowances; do not extrapolate to twelve completed calls or analyze only complete
runs. Show completed/attempted decisions beside the planned twelve. For each
block show the treatment-minus-baseline unique-count difference when both runs
started, alongside their stopping reasons; do not impute a missing partner.
Show the three arm-level values and descriptive ranges. This sample does not
support a general effectiveness claim or a significance test chosen after seeing
results.

Secondary outcomes are terminal best verified size `L`, improvement from the
first valid candidate, and the hidden evaluation gap `U-L`; record a missing
worker-quality result when no valid candidate exists. Also report valid
submission count, valid duplicates, invalid mathematical candidates, protocol
failures, visible/dropped history entries, and the number and timing of increases
in the run's verified best. Distinct candidates of equal or smaller size can
raise the primary diversity count without improving the objective; present
quality beside diversity throughout.

Report per-attempt and cumulative input, output, reasoning and cache usage;
calculated cost; retained unknown reservations; worker elapsed time; and evaluator
time separately. Keep failures in resource totals and label incomplete totals.
Do not treat calculated cost as reconciled billing. Plot measured quality against
actual calls, known tokens and known cost without extending terminated traces
as if additional decisions occurred. Show failure endpoints and unknown-usage
markers. Keep the deterministic exact solver as a separate baseline, without
crediting its solution to a model.

For diagnostics, report attempted dispatches with a persisted client ID and
those with returned provider IDs separately; a missing provider ID is not itself
a logging defect. Report whether every failure has a recorded outcome and
whether known usage settles or unknown usage retains its reserve. Offline fault
injection establishes coverage of failure cases the live sample may never hit.

## Qualification and subsequent research

The engineering gate must pass before paid approval: offline tests demonstrate
own-history isolation, deterministic validation witnesses, both-arm continuation
after invalid mathematics, unchanged decision/call ceilings, history count and
byte limits, schema/protocol stopping, diagnostic redaction, and retention plus
global stopping on unknown usage. Replay must reconstruct visible history and
verified results without relying on model assertions.

After the proposed live study, call the feedback loop **operationally qualified**
only if the engineering checks remain satisfied and at least one treatment run
records a strict increase over its earlier verified best after an observation
that actually contained its own prior invalid or repeated candidate attempt.
Report that predeclared event with its exact trace links, the prior best, the
visible qualifying entry and the improved independently validated candidate.
If no qualifying history appears, the behavioral check is unexercised. If it
appears without improvement, the criterion is unmet. Neither outcome authorizes
additional sampling. Preserve adverse results and revise offline before proposing
another paid stage.

This modest criterion establishes an observed recover-and-progress sequence,
not that feedback caused it or that the treatment outperformed the baseline.
The comparative hypothesis is that the combined memory/feedback observation
will yield more distinct valid candidates and useful verified progress under
equal ceilings. The six-run, one-instance study is descriptive qualification;
even a favorable arm difference does not separate memory from feedback or
establish a swarm advantage. Lack of evidence here is not a proof that either
component is ineffective.

Only after reviewing this evidence should a separate proposal test peer-message
value: hold saved worker state, roster, roles, model and allowances fixed while
delivering or withholding a selected message; repeat across held-out checkable
instances and account for communication costs. Those interventions, additional
instances, larger teams and model sweeps are outside this authorization proposal.

## Preservation and approval boundary

The [budget proposal](feedback-v02-budget-proposal.md) supplies the concrete
approval wording. Preparation must not load credentials or contact a model.

```sh
python3 -m swarm_lab.feedback prepare --out runs/feedback-v02-proposal
```

This command writes a proposed manifest with protocol and source hashes, the
six configurations, and the preserved price reference that must be reverified.
It does not create a spending ledger. Prepared configurations have
`allow_live=false`; this preparation module has no execution command.

The future live runner must bind explicit fresh authorization to the committed
protocol, source hashes, price snapshot, six configurations and schedule, and
claim it durably before dispatch. Offline fixtures and simulated accounting must
be labeled and kept separate from future live observations.

Preserve the [v1 protocol](live-comparison-protocol.md),
[v1 results](live-comparison-results.md) and
[public v1 package](../examples/terra-comparison/README.md) as historical evidence.
The v1 unknown reservation remains unresolved independently of this proposal.
Publish all six planned rows, the manifest, public traces, sanitized diagnostics,
ledger exports, replay results and any amendments with the new result. The
article may explain why this study was proposed now, but it must not present its
hypotheses, offline tests or proposed budget as completed live findings.
