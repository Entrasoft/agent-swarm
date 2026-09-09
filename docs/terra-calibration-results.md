# Terra difficulty calibration — 2026-09-09

The authorized calibration completed **six live calls**, using **10,395 provider-reported tokens** and **USD 0.102580 calculated API cost** (about 10.3 cents). There were no retries, failed calls, invalid candidates, unknown usage, retained reservations or budget overshoots. Billing remains unreconciled.

The [precommitted selection rule](calibration-protocol.md#frozen-difficulty-selection-rule) selects **m=24** for a proposed comparison. Terra returned an eight-member set on all three decisions there, while independent exact evaluation established an optimum of ten. At m=18, the first decision already reached the optimum of eight. This is difficulty calibration from one trace per size, not a swarm result or a reliable estimate of success probability.

## Settings and provenance

Campaign: `terra-calibration-fc7a8aa8-5ec4-4c8a-ad2d-f06242d255bf`. Authorization: `terra-calibration-v1-2026-09-09`, at most six calls, USD 2 and 100,000 tokens combined, zero retries. The call allowance is exhausted even though USD 1.897420 and 89,605 tokens remain unused under those ceilings. No comparative inference was performed.

Source revision `c0c3fef5b55b248afb6bbb48c228af5776acbc9b` and the calibration protocol were committed before generation. The [manifest](../examples/terra-calibration/manifest.json) preserves that protocol, module hashes, both configurations, the price snapshot and conservative reservation estimates. Both runtime configurations recorded a clean working tree. Later reporting edits do not replace this executed source revision.

The two runs used `gpt-5.6-terra`, medium reasoning effort, default service tier, one solo searcher, three sequential decisions, 25,000 maximum output tokens per request including reasoning, and a 120-second timeout. Each size started with an empty private incumbent and no peers or messages. All six responses identified the requested model and tier. The evaluator ran after each worker phase; its output was absent from both workers' observations.

## Verified outcomes

| Size | First decision size | Final best size L | Exact optimum U | Gap | Completed calls | Duplicate candidates | Worker seconds | Exact evaluator ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| m=18 | 8 | 8 | 8 | 0 | 3 | 2 | 50.11 | 1.11 |
| m=24 | 8 | 8 | 10 | 2 | 3 | 2 | 87.47 | 9.32 |

Every decision returned `{1, 2, 4, 5, 10, 11, 13, 14}`. It is valid for both universes. For m=24, the independent evaluator found the valid ten-member set `{1, 2, 5, 7, 11, 16, 18, 19, 23, 24}` and established that no larger set exists. That evaluator candidate is not credited to Terra.

The m=18 stopping reason was `solved`; m=24 stopped at `step_limit`. No worker improvement occurred after either first decision. The recorded tokens therefore show additional model expenditure without an improvement in candidate size in these particular traces. They do not establish a general relationship between reasoning effort and quality. The much faster deterministic evaluator remains an essential baseline; all timings are single measurements on this host.

## Provider usage and calculated cost

| Size / call | Input | Output | Reasoning within output | Total tokens | Calculated USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| m=18 / 1 | 354 | 958 | 920 | 1,312 | 0.012204 |
| m=18 / 2 | 377 | 376 | 338 | 753 | 0.005266 |
| m=18 / 3 | 377 | 1,467 | 1,429 | 1,844 | 0.018358 |
| **m=18 subtotal** | **1,108** | **2,801** | **2,687** | **3,909** | **0.035828** |
| m=24 / 1 | 354 | 913 | 875 | 1,267 | 0.011664 |
| m=24 / 2 | 377 | 3,739 | 3,701 | 4,116 | 0.045622 |
| m=24 / 3 | 377 | 726 | 688 | 1,103 | 0.009466 |
| **m=24 subtotal** | **1,108** | **5,378** | **5,264** | **6,486** | **0.066752** |
| **Combined** | **2,216** | **8,179** | **7,951** | **10,395** | **0.102580** |

All calls explicitly reported zero cache reads and writes. Using the [frozen price snapshot](../examples/terra-calibration/manifest.json), calculated cost is `(2,216 × USD 2 + 8,179 × USD 12) / 1,000,000 = USD 0.102580`. Reasoning is already included in output and is not added twice. The [combined ledger](../examples/terra-calibration/campaign-ledger.json) includes each request once and agrees with both per-run ledgers. `actual_model_cost` remains null because no billing reconciliation has occurred.

The campaign admission ledger enforced both per-run limits and the shared six-call, USD 2 and 100,000-token limits in each reservation transaction. Earlier settlements released unused headroom, allowing all six calls to fit. The persistent authorization claim prevents another output directory from repeating this stage. No generation retry or restart was used.

## Evidence and verification

The [public evidence directory](../examples/terra-calibration/) contains the manifest, campaign report and combined ledgers, plus each run's configuration, 24-event trace, summary and JSON/CSV ledgers. JSON and JSONL files are byte-for-byte copies. Only CSV line endings were normalized from CRLF to LF under repository rules. `SHA256SUMS` describes the published files. SQLite stores and execution claims remain in the ignored local run directories. No credential values or private reasoning text were collected in these artifacts.

Replay without an API key or generation:

```sh
python3 -m swarm_lab replay examples/terra-calibration/m18-solo --verify
python3 -m swarm_lab replay examples/terra-calibration/m24-solo --verify
```

Both 24-event traces passed independent replay checks. The implementation passed 125 offline tests, including shared token/cost/call ceilings, concurrent reservations, failed and ambiguous requests, unexpected returned model/tier, preservation of failure stopping reasons, and repeat execution across output directories. The PR test matrix passed on Python 3.11, 3.12 and 3.13 before inference.

A separate audit recomputed the ledger from raw response usage and independently enumerated all valid subsets without importing the repository oracle: 9,526 valid subsets at m=18 with maximum size 8, and 96,847 at m=24 with maximum size 10. It confirmed every candidate, both replay results, all source/protocol hashes and that the source commit preceded preparation and first admission.

## Consequence for the article

m=24 supplies observed room for improvement under the frozen rule. It does not show that adding agents or messages will close the gap. The [proposed four-condition comparison](live-comparison-proposal.md) includes solo search, independent searchers, fixed coordination and adaptive coordination, with explicit whole-team budgets and preserved failures. Keep these calibration traces out of the comparative sample. The next stage needs its own finalized protocol, executable runner and paid authorization; this completed stage grants none of those calls.
