# Solo feedback v0.2 evidence — halted qualification

This is the public record of the separately authorized six-run solo feedback
qualification conducted on September 10, 2026 UTC. Read the
[results](../../docs/feedback-v02-results.md), preserved
[protocol](../../docs/feedback-v02-protocol.md) and
[execution record](../../docs/feedback-v02-execution.md). Source, protocol,
prices and reporting code were frozen before inference at
[`d86c9c38ba0d8a283423087f13fe148d88253b94`](https://github.com/Entrasoft/agent-swarm/commit/d86c9c38ba0d8a283423087f13fe148d88253b94).

The campaign halted after **32 attempted calls**: one run completed, one failed
on the local action protocol, one was interrupted by a transport timeout with
unknown usage, and three never started. The feedback qualification criterion
was **unmet**. Seven dispatched treatment observations contained its own earlier
repeated attempts; none was followed by an improvement. The sole treatment run
remained at verified size eight; both observed baselines reached nine. None
reached the independently established optimum of ten. One observed pair, with
unequal completion, cannot establish comparative effectiveness.

Known usage is **65,225 tokens and USD 0.644390 calculated cost**. The unknown
request retains **28,077 tokens and USD 0.3076925** in reservations, bringing
commitments to 93,302 tokens and USD 0.9520825. A reservation is not a measured
charge. Total usage and calculated cost remain unknown; billing is unreconciled.
The separate ceilings were 72 calls, 600,000 tokens and USD 6, with zero retries.
No replacement calls were made. This one-use authorization remains claimed;
resolving usage does not authorize resuming or replacing the campaign.

## Contents

- [manifest.json](manifest.json): frozen document text, source hashes, price
  snapshot, all six identities, configurations, order and allowances.
- [feedback-campaign.json](feedback-campaign.json): all six planned outcome rows,
  including failed, interrupted and unstarted runs.
- [campaign-ledger.json](campaign-ledger.json),
  [campaign-ledger.csv](campaign-ledger.csv) and
  [campaign-summary.json](campaign-summary.json): all attempt accounting and
  retained uncertainty.
- `r01-history_feedback`, `r01-private_best_only` and `r02-private_best_only`:
  the three started runs, each with configuration, public event trace, summary
  and usage exports. Unstarted runs have no invented run directories.
- [report/analysis.json](report/analysis.json), [report/runs.csv](report/runs.csv)
  and [report/report.md](report/report.md): deterministic descriptive analysis,
  all six rows, paired availability and feedback exposure checks.
- [report/curves.json](report/curves.json) and figures against
  [calls](report/quality-vs-calls.png), [tokens](report/quality-vs-tokens.png) and
  [calculated cost](report/quality-vs-cost.png): finite observed trajectories,
  missing runs and labeled unknown subtotals. Circles mark completed endpoints;
  crosses mark failures or interruptions. Quality axes start near eight.
- [report/independent-audit.json](report/independent-audit.json): 1,065 passing
  independent checks of mathematics, accounting, source identity and linkage.
  This checks public consistency, not log authenticity or reconciled billing.
- [report/replay-verification.json](report/replay-verification.json): all three
  started traces pass replay; finalized trace completeness is separate from
  completing every scheduled decision. The report additionally passes 226 checks.
- [SHA256SUMS](SHA256SUMS): hashes of every package file except itself.

The treatment's final action failed a local protocol check whose exact field
was not retained. The unknown request has a persisted client correlation ID
but no response headers, server request ID or usage. Its wall-clock timestamps
span 3,054.334 seconds while monotonic counters advance 120.036 seconds. These
records do not establish the cause of that disagreement, provider latency or
whether the request was billed. See the results report for trace identifiers.

## Preservation and reproduction

The **23 raw exports** contain **19 byte-identical JSON/JSONL files** and **four
CSV files normalized from CRLF to LF**, with parsed cells unchanged. They occupy
**1,060,584 bytes** after normalization. The nine report files and this README
are derived artifacts. Credential files, authorization headers, private
reasoning text, SQLite databases and the local one-use claim are not published.
No runtime, protocol, price or reporting logic was amended after inference.

From the repository root, these commands read saved evidence without model calls:

```sh
python3 -m swarm_lab replay examples/terra-feedback-v02/r01-history_feedback --verify
python3 -m swarm_lab replay examples/terra-feedback-v02/r01-private_best_only --verify
python3 -m swarm_lab replay examples/terra-feedback-v02/r02-private_best_only --verify
python3 scripts/audit_feedback_comparison.py examples/terra-feedback-v02
python3 scripts/report_feedback_comparison.py --campaign examples/terra-feedback-v02 \
  --out runs/terra-feedback-v02-reproduced
```

The audit requires runtime source hashes matching the manifest. From a later
checkout, pass `--source-root /path/to/frozen-checkout` pointing to the recorded
source commit. The independent audit uses only the Python standard library and
does not import the runtime. For exact report behavior, also use that frozen
checkout. Add `--plots` with Matplotlib installed to recreate figures; rendering
library versions can change PNG bytes without changing measured coordinates.
The exporter writes to a separate output directory outside this evidence package.

Historical prepare/execute commands document the consumed authorization. They
are not permission for further paid work. The next scientific step is an
offline review of the unsuccessful search loop before a new paid proposal.
