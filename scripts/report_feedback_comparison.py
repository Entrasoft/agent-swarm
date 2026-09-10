"""Read-only descriptive analysis of the six-run v0.2 feedback qualification.

No credentials, model calls, SQLite access or campaign continuation occur here.
The primary outcome and behavioral gate are rebuilt from worker-visible events;
the campaign JSON ledger supplies final accounting for every reserved attempt.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys

# Support both ``python -m scripts...`` and the documented direct script command.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swarm_lab.cli import verify_replay
from swarm_lab.math_task import validate_candidate


ARMS = ("private_best_only", "history_feedback")
STATUSES = ("unstarted", "running", "completed", "budget_stopped", "failed", "interrupted")
COUNTERS = ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens")
ZERO = Decimal("0")


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else None


def amount(value):
    result = Decimal(str(value)) if value is not None else ZERO
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid nonnegative monetary amount in evidence.")
    return result


def distribution(values):
    values = [value for value in values if value is not None]
    return dict(n=len(values), min=min(values) if values else None,
                median=statistics.median(values) if values else None,
                max=max(values) if values else None)


def _path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Run path must remain inside the source campaign.")
    return path


def _events(directory):
    source = directory / "events.jsonl"
    return [json.loads(line) for line in source.read_text().splitlines() if line.strip()] if source.is_file() else []


def _accounting(entries):
    """Add disjoint final ledger entries; never turn an unknown call into zero use."""
    result = dict(attempts=len(entries), known_tokens=0, known_calculated_cost_usd="0",
                  reserved_tokens=0, reserved_cost="0", pending_attempts=0,
                  unknown_attempts=0, unknown_cost_attempts=0,
                  tokens_complete=True, cost_complete=True,
                  reconciled_cost_usd="0", billing_status="not_reconciled")
    result.update({key: 0 for key in COUNTERS})
    cost, reserved, reconciled = ZERO, ZERO, ZERO
    for entry in entries:
        normalized = entry.get("normalized", {})
        # The aggregate ledger only counts complete token records. Optional
        # subsets must not increase the inclusive input-plus-output count.
        complete = normalized.get("complete") is True
        parts = [entry.get(key) for key in ("input_tokens", "output_tokens")]
        if complete and not all(type(value) is int and value >= 0 for value in parts):
            raise ValueError("Complete ledger entry has invalid token counters.")
        if complete:
            for key in COUNTERS:
                value = entry.get(key)
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError("Invalid ledger token subset.")
                result[key] += value or 0
            if (entry.get("cached_input_tokens") or 0) + (entry.get("cache_write_tokens") or 0) > parts[0]:
                raise ValueError("Input cache subsets exceed inclusive input tokens.")
            if (entry.get("reasoning_tokens") or 0) > parts[1]:
                raise ValueError("Reasoning subset exceeds inclusive output tokens.")
            result["known_tokens"] += sum(parts)
        else:
            result["unknown_attempts"] += 1
        observed = entry.get("observed_cost")
        cost += amount(observed)
        result["unknown_cost_attempts"] += observed is None
        result["pending_attempts"] += entry.get("outcome") == "pending"
        reserve = entry.get("reserved_tokens", 0)
        if type(reserve) is not int or reserve < 0:
            raise ValueError("Invalid token reservation.")
        result["reserved_tokens"] += reserve
        reserved += amount(entry.get("reserved_cost"))
        reconciled += amount(entry.get("reconciled_cost"))
    result.update(known_calculated_cost_usd=str(cost), reserved_cost=str(reserved),
                  reconciled_cost_usd=str(reconciled),
                  tokens_complete=not result["unknown_attempts"] and not result["pending_attempts"],
                  cost_complete=not result["unknown_cost_attempts"] and not result["pending_attempts"])
    result["total_tokens"] = result["known_tokens"] if result["tokens_complete"] else None
    result["calculated_cost_usd"] = str(cost) if result["cost_complete"] else None
    if entries and all(entry.get("reconciled_cost") is not None for entry in entries):
        result["billing_status"] = "reconciled"
    return result


def _check_summary(usage, calculated):
    if usage is None:
        return
    for key, target in (("attempts", "attempts"), ("total_tokens", "known_tokens"),
                        ("reserved_tokens", "reserved_tokens"), *[(key, key) for key in COUNTERS]):
        if key in usage and usage[key] != calculated[target]:
            raise ValueError(f"Ledger entries disagree with summary field {key}.")
    for key, target in (("observed_cost", "known_calculated_cost_usd"), ("reserved_cost", "reserved_cost")):
        if key in usage and amount(usage[key]) != amount(calculated[target]):
            raise ValueError(f"Ledger entries disagree with summary field {key}.")


def _scan(events, config, arm, path, run_id, check):
    """Recompute mathematics, distinct sets, and every eligible feedback exposure."""
    seen, verifications, observations, exposures, qualifying, improvements = set(), {}, {}, [], [], []
    valid_count = invalid_count = visible_count = dropped_count = 0
    first, lower = None, None
    decisions = 0
    dispatched_observations = 0
    dispatched_tasks = {event.get("task_id") for event in events
                        if event["event_type"] in {"provider_request", "usage"}}
    verification_points = {}
    for event in events:
        kind, payload = event["event_type"], event.get("payload", {})
        if kind == "observation":
            decisions += 1
            observations[event.get("task_id")] = event
            history = payload.get("attempt_history", [])
            # Runtime constructs/logs an observation before attempting a budget
            # reservation. Only admitted dispatches can expose feedback to a
            # model; a denied final request is not a behavioral observation.
            if event.get("task_id") not in dispatched_tasks:
                continue
            dispatched_observations += 1
            visible_count += len(history)
            if arm == "history_feedback":
                # All previously submitted attempts minus actually exposed
                # entries; a repeated omission on another call counts again.
                dropped_count += max(0, len(verifications) - len(history))
            eligible = []
            for entry in history:
                prior = verifications.get(entry.get("verification_event_id"))
                if prior is None:
                    check(False, "history_entry_without_prior_verification", path)
                    continue
                if not prior["valid"] or prior["repeated"]:
                    eligible.append(dict(verification_event_id=entry["verification_event_id"],
                                         decision=entry.get("decision"),
                                         kind="invalid" if not prior["valid"] else "repeated",
                                         candidate=entry.get("candidate"),
                                         forbidden_triple=entry.get("forbidden_triple")))
            if arm == "history_feedback" and eligible:
                exposures.append(dict(path=path, run_id=run_id, observation_event_id=event["event_id"],
                                      task_id=event.get("task_id"), decision=decisions,
                                      prior_lower_bound=lower, qualifying_history=eligible))
        elif kind == "verification":
            result = validate_candidate(config["m"], payload["candidate"])
            check(result.valid == payload.get("valid"), "verification_validity", path)
            normalized = tuple(sorted(payload["candidate"])) if result.valid else None
            repeated = result.valid and normalized in seen
            prior_lower = lower
            if result.valid:
                valid_count += 1
                seen.add(normalized)
                size = len(normalized)
                if first is None:
                    first = size
                lower = size if lower is None else max(lower, size)
            else:
                invalid_count += 1
            verifications[event["event_id"]] = dict(valid=result.valid, repeated=repeated)
            verification_points[event["event_id"]] = lower
            if result.valid and prior_lower is not None and lower > prior_lower:
                improvement = dict(path=path, run_id=run_id, verification_event_id=event["event_id"],
                                   decision=decisions, prior_lower_bound=prior_lower,
                                   lower_bound=lower, candidate=list(normalized),
                                   elapsed_seconds=event.get("elapsed_seconds"))
                improvements.append(improvement)
                observation = observations.get(event.get("task_id"))
                if observation:
                    exposure = next((item for item in reversed(exposures)
                                     if item["observation_event_id"] == observation["event_id"]), None)
                    if exposure is not None:
                        qualifying.append(dict(improvement,
                                               observation_event_id=observation["event_id"],
                                               qualifying_history=exposure["qualifying_history"]))
    return dict(valid_submissions=valid_count, invalid_mathematical_candidates=invalid_count,
                unique_valid_candidates=len(seen), duplicate_candidates=valid_count-len(seen),
                lower_bound=lower, first_valid_lower_bound=first,
                improvement_from_first_valid=lower-first if lower is not None else None,
                improvements=improvements, improvement_count=len(improvements),
                visible_history_entries=visible_count, dropped_history_entries=dropped_count,
                history_entry_drop_semantics="Per observation: all prior submitted attempts minus entries actually visible; repeated omissions count on each call.",
                observations=dispatched_observations,
                observations_constructed=decisions), exposures, qualifying, verification_points


def _diagnostics(events, entries, path, check):
    requests = {event["payload"].get("attempt_id"): event for event in events if event["event_type"] == "provider_request"}
    responses = {event["payload"].get("attempt_id"): event for event in events
                 if event["event_type"] in {"provider_result", "provider_failure"}}
    counts, records = Counter(), []
    for entry in entries:
        identity = entry["attempt_id"]
        request, response = requests.get(identity), responses.get(identity)
        payload = response.get("payload", {}) if response else {}
        details = payload.get("diagnostics", {})
        client_id = request.get("payload", {}).get("client_request_id") if request else None
        counts["attempts"] += 1
        counts["persisted_client_ids"] += bool(client_id)
        source = details.get("request_id_source")
        header_id = payload.get("request_id") if source == "response_header" else None
        fallback_id = payload.get("request_id") if source == "response_id_fallback" else None
        counts["returned_provider_request_ids"] += bool(header_id)
        counts["response_id_fallbacks"] += bool(fallback_id)
        counts["request_ids_without_source"] += bool(payload.get("request_id") and source not in {"response_header", "response_id_fallback"})
        outcome = entry.get("outcome")
        failure = outcome not in {"completed", "pending"}
        counts["failures"] += failure
        counts["failures_with_outcome"] += failure and bool(outcome)
        category = details.get("failure_category")
        counts["failures_with_diagnostic_category"] += failure and bool(category)
        if not entry.get("simulated"):
            check(bool(client_id), "persisted_client_id", path)
            if response is not None:
                check(request is not None and request["event_id"] < response["event_id"], "client_id_precedes_response", path)
                check(client_id == payload.get("client_request_id"), "client_id_correlation", path)
        check(bool(outcome), "attempt_outcome", path)
        if entry.get("normalized", {}).get("complete"):
            check(entry.get("status") in {"observed", "reconciled"} and not entry.get("reserved_tokens"), "known_usage_settled", path)
        else:
            check(entry.get("reserved_tokens", 0) > 0, "unknown_usage_token_reserve_retained", path)
        if entry.get("observed_cost") is None and entry.get("reconciled_cost") is None:
            check(amount(entry.get("reserved_cost")) > 0, "unknown_cost_reserve_retained", path)
        records.append(dict(attempt_id=identity, outcome=outcome, client_request_id=client_id,
                            provider_request_id=header_id, response_id_fallback=fallback_id,
                            request_id_source=source, failure_category=category,
                            response_status=details.get("response_status"),
                            incomplete_reason=details.get("incomplete_reason"),
                            content_types=details.get("content_types"),
                            refusal_count=details.get("refusal_count"),
                            reserved_tokens=entry.get("reserved_tokens"),
                            reserved_cost=entry.get("reserved_cost"),
                            known_calculated_cost_usd=entry.get("observed_cost"),
                            **{key: entry.get(key) for key in COUNTERS}))
    for key in ("attempts", "persisted_client_ids", "returned_provider_request_ids", "response_id_fallbacks",
                "request_ids_without_source", "failures", "failures_with_outcome", "failures_with_diagnostic_category"):
        counts.setdefault(key, 0)
    return dict(counts) | {"attempt_records": records}


def _curve(events, entries, lower_points, status):
    lookup = {entry["attempt_id"]: entry for entry in entries}
    counted, accumulated, points = set(), [], []
    lower = None
    for event in events:
        kind, payload = event["event_type"], event.get("payload", {})
        if kind == "usage":
            identity = payload.get("attempt_id")
            if identity not in lookup:
                raise ValueError("Usage event has no campaign ledger attempt.")
            if identity in counted:
                continue
            counted.add(identity)
            accumulated.append(lookup[identity])
        elif kind == "verification":
            lower = lower_points[event["event_id"]]
        else:
            continue
        values = _accounting(accumulated)
        points.append(dict(event_id=event["event_id"], kind=kind,
                           calls=values["attempts"], lower_bound=lower,
                           **{key: values[key] for key in ("known_tokens", "known_calculated_cost_usd",
                                                           "tokens_complete", "cost_complete", "unknown_attempts", *COUNTERS)}))
    # Include reserved/pending attempts even if interruption prevented telemetry.
    values = _accounting(entries)
    points.append(dict(event_id=events[-1]["event_id"] if events else None,
                       kind="endpoint", status=status, calls=len(entries), lower_bound=lower,
                       **{key: values[key] for key in ("known_tokens", "known_calculated_cost_usd",
                                                       "tokens_complete", "cost_complete", "unknown_attempts", *COUNTERS)}))
    return points


def _group(rows, entries):
    result = _accounting(entries)
    result.update(planned_runs=len(rows), started_runs=sum(row["started"] for row in rows),
                  status_counts={status: sum(row["status"] == status for row in rows) for status in STATUSES},
                  decisions_completed=sum(row["decisions_completed"] or 0 for row in rows),
                  unique_valid_candidates=distribution(row["unique_valid_candidates"] for row in rows),
                  unique_valid_values=[row["unique_valid_candidates"] for row in rows],
                  lower_bound=distribution(row["lower_bound"] for row in rows),
                  gap=distribution(row["gap"] for row in rows),
                  valid_submissions=sum(row["valid_submissions"] or 0 for row in rows),
                  duplicate_candidates=sum(row["duplicate_candidates"] or 0 for row in rows),
                  invalid_mathematical_candidates=sum(row["invalid_mathematical_candidates"] or 0 for row in rows),
                  worker_seconds=distribution(row["worker_seconds"] for row in rows),
                  oracle_seconds=distribution(row["oracle_seconds"] for row in rows))
    return result


def analyze(campaign):
    campaign = Path(campaign)
    manifest = read_json(campaign / "manifest.json")
    report = read_json(campaign / "feedback-campaign.json")
    ledger = read_json(campaign / "campaign-ledger.json")
    if not all(isinstance(item, dict) for item in (manifest, report, ledger)):
        raise ValueError("Require manifest.json, feedback-campaign.json and campaign-ledger.json.")
    schedule = sorted(manifest.get("schedule", manifest.get("runs", [])), key=lambda row: row["order"])
    if (len(schedule) != 6 or [row["order"] for row in schedule] != list(range(1, 7))
            or {(row["block"], row["arm"]) for row in schedule} != {(block, arm) for block in range(1, 4) for arm in ARMS}
            or any(len({row[key] for row in schedule}) != 6 for key in ("path", "run_id"))):
        raise ValueError("Manifest must contain the six distinct planned run identities and arm/block cells.")
    sources = {row["run_id"]: row for row in report["runs"]}
    if len(sources) != 6 or set(sources) != {row["run_id"] for row in schedule}:
        raise ValueError("Campaign snapshot must retain all six planned rows.")
    entries = ledger["entries"]
    if len({entry["attempt_id"] for entry in entries}) != len(entries) or any(entry["run_id"] not in sources for entry in entries):
        raise ValueError("Duplicate or foreign attempt in campaign ledger.")
    audit = dict(verified=True, checks=0, failures=[], replay=[])

    def check(passed, name, path=None):
        audit["checks"] += 1
        if not passed:
            audit["verified"] = False
            audit["failures"].append(dict(check=name, path=path))

    rows, curves, exposures, qualifying = [], [], [], []
    for planned in schedule:
        source = sources[planned["run_id"]]
        for key in ("order", "block", "arm", "path"):
            if source.get(key) != planned.get(key):
                raise ValueError("Campaign row identity differs from frozen manifest.")
        status = source["status"]
        if status not in STATUSES:
            raise ValueError("Unknown feedback run status.")
        directory = _path(campaign, planned["path"])
        row_entries = [entry for entry in entries if entry["run_id"] == planned["run_id"]]
        events = _events(directory)
        summary = read_json(directory / "summary.json") or source.get("summary") or {}
        config = read_json(directory / "config.json") or planned.get("config") or {"m": 24}
        started = status != "unstarted"
        if not started and (events or summary or row_entries):
            raise ValueError("Unstarted row contains execution evidence.")
        row = {key: planned.get(key) for key in ("order", "block", "seed", "arm", "path", "run_id")}
        row.update(status=status, started=started, planned_decisions=planned.get("limits", {}).get("call_limit", 12),
                   stopping_reason=summary.get("stopping_reason"), worker_seconds=summary.get("worker_seconds"),
                   verification_seconds=summary.get("verification_seconds"),
                   oracle_seconds=summary.get("oracle", {}).get("elapsed_seconds"),
                   oracle_status=summary.get("oracle", {}).get("status"),
                   upper_bound=summary.get("upper_bound"))
        scan, eligible, qualifies, lower_points = _scan(events, config, row["arm"], row["path"], row["run_id"], check)
        if started:
            try:
                replay = verify_replay(directory)
                check(replay.get("verified") is True, "replay", row["path"])
                audit["replay"].append(dict(path=row["path"], **replay))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                check(False, "replay_" + type(exc).__name__, row["path"])
                audit["replay"].append(dict(path=row["path"], verified=False, error_type=type(exc).__name__))
            for key in ("unique_valid_candidates", "duplicate_candidates"):
                if key in summary:
                    check(summary[key] == scan[key], "summary_" + key, row["path"])
            if "lower_bound" in summary:
                check(summary["lower_bound"] == (scan["lower_bound"] or 0), "summary_lower_bound", row["path"])
        accounting = _accounting(row_entries)
        _check_summary(read_json(directory / "usage-summary.json") or summary.get("usage"), accounting)
        row.update(scan)
        row.update(accounting)
        row["decisions_completed"] = scan["valid_submissions"] + scan["invalid_mathematical_candidates"]
        row["protocol_failures"] = sum(event["event_type"] == "invalid_action" for event in events)
        row["gap"] = row["upper_bound"]-row["lower_bound"] if row["lower_bound"] is not None and row["upper_bound"] is not None else None
        row["diagnostics"] = _diagnostics(events, row_entries, row["path"], check)
        if not started:
            for key in ("unique_valid_candidates", "duplicate_candidates", "valid_submissions",
                        "invalid_mathematical_candidates", "decisions_completed", "protocol_failures",
                        "lower_bound", "first_valid_lower_bound", "improvement_from_first_valid", "improvement_count",
                        "visible_history_entries", "dropped_history_entries", "observations", "observations_constructed", *accounting.keys()):
                row[key] = None
        check(len(row_entries) <= row["planned_decisions"], "run_call_ceiling", row["path"])
        check(accounting["known_tokens"] + accounting["reserved_tokens"] <= config.get("token_limit", 100000),
              "run_token_ceiling", row["path"])
        check(amount(accounting["known_calculated_cost_usd"]) + amount(accounting["reserved_cost"]) <= amount(config.get("cost_limit", "1")),
              "run_cost_ceiling", row["path"])
        rows.append(row)
        exposures.extend(eligible)
        qualifying.extend(qualifies)
        curves.append(dict(path=row["path"], block=row["block"], arm=row["arm"], status=status,
                           points=_curve(events, row_entries, lower_points, status) if started else []))
    totals = _group(rows, entries)
    _check_summary(read_json(campaign / "campaign-summary.json") or report.get("usage"), totals)
    limits = manifest.get("limits", {})
    check(len(entries) <= limits.get("call_limit", 72), "campaign_call_ceiling")
    check(totals["known_tokens"] + totals["reserved_tokens"] <= limits.get("token_limit", 600000), "campaign_token_ceiling")
    check(amount(totals["known_calculated_cost_usd"]) + amount(totals["reserved_cost"]) <= amount(limits.get("cost_limit", "6")), "campaign_cost_ceiling")
    unknown = [entry for entry in entries if not entry.get("normalized", {}).get("complete") or entry.get("observed_cost") is None]
    if unknown:
        check(report.get("status") == "halted", "unknown_usage_halts_campaign")
        first_unknown = next(index for index, entry in enumerate(entries) if entry in unknown)
        check(first_unknown == len(entries)-1, "no_dispatch_after_unknown_usage")
    paired = []
    for block in range(1, 4):
        baseline = next(row for row in rows if row["block"] == block and row["arm"] == ARMS[0])
        treatment = next(row for row in rows if row["block"] == block and row["arm"] == ARMS[1])
        paired.append(dict(block=block, baseline_unique=baseline["unique_valid_candidates"],
                           treatment_unique=treatment["unique_valid_candidates"],
                           treatment_minus_baseline=treatment["unique_valid_candidates"]-baseline["unique_valid_candidates"]
                           if baseline["started"] and treatment["started"] else None,
                           baseline_status=baseline["status"], treatment_status=treatment["status"],
                           baseline_stopping_reason=baseline["stopping_reason"], treatment_stopping_reason=treatment["stopping_reason"]))
    qualification = dict(status="qualified" if qualifying and audit["verified"] else
                        "engineering_failed" if not audit["verified"] else "unmet" if exposures else "unexercised",
                         engineering_checks_passed=audit["verified"],
                         eligible_exposures=exposures, qualifying_events=qualifying,
                         witness=qualifying[0] if qualifying else None,
                         witness_selection="Earliest qualifying improvement in the frozen execution schedule; all qualifying events retained.",
                         interpretation="An observed recover-and-progress sequence does not establish feedback causation or comparative effectiveness.")
    analysis = dict(schema_version=1, study="solo-feedback-v0.2", campaign_id=report.get("campaign_id"),
                    status=report.get("status"), stop_reason=report.get("stop_reason"),
                    source_sha256={name: hashlib.sha256((campaign/name).read_bytes()).hexdigest()
                                   for name in ("manifest.json", "feedback-campaign.json", "campaign-ledger.json")},
                    definitions=dict(primary="Distinct actually submitted valid sets over the entire run. Initial private state is excluded; a submitted empty set counts. Unstarted outcomes are null.",
                                     quality="Best independently checked worker size; null until an actual valid submission. The hidden exact solver remains a separate evaluator baseline.",
                                     resources="Final JSON ledger accounting in dispatch order. Input plus output only; cache and reasoning are subsets. Calculated cost is not reconciled billing; unknown calls retain reservations.",
                                     interpretation="Six runs on one instance provide descriptive qualification only; diversity can increase without objective progress, and paired blocks are not identical provider draws.",
                                     audit="Read-only replay and independent event/accounting consistency checks; not cryptographic authentication or a rerun of the frozen offline fault-injection suite."),
                    runs=rows, totals=totals, paired_blocks=paired,
                    arms={arm: _group([row for row in rows if row["arm"] == arm],
                                     [entry for entry in entries if sources[entry["run_id"]]["arm"] == arm]) for arm in ARMS},
                    qualification=qualification, audit=audit)
    return analysis, curves


def markdown(analysis):
    totals, gate = analysis["totals"], analysis["qualification"]
    lines = ["# Solo feedback v0.2: descriptive results", "",
             f"Campaign status: **{analysis['status']}**. Behavioral qualification: **{gate['status']}**.", "",
             "All six planned rows are retained. These observations do not establish causation or a swarm advantage.", "",
             "| Block | Arm | Status | Calls / 12 | Decisions | Unique valid | Valid duplicates | Invalid math | L | Gap | Known calculated USD |",
             "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    show = lambda value: "—" if value is None else str(value)
    for row in analysis["runs"]:
        values = [row[key] for key in ("block", "arm", "status", "attempts", "decisions_completed", "unique_valid_candidates",
                                      "duplicate_candidates", "invalid_mathematical_candidates", "lower_bound", "gap", "known_calculated_cost_usd")]
        lines.append("| " + " | ".join(show(value) for value in values) + " |")
    lines += ["", "| Block | Treatment − baseline unique sets | Baseline status | Treatment status |",
              "| ---: | ---: | --- | --- |"]
    for pair in analysis["paired_blocks"]:
        lines.append(f"| {pair['block']} | {show(pair['treatment_minus_baseline'])} | {pair['baseline_status']} | {pair['treatment_status']} |")
    lines += ["", f"Known totals: {totals['attempts']} reserved attempts, {totals['known_tokens']:,} provider-reported tokens, "
              f"USD {totals['known_calculated_cost_usd']} calculated cost. Token totals complete: {totals['tokens_complete']}; "
              f"calculated cost complete: {totals['cost_complete']}.", "",
              f"Retained reservations: {totals['reserved_tokens']:,} tokens and USD {totals['reserved_cost']}. "
              "Reasoning is included in output, and cache counters are input subsets. Calculated costs are not billing reconciliation.", "",
              f"Replay and report checks: {analysis['audit']['checks']} checks, {len(analysis['audit']['failures'])} failures. "
              f"Eligible feedback observations: {len(gate['eligible_exposures'])}; qualifying improvements: {len(gate['qualifying_events'])}.", "",
              "All eligible exposures, all qualifying events, attempt diagnostics, and arm ranges are retained in analysis.json. "
              "Curves stop at measured endpoints and include failed/unknown attempts; no continuation is inferred."]
    if gate["witness"]:
        witness = gate["witness"]
        lines += ["", f"Predeclared earliest witness: `{witness['path']}/events.jsonl`, observation event "
                  f"{witness['observation_event_id']} and verification event {witness['verification_event_id']}: "
                  f"L increased from {witness['prior_lower_bound']} to {witness['lower_bound']}. "
                  f"Visible qualifying history: {json.dumps(witness['qualifying_history'], sort_keys=True)}.", "",
                  "This is a recover-and-progress sequence; the observation does not isolate feedback's causal effect."]
    return "\n".join(lines) + "\n"


def plots(analysis, curves, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {1: "#2563eb", 2: "#0f766e", 3: "#9333ea"}
    endpoints = {"completed": "o", "budget_stopped": "s", "failed": "X", "interrupted": "X", "running": "^"}
    for field, label, filename in (("calls", "Actual reserved calls", "quality-vs-calls.png"),
                                    ("known_tokens", "Known cumulative provider tokens", "quality-vs-tokens.png"),
                                    ("known_calculated_cost_usd", "Known cumulative calculated cost (USD)", "quality-vs-cost.png")):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True, sharey=True, layout="constrained")
        for arm, ax in zip(ARMS, axes):
            for curve in [curve for curve in curves if curve["arm"] == arm and curve["points"]]:
                points = [point for point in curve["points"] if point["lower_bound"] is not None]
                if not points:
                    continue
                xs, ys = [float(point[field]) for point in points], [point["lower_bound"] for point in points]
                color = colors[curve["block"]]
                ax.step(xs, ys, where="post", color=color, label=f"Block {curve['block']}")
                ax.scatter(xs[-1], ys[-1], color=color, marker=endpoints.get(curve["status"], "X"), zorder=3)
                if not points[-1]["tokens_complete"] or not points[-1]["cost_complete"]:
                    ax.annotate("unknown usage/cost", (xs[-1], ys[-1]), xytext=(4, 7), textcoords="offset points", fontsize=8)
            bounds = {row["upper_bound"] for row in analysis["runs"] if row["oracle_status"] == "optimal"}
            for bound in bounds:
                ax.axhline(bound, color="#475569", linestyle="--", linewidth=.8, label=f"Exact evaluator optimum {bound}")
            missing = [row for row in analysis["runs"] if row["arm"] == arm and row["lower_bound"] is None]
            if missing:
                labels = [f"block {row['block']} ({row['status']}" +
                          (", unknown usage/cost" if row["started"] and
                           (not row["tokens_complete"] or not row["cost_complete"]) else "") + ")"
                          for row in missing]
                ax.text(.02, .02, "No worker quality:\n" + "\n".join(labels), transform=ax.transAxes, fontsize=8)
            ax.set(title=arm.replace("_", " "), xlabel=label, ylabel="Best verified worker size L")
            ax.grid(alpha=.15)
            ax.legend(fontsize=8)
        fig.suptitle("Solo feedback qualification · measured endpoints only; unknown subtotals labeled")
        fig.savefig(output / filename, dpi=180)
        plt.close(fig)


def export(campaign, output, make_plots=False):
    campaign, output = Path(campaign), Path(output)
    if output.resolve().is_relative_to(campaign.resolve()) or campaign.resolve().is_relative_to(output.resolve()):
        raise ValueError("Export to a separate directory outside the source campaign.")
    analysis, curves = analyze(campaign)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("analysis.json", analysis), ("curves.json", curves)):
        (output/name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    (output/"report.md").write_text(markdown(analysis))
    with (output/"runs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(analysis["runs"][0]), lineterminator="\n")
        writer.writeheader()
        for row in analysis["runs"]:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    if make_plots:
        plots(analysis, curves, output)
    return analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, nargs="?")
    parser.add_argument("--campaign", type=Path, dest="campaign_option")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args(argv)
    campaign = args.campaign_option or args.campaign
    if campaign is None or args.campaign_option is not None and args.campaign is not None:
        parser.error("Supply exactly one campaign path.")
    result = export(campaign, args.out, args.plots)
    print(json.dumps(dict(output=str(args.out), totals=result["totals"], qualification=result["qualification"]["status"],
                          audit_verified=result["audit"]["verified"]), indent=2))


if __name__ == "__main__":
    main()
