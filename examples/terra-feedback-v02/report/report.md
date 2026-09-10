# Solo feedback v0.2: descriptive results

Campaign status: **halted**. Behavioral qualification: **unmet**.

All six planned rows are retained. These observations do not establish causation or a swarm advantage.

| Block | Arm | Status | Calls / 12 | Decisions | Unique valid | Valid duplicates | Invalid math | L | Gap | Known calculated USD |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | history_feedback | failed | 9 | 8 | 1 | 7 | 0 | 8 | 2 | 0.101086 |
| 1 | private_best_only | completed | 12 | 12 | 2 | 8 | 2 | 9 | 1 | 0.278098 |
| 2 | private_best_only | interrupted | 11 | 10 | 2 | 7 | 1 | 9 | 1 | 0.265206 |
| 2 | history_feedback | unstarted | — | — | — | — | — | — | — | — |
| 3 | history_feedback | unstarted | — | — | — | — | — | — | — | — |
| 3 | private_best_only | unstarted | — | — | — | — | — | — | — | — |

| Block | Treatment − baseline unique sets | Baseline status | Treatment status |
| ---: | ---: | --- | --- |
| 1 | -1 | completed | failed |
| 2 | — | interrupted | unstarted |
| 3 | — | unstarted | unstarted |

Known totals: 32 reserved attempts, 65,225 provider-reported tokens, USD 0.644390 calculated cost. Token totals complete: False; calculated cost complete: False.

Retained reservations: 28,077 tokens and USD 0.3076925. Reasoning is included in output, and cache counters are input subsets. Calculated costs are not billing reconciliation.

Replay and report checks: 226 checks, 0 failures. Eligible feedback observations: 7; qualifying improvements: 0.

All eligible exposures, all qualifying events, attempt diagnostics, and arm ranges are retained in analysis.json. Curves stop at measured endpoints and include failed/unknown attempts; no continuation is inferred.
