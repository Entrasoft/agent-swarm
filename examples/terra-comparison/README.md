# Terra comparison evidence — halted campaign

This is the public record of the authorized m=24 comparison conducted on
2026-09-09. Read the [results report](../../docs/live-comparison-results.md) for
the complete interpretation and [frozen protocol](../../docs/live-comparison-protocol.md)
for the design. The source was committed at
[`4a30a2519491f355c60bcaa19799ab14010e71ab`](https://github.com/Entrasoft/agent-swarm/commit/4a30a2519491f355c60bcaa19799ab14010e71ab)
before inference.

The campaign halted after 95 attempted calls: five runs completed, four failed
with known accounting, one was interrupted with unknown usage, and ten never
started. None of the ten attempted runs reached the verified optimum of ten.
All twenty planned rows remain in the exports; missing quality is not zero.

Known provider usage totals 156,639 tokens and USD 1.499658 calculated cost.
The unknown attempt retains a reservation of 28,075 tokens and USD 0.3076875;
known plus reserved commitment is 184,714 tokens and USD 1.8073455. The actual
usage total and calculated cost are incomplete, and billing is unreconciled.
No retries or replacement calls were made. This package does not authorize
resuming the campaign; resolving usage alone does not authorize more calls.

## Files

- [manifest.json](manifest.json): frozen protocol text, randomized schedule,
  twenty configurations and run identities, source hashes, price snapshot and
  run/campaign allowances.
- [comparison.json](comparison.json): all twenty rows, final statuses, recorded
  run summaries and aggregate accounting.
- [campaign-ledger.json](campaign-ledger.json),
  [campaign-ledger.csv](campaign-ledger.csv), and
  [campaign-summary.json](campaign-summary.json): all 95 attempt reservations,
  outcomes, known usage and retained uncertainty.
- `r01-*`, `r02-*`, `r03-independent`, and `r03-solo`: ten started-run directories,
  each containing `config.json`, `events.jsonl`, `summary.json`,
  `usage-ledger.json`, `usage-ledger.csv` and `usage-summary.json`. Unstarted runs
  have manifest identities and comparison rows but no invented run artifacts.
- [report/analysis.json](report/analysis.json) and
  [report/runs.csv](report/runs.csv): descriptive condition summaries and every
  planned run, preserving missing values and known/incomplete cost flags.
- [report/curves.json](report/curves.json),
  [quality-vs-tokens.png](report/quality-vs-tokens.png), and
  [quality-vs-cost.png](report/quality-vs-cost.png): actual verified quality and
  known cumulative resources, with finite failure endpoints.
- [report/trace-annotations.md](report/trace-annotations.md): deterministic
  selection of recorded public delivery, observation and verification events.
  This documents provenance, not causal benefit.
- [report/replay-verification.json](report/replay-verification.json): all ten
  started traces passed replay checks.
- [report/independent-audit-local.json](report/independent-audit-local.json):
  3,831 passing independent checks, including the retained local SQLite ledger
  and manifest receipt.
- [report/independent-audit-public.json](report/independent-audit-public.json):
  3,802 passing checks using the published artifacts, without SQLite or the
  local receipt. Both audits separately count 93 candidate verifications,
  90 valid candidates and three invalid candidates.
- [SHA256SUMS](SHA256SUMS): checksums of every published file in this directory
  except the checksum file itself, including this README.

## Preservation and reproduction

The 65 raw campaign exports contain 54 byte-identical JSON/JSONL files and
eleven CSV files normalized from CRLF to LF for Git. Parsed CSV cells are
unchanged. Raw export files occupy 3,032,808 bytes after normalization. The
analysis, charts, audits and this README are separate derived artifacts.
Credential files, authorization headers, private reasoning text, SQLite
databases and the local authorization claim are not published.

From the repository root, these commands read saved artifacts without issuing
model requests:

```sh
python3 -m swarm_lab replay examples/terra-comparison/r01-independent --verify
python3 scripts/audit_live_comparison.py examples/terra-comparison
python3 scripts/report_live_comparison.py examples/terra-comparison \
  --out runs/terra-comparison-reproduced
```

The independent audit requires runtime source hashes matching the frozen
manifest. When running from a later checkout, point `--source-root` to a
checkout of the recorded commit. The audit script itself is independent of
`swarm_lab` imports and can run from the current checkout against that source.
Use `--require-sqlite` only against the original local campaign, where the raw
database remains available. The published audit cannot independently recover
unpublished SQLite state or the local receipt.

The report exporter uses the standard library by default. Add `--plots` with
Matplotlib installed to recreate the figures in the chosen output directory.
Generated figure bytes can differ with rendering-library versions; the
published data and resource coordinates remain available for inspection.
The exporter requires an output directory outside this evidence directory and
never resumes a run or requests credentials.

The [protocol](../../docs/live-comparison-protocol.md) contains the historical
prepare/execute commands for reproducibility. They describe the halted
campaign authorization, not permission for a new paid execution. No automatic
resume is permitted; a later continuation requires fresh authorization and a
disclosed protocol amendment.
