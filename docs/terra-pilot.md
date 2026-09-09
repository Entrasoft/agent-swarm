# Terra pilot — 2026-09-09

Three authorized calls to `gpt-5.6-terra` completed successfully with **2,260 provider-reported tokens** and **USD 0.016160 calculated API cost** (about 1.62 cents). Both totals are below the owner's whole-run ceilings of 100,000 tokens and USD 2. There were no retries, failed calls, unknown usage, or outstanding reservations. Billing has not been reconciled; `actual_model_cost` remains null by design.

## Settings and provenance

The pilot used one solo searcher, m=12, three sequential decisions, medium reasoning effort, default service tier, a 120-second request timeout, and a maximum of 25,000 output tokens per call, including reasoning. Automatic retries were disabled. These settings were selected before generation; the limits apply across all three calls. Completion exhausts the three-call authorization even though monetary and token headroom remains.

Run ID: `d45624ab-3a70-44b6-9419-782da420e18b`. The run began at 2026-09-09 18:36:50 UTC on clean source revision `eeb79d7f6d33ffbedef9e0344d39d7aa1cdbcec5`. The [frozen configuration](../examples/terra-pilot/config.json) contains module SHA-256 hashes and the price snapshot verified on that date. All returned model identifiers were `gpt-5.6-terra`, with default service tier; the response did not supply a more specific model version.

The [setup instructions](live-provider.md) preserve the command and the macOS CA-bundle setting needed on this host. A preliminary model visibility check generated no output tokens. The three subsequent Responses requests are the paid inference attempts counted here. Credentials and authorization headers are excluded from all recorded artifacts.

## Usage and calculated cost

| Call | Input tokens | Output tokens | Reasoning within output | Total tokens | Calculated USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 354 | 613 | 579 | 967 | 0.008064 |
| 2 | 371 | 398 | 364 | 769 | 0.005518 |
| 3 | 371 | 153 | 119 | 524 | 0.002578 |
| **Total** | **1,096** | **1,164** | **1,062** | **2,260** | **0.016160** |

All responses explicitly reported zero cache-read and cache-write tokens. At the frozen rates of USD 2 per million ordinary input tokens and USD 12 per million output tokens, the calculation is `(1,096 × 2 + 1,164 × 12) / 1,000,000 = 0.016160`. Reasoning tokens are already included in output. The ledger reports 97,740 tokens and USD 1.983840 of unused headroom, with zero overshoot. These values describe this run's budget, not the account's remaining credit balance.

The sum of pre-dispatch reservations was 84,171 estimated tokens and USD 0.9229275. Those conservative estimates include output headroom and byte-based input allowances; they are not additional usage or charges. Each reservation settled from the corresponding response's usage. The [usage summary](../examples/terra-pilot/usage-summary.json) retains the distinction between calculated cost and unreconciled billing charges.

## Verified result and limits

The first call returned `{1, 2, 4, 5, 10, 11}`. Validation found no three distinct members forming an arithmetic progression. Both later calls returned the same set. The hidden exact evaluator ran only after the worker phase and established an optimum of six, so the final lower and upper bounds both equal six and the gap is zero. The worker saw its own previous candidate but no oracle result. The final stopping reason is `solved`; all three configured decisions had completed before evaluation.

The first optimal candidate was validated at about 14.45 seconds. The run took about 26.2 seconds; the exact evaluator took about 0.095 milliseconds. These are single-run timings on this host. There were two duplicate candidates, no invalid claims, and no inter-agent messages.

This is evidence that the live request, validation, accounting and replay path worked under the selected settings. One tiny solo run does not establish a best model, predict larger-run cost, compare coordination strategies, or show an advantage over deterministic search. Further paid experiments need their own bounded authorization and a disclosed comparison design.

## Preserved evidence and verification

The [public evidence directory](../examples/terra-pilot/) contains byte-for-byte copies of the original JSON/JSONL configuration, event log, summary, ledger and usage summary. The CSV ledger differs only in line endings, normalized from CRLF to LF under the repository rules. SHA-256 checksums describe the published files. SQLite stores remain in the local run directory. Only public candidate data and usage metadata are retained; private reasoning text is not collected.

Verify the preserved trace locally without an API key or generation request:

```sh
python3 -m swarm_lab replay examples/terra-pilot --verify
```

Replay verified all 24 events, the completed run, and equal bounds of six. A separate audit recomputed usage and price arithmetic and independently checked the candidate and tiny-instance optimum. This reporting change does not rerun inference or modify the executed source revision.
