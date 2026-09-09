# Local event display

Open a recorded run in a local desktop window:

```sh
python -m swarm_lab.display runs/YOUR_RUN_DIRECTORY
```

The display uses Python's standard-library Tkinter. It requires a graphical
desktop and a Python installation with Tk support. It opens no server and does
not publish or deploy a website. Headless environments can still import the
module and run all projection tests.

![Actual desktop replay of an algorithmic adaptive run](images/display.jpg)

This screenshot shows event 100 of a real 180-event algorithmic run with ten
agents (`m=12`, seed 0, 24 decisions), paused on a recorded artifact-use event.
Its usage is simulated. The final run reached verified bounds 6–6 with zero
actual model calls; the screenshot intentionally shows the earlier replay
position, before hidden evaluation establishes the final upper bound.

The window reads `config.json` and tails `events.jsonl` in the selected run
directory. It can attach while the runtime is still appending events. Complete
JSONL lines appear on the next polling interval; a partially written final line
waits for its newline, even when a multibyte UTF-8 character is split across
writes. A corrupt complete record produces a visible warning. Replacing or
truncating a log resets the display's projection.

## Reading the display

- The mode banner separates algorithmic computation, scripted fixtures, and
  live-provider execution. The usage source is shown independently: simulated,
  estimated, reported, reconciled, or unknown.
- The team graph shows recorded identities, roles, tasks, and states. Configured
  `agent-0` through `agent-N` have stable positions. Assignment, message, artifact,
  and verification edges use distinct colors. The graph shows the latest route
  for each category within the last 60 edge events. Artifact-use edges may
  identify the sender through an explicitly referenced delivery event; they show
  recorded reference/use, not a causal contribution. The event log remains the
  source of truth. A connected graph does not demonstrate cooperation.
- The activity table aligns events with recorded elapsed time, actor, recipient,
  task, and verification status. It shows the latest 1,500 events at the current
  playback position; the full log remains available by replaying earlier events.
- Selecting an event exposes its public payload, recorded assumptions and
  verification status, recursive parent events, missing parent references, and
  events for the same artifact, including its versions. Selecting a graph node
  exposes its recorded state and recent public events. No private reasoning is
  requested, inferred, or fabricated.
- Bounds change only from trusted verification, hidden-evaluator, or final summary events. A
  worker's candidate or assertion cannot establish an optimum in this display.
  Final bounds and the stopping reason appear only when the replay reaches their
  recorded events.
- The usage tab shows cumulative known token/cost curves and per-agent totals.
  Sources and currencies stay separate. Cached-input and reasoning token
  subsets are not added to input/output totals a second time. Missing usage is
  marked unknown (`?`) or unpriced. Replaying an event or receiving a duplicate
  event ID cannot duplicate spend. Later telemetry for the same attempt replaces
  the prior record; the timeline uses the latest per-attempt values at their
  recorded correction time. It is a projection of the selected replay position,
  not a billing statement.

`Follow live log` immediately advances to the newest recorded event and follows
new writes. `Replay` starts from the beginning. `Play`/`Pause`, `Step`, the speed
selector, and the position slider control event playback. Playback advances by
events per second, rather than pretending to reproduce wall-clock timing. All
time labels use the original event timestamps/elapsed time.

## Data contract

`run_started.payload` contains configuration directly (a nested `config` object
is also accepted) and a `team` list of objects with `agent_id` and `role`.
Configuration includes `mode`, universe size `m`, and
`agents` (the team size). `assignment` supplies `recipient` and `task_id`.
`verification.payload` supplies trusted `lower_bound`, `upper_bound`, and `valid`.
`run_finished.payload.summary` supplies the final bounds and `stopping_reason`.

A `usage` event has an `attempt_id`, nullable `input_tokens`, `output_tokens`, and
`cost`, and a `simulated` flag. Optional `currency` defaults to USD for this
runtime's ledger. Optional `status`/`usage_status` identifies estimates or billing
reconciliation. Optional committed/remaining token and cost values populate the
budget panel. Unattributable usage records without an attempt ID are retained in
the event inspector but excluded from aggregates. The runtime's ledger exports
remain authoritative for detailed billing accounting.

The module exports `launch(run_dir)`, `project_events(events, config=None)`,
`EventProjection`, and `JsonlTail`. Tests exercise verified-bound isolation,
replay consistency, duplicate/corrected telemetry, unknown usage, token subsets,
provenance cycles, stable positions, partial UTF-8 records, and log truncation:

```sh
python -m unittest discover -s tests -p 'test_display.py'
```
