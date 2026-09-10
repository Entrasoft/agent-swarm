# Changelog

## Unreleased — approved v0.2 execution

- Adds the separately authorized six-run feedback campaign executor, with fixed per-run/shared allowances, frozen source and document receipts, clean-source checks, and a persistent one-use claim. The ceilings are 72 calls, USD 6 and 600,000 tokens, with zero retries.
- Freezes a new UTC-dated price snapshot and the execution record without modifying the original proposed protocol or historical comparison evidence. Adds descriptive reporting and an independent public mathematics/accounting audit.
- Before inference, 236 offline tests pass, including 18 campaign guard tests, 15 reporting tests and three independent audit tests. A read-only metadata request confirmed model visibility without generation.

## 0.2.0 — feedback qualification preparation

- Adds an opt-in solo decision protocol with bounded own-attempt history and deterministic validator feedback. Both proposed arms continue after invalid mathematics while preserving provider/protocol stopping and unknown-usage reservations. Defaults retain the legacy protocol.
- Records a client request ID before dispatch, retains server correlation information through body failures, and classifies refusal, incomplete response, malformed output and transport failures using bounded metadata. Usage telemetry is restricted to accounting counters; raw response text and private reasoning are not diagnostic artifacts.
- Adds independent replay checks for visible feedback history and offline fault-injection coverage. Prepares a six-run comparison proposal with ceilings of 72 calls, USD 6 and 600,000 tokens; preparation cannot authenticate or execute inference. No paid v0.2 calls have been made.
- Validation: 200 offline tests pass, the scripted feedback demonstration passes replay, and all 75 historical comparison checksums plus 3,802 independent public audit checks remain valid against the frozen v1 source.

### Earlier comparison and calibration work included in this version

- Executed the approved comparison until its mandatory halt: 95 attempts, 94 known responses, 156,639 known tokens and USD 1.499658 known calculated cost. One unresolved transport attempt retains its reservation. Preserved five completed, four failed, one interrupted and ten unstarted rows, plus public audits, charts and revised unpublished drafts. No optimum was found in the ten started runs.

- Added the approved twenty-run m=24 comparison runner with fixed per-run allowances, frozen randomized order and campaign-wide interruption handling. Its separate authorization permits at most 240 calls, USD 20 and 2,000,000 tokens, with zero retries.

- Added durable shared campaign token, currency and call ceilings, plus a fixed, single-execution difficulty calibration runner. Failed or ambiguous calls stop calibration and retain reservations; returned model and service tier must match the approved configuration.
- Completed the separately authorized six-call Terra calibration: 10,395 tokens and USD 0.102580 calculated cost, with zero retries. m=18 was first-call optimal; m=24 retained gap 2 and was selected by the precommitted rule. Preserved the report and raw evidence separately from the later comparison.
- Added regression coverage for shared budgets, concurrent claims, returned identifiers, failure reporting and difficulty selection; the comparison checkpoint had 154 offline tests, including comparison and reporting checks.

## 0.1.1 — 2026-09-09

Marks the completed Terra integration pilot and prepares the next article experiment. This release updates package metadata and documentation; it does not change runtime behavior or perform additional inference.

- Preserves the three-call Terra pilot report and public trace: 2,260 provider-reported tokens, USD 0.016160 calculated API cost, and independently verified optimum 6 at m=12. Billing remains unreconciled.
- Adds a ready-to-paste follow-on prompt for difficulty calibration, a frozen live comparison protocol, campaign budget controls and the article package.
- Keeps the original pilot configuration, executed source revision and artifact checksums unchanged. The pilot ran at revision `eeb79d7`, before this version bump.

## 0.1.0 — initial implementation

Implemented offline search, mathematical validation, hidden exact evaluation, durable event and usage stores, a local replay viewer, an opt-in Responses adapter, secure local credential setup, and the initial evidence and article drafts. Subsequent work on this version completed the first live Terra pilot.
