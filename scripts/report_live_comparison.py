"""Export descriptive live-comparison evidence without modifying source artifacts.

The default path uses only the standard library. ``--plots`` additionally needs
matplotlib in the author's environment; it is not a runtime dependency. This
script never contacts a provider, reads credentials, or resumes a campaign.
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


CONDITIONS = ("solo", "independent", "fixed", "adaptive")
STATUSES = ("unstarted", "running", "completed", "budget_stopped", "failed", "interrupted")
MONEY = Decimal("0")


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else None


def money(value):
    return Decimal(str(value)) if value is not None else MONEY


def distribution(values):
    """Never fill unavailable observations with zero."""
    values = [value for value in values if value is not None]
    return {"n": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}


def _complete(usage, kind):
    fields = ("unknown_attempts", "pending_attempts") if kind == "tokens" else (
        "unknown_cost_attempts", "pending_attempts", "unpriced_attempts")
    return usage is not None and all(not usage.get(field, 0) for field in fields)


def _cost(usage):
    # Keep the calculation separate from known_cost, which may include a later
    # billing reconciliation. Missing observed spend is never silently invented.
    return usage.get("observed_cost") if usage else None


def _calculation_complete(usage, entries=None):
    if not _complete(usage, "tokens") or not _complete(usage, "cost") or _cost(usage) is None:
        return False
    if entries is not None:
        return len(entries) == usage.get("attempts", 0) and all(entry.get("observed_cost") is not None for entry in entries)
    # A billed amount can resolve a ledger's unknown charge without resolving
    # provider usage. Without entries, do not infer calculated-cost completeness
    # from a reconciled aggregate alone.
    return money(usage.get("reconciled_cost")) == 0


def _events(directory):
    path = directory / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []


def _run_directory(campaign, relative):
    directory = (campaign / relative).resolve()
    if not directory.is_relative_to(campaign.resolve()):
        raise ValueError("Run path must remain inside the source campaign directory.")
    return directory


def _curve(events, usage, entries, status):
    """Keep the last charged failure in the curve, even without a new candidate.

    Coordinates are known subtotals. Completeness flags distinguish a final
    total from a lower bound when a failed request has uncertain accounting.
    Final ledger entries supersede an earlier telemetry event if corrected.
    """
    lookup = {entry["attempt_id"]: entry for entry in entries}
    counted = set()
    tokens, cost, best = 0, MONEY, 0
    tokens_complete = cost_complete = True
    points = [{"event_id": None, "known_tokens": 0, "known_cost_usd": "0",
               "lower_bound": 0, "tokens_complete": True, "cost_complete": True,
               "kind": "initial"}]
    for event in events:
        payload = event.get("payload", {})
        event_type = event["event_type"]
        if event_type == "usage":
            attempt_id = payload.get("attempt_id")
            if attempt_id in counted:
                continue
            counted.add(attempt_id)
            entry = lookup.get(attempt_id, payload)
            observed = entry.get("observed_cost", entry.get("cost"))
            parts = (entry.get("input_tokens"), entry.get("output_tokens"))
            complete_parts = all(type(part) is int and part >= 0 for part in parts)
            # Match Ledger._aggregate: an incomplete attempt retains a budget
            # reservation; its isolated token fields are not a complete total.
            if complete_parts:
                tokens += sum(parts)
            tokens_complete &= complete_parts
            cost += money(observed)
            cost_complete &= observed is not None
        elif event_type == "verification":
            if payload.get("valid"):
                best = max(best, len(payload["candidate"]))
        else:
            continue
        points.append({"event_id": event.get("event_id"), "known_tokens": tokens,
                       "known_cost_usd": str(cost), "lower_bound": best,
                       "tokens_complete": tokens_complete, "cost_complete": cost_complete,
                       "kind": event_type})
    # A pending/interrupted attempt can be in the ledger without a usage event.
    # The summary also catches any missing event projection; its total must not
    # disappear merely because the last response supplied no candidate.
    if usage is not None:
        final_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        final_cost = _cost(usage)
        if final_tokens < tokens or (final_cost is not None and money(final_cost) < cost):
            raise ValueError("Curve event accounting exceeds the final ledger summary.")
        tokens = final_tokens
        if final_cost is not None:
            cost = money(final_cost)
        tokens_complete = _complete(usage, "tokens")
        cost_complete = _calculation_complete(usage, entries or None)
    points.append({"event_id": events[-1].get("event_id") if events else None,
                   "known_tokens": tokens, "known_cost_usd": str(cost), "lower_bound": best,
                   "tokens_complete": tokens_complete, "cost_complete": cost_complete,
                   "kind": "endpoint", "status": status})
    return points


def _row(source, campaign):
    directory = _run_directory(campaign, source["path"])
    status = source["status"]
    if status not in STATUSES:
        raise ValueError(f"Unknown run status: {status}")
    summary = source.get("summary") or read_json(directory / "summary.json") or {}
    usage = read_json(directory / "usage-summary.json") or summary.get("usage") or source.get("usage")
    events = _events(directory)
    ledger = read_json(directory / "usage-ledger.json") or {}
    started = status != "unstarted"
    if not started and (events or summary or usage):
        raise ValueError("Unstarted row has run evidence; check the campaign snapshot.")
    row = {key: source.get(key) for key in ("order", "repetition", "seed", "condition", "path", "run_id", "status")}
    attempts = usage.get("attempts") if usage is not None else None
    row.update(started=started, attempted=bool(attempts) if attempts is not None else None if started else False,
               attempts=attempts, stopping_reason=summary.get("stopping_reason"),
               lower_bound=summary.get("lower_bound"), upper_bound=summary.get("upper_bound"),
               gap=summary.get("gap"), solved=summary["gap"] == 0 if summary.get("gap") is not None else None)
    for key in ("decisions_completed", "invalid_claims", "duplicate_candidates", "artifact_reuse",
                "messages", "message_bytes", "worker_seconds", "verification_seconds",
                "time_to_optimal_candidate_seconds", "time_to_verified_optimality_seconds"):
        row[key] = summary.get(key)
    row["oracle_seconds"] = summary.get("oracle", {}).get("elapsed_seconds")
    row["oracle_status"] = summary.get("oracle", {}).get("status")
    row["best_candidate"] = summary.get("best_candidate")
    row["known_tokens"] = usage.get("total_tokens") if usage is not None else None
    row["known_calculated_cost_usd"] = _cost(usage)
    row["tokens_complete"] = _complete(usage, "tokens") if started else None
    row["cost_complete"] = _calculation_complete(usage, ledger.get("entries")) if started else None
    row["total_tokens"] = row["known_tokens"] if row["tokens_complete"] else None
    row["calculated_cost_usd"] = row["known_calculated_cost_usd"] if row["cost_complete"] else None
    row["reconciled_cost_usd"] = usage.get("reconciled_cost") if usage is not None else None
    row["billing_status"] = usage.get("billing_status") if usage is not None else None
    for key in ("unknown_attempts", "unknown_cost_attempts", "pending_attempts", "reserved_tokens", "reserved_cost",
                "input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens"):
        row[key] = usage.get(key) if usage is not None else None
    coordination = usage.get("groups", {}).get("purpose", {}).get("coordination", {}) if usage is not None else {}
    row["coordinator_attempts"] = coordination.get("attempts", 0) if usage is not None else None
    row["coordinator_known_tokens"] = coordination.get("total_tokens", 0) if usage is not None else None
    row["coordinator_known_calculated_cost_usd"] = coordination.get("observed_cost", "0") if usage is not None else None
    coordinator_entries = [entry for entry in ledger.get("entries", []) if entry.get("purpose") == "coordination"] if "entries" in ledger else None
    row["coordinator_cost_complete"] = _calculation_complete(coordination, coordinator_entries) if coordination else True if usage is not None else None
    row["per_agent_attempts"] = {key: value["attempts"] for key, value in usage.get("groups", {}).get("agent", {}).items()} if usage is not None else None
    row["per_agent_completed_decisions"] = dict(Counter(event["actor"] for event in events if event["event_type"] == "task_completed")) if started else None
    for event_type in ("message_delivered", "message_rejected", "message_read", "artifact_used"):
        row[event_type + "_count"] = sum(event["event_type"] == event_type for event in events) if started else None
    quality_recorded = row["lower_bound"] is not None or any(event["event_type"] == "verification" for event in events)
    curve = _curve(events, usage, ledger.get("entries", []), status) if started and quality_recorded else []
    if curve and row["lower_bound"] is not None and events and curve[-1]["lower_bound"] != row["lower_bound"]:
        raise ValueError("Verified curve endpoint does not match the recorded run lower bound.")
    return row, events, curve


def _group(rows):
    started = [row for row in rows if row["started"]]
    statuses = Counter(row["status"] for row in rows)
    solved = sum(row["solved"] is True for row in rows)
    known_cost = sum((money(row["known_calculated_cost_usd"]) for row in started), MONEY)
    cost_complete = all(row["cost_complete"] for row in started)
    tokens_complete = all(row["tokens_complete"] for row in started)
    return {
        "planned_runs": len(rows), "started_runs": len(started),
        "attempted_runs": sum(row["attempted"] is True for row in rows),
        "attempted_status_unknown_runs": sum(row["started"] and row["attempted"] is None for row in rows),
        "status_counts": {status: statuses[status] for status in STATUSES},
        "solved_runs": solved, "quality_available_runs": sum(row["lower_bound"] is not None for row in rows),
        "solved_assessed_runs": sum(row["solved"] is not None for row in rows),
        "attempts": sum(row["attempts"] or 0 for row in rows),
        "completed_decisions": sum(row["decisions_completed"] or 0 for row in rows),
        "lower_bound": distribution(row["lower_bound"] for row in rows),
        "gap": distribution(row["gap"] for row in rows),
        "oracle_seconds": distribution(row["oracle_seconds"] for row in rows),
        "worker_seconds": distribution(row["worker_seconds"] for row in rows),
        "known_tokens": sum(row["known_tokens"] or 0 for row in started),
        "tokens_complete": tokens_complete,
        "known_calculated_cost_usd": str(known_cost), "cost_complete": cost_complete,
        "calculated_cost_usd": str(known_cost) if cost_complete else None,
        "calculated_cost_per_verified_solution_usd": str(known_cost / solved) if solved and cost_complete else None,
        "cost_per_solution_status": "incomplete_unknown_cost" if not cost_complete else "undefined_no_solutions" if not solved else "calculated",
        "coordinator_attempts": sum(row["coordinator_attempts"] or 0 for row in rows),
        "coordinator_known_tokens": sum(row["coordinator_known_tokens"] or 0 for row in rows),
        "coordinator_known_calculated_cost_usd": str(sum((money(row["coordinator_known_calculated_cost_usd"]) for row in rows), MONEY)),
        "messages_sent": sum(row["messages"] or 0 for row in rows),
        "messages_delivered": sum(row["message_delivered_count"] or 0 for row in rows),
        "message_bytes": sum(row["message_bytes"] or 0 for row in rows),
        "policy_reported_reuse": sum(row["artifact_used_count"] or 0 for row in rows),
    }


def _trace(rows, events_by_path):
    prefix = ["# Annotated public trace", "",
              "Selection rule: earliest scheduled adaptive run containing a delivered message; "
              "select its first delivery, the first receiver observation containing that delivery, "
              "and a valid candidate from that receiver in the same decision task.", "",
              "These are recorded public actions and policy-reported provenance. Temporal order "
              "and a reported use do not establish that the message caused an improvement. "
              "No private reasoning text is collected.", ""]
    selected = next((row for row in rows if row["condition"] == "adaptive" and any(
        event["event_type"] == "message_delivered" for event in events_by_path[row["path"]])), None)
    if selected is None:
        prefix += ["No adaptive run contains a delivered message. No message-to-candidate example is available.", ""]
        selected = next((row for row in rows if row["started"]), None)
        if selected is None:
            return "\n".join(prefix + ["No run was started.", ""])
        chosen = [event for event in events_by_path[selected["path"]] if event["event_type"] in (
            "observation", "provider_result", "usage", "verification", "attempt_failed", "run_interrupted")][:5]
        prefix += ["Fallback: first scheduled started run; its first five public attempt/verification events.", ""]
    else:
        events = events_by_path[selected["path"]]
        delivery = next(event for event in events if event["event_type"] == "message_delivered")
        observation = next((event for event in events if event["event_type"] == "observation"
                            and event["actor"] == delivery["recipient"] and event["event_id"] > delivery["event_id"]
                            and any(item.get("event_id") == delivery["event_id"] for item in event["payload"].get("mailbox", []))), None)
        candidate = next((event for event in events if observation is not None and event["event_type"] == "verification"
                          and event["recipient"] == delivery["recipient"] and event["event_id"] > observation["event_id"]
                          and event.get("task_id") == observation.get("task_id")
                          and event["payload"].get("valid")), None)
        chosen = [event for event in (delivery, observation, candidate) if event is not None]
        if observation is None:
            prefix += ["The message was delivered, but no later receiver observation includes it.", ""]
        elif candidate is None:
            prefix += ["The receiver saw the message; no valid receiver candidate is recorded in that decision task.", ""]
        else:
            uses = [event["event_id"] for event in events if event["event_type"] == "artifact_used"
                    and event.get("task_id") == candidate.get("task_id")
                    and delivery["event_id"] in event.get("parent_event_ids", [])]
            prefix += [f"Receiver reported using this delivery in the selected candidate task: {bool(uses)}. "
                       f"Matching artifact-used event IDs: {uses}.", ""]
    prefix += [f"Run: `{selected['path']}`; repetition {selected['repetition']}; "
               f"condition {selected['condition']}; status {selected['status']}.", ""]
    for event in chosen:
        prefix += [f"## Event {event.get('event_id')}: {event['event_type']}", "",
                   f"Actor: `{event.get('actor')}`; recipient: `{event.get('recipient')}`; "
                   f"task: `{event.get('task_id')}`; elapsed: {event.get('elapsed_seconds')} seconds.", "",
                   "```json", json.dumps(event.get("payload", {}), indent=2, sort_keys=True), "```", ""]
    return "\n".join(prefix)


def analyze(campaign):
    campaign = Path(campaign)
    report = read_json(campaign / "comparison.json")
    if report is None:
        raise ValueError("Missing comparison.json.")
    sources = sorted(report["runs"], key=lambda row: row["order"])
    rows, events_by_path, curves = [], {}, []
    if len({row["path"] for row in sources}) != len(sources):
        raise ValueError("Duplicate run paths in comparison snapshot.")
    for source in sources:
        if source["condition"] not in CONDITIONS:
            raise ValueError("Unknown condition.")
        row, events, points = _row(source, campaign)
        rows.append(row)
        events_by_path[row["path"]] = events
        curves.append({key: row[key] for key in ("path", "condition", "repetition", "status")} | {"points": points})
    totals = _group(rows)
    campaign_usage = read_json(campaign / "campaign-summary.json") or report.get("usage")
    if campaign_usage is not None:
        expected = {"attempts": totals["attempts"], "total_tokens": totals["known_tokens"]}
        for key, value in expected.items():
            if campaign_usage.get(key) is not None and campaign_usage[key] != value:
                raise ValueError(f"Run totals do not match campaign ledger field {key}.")
        if _cost(campaign_usage) is not None and money(_cost(campaign_usage)) != money(totals["known_calculated_cost_usd"]):
            raise ValueError("Run calculated costs do not match campaign ledger.")
    analysis = {
        "schema_version": 1, "campaign_id": report.get("campaign_id"), "status": report.get("status"),
        "stop_reason": report.get("stop_reason"), "source_comparison_sha256": hashlib.sha256((campaign / "comparison.json").read_bytes()).hexdigest(),
        "definitions": {
            "scope": "Descriptive case study; all planned rows retained, including unstarted runs and failures.",
            "quality": "Best independently valid worker cardinality L; missing recorded values remain null. Distributions use available values only.",
            "cost": "Provider usage multiplied by frozen rates; not a billing statement. Unknown amounts remain incomplete; known subtotals include failed attempts.",
            "tokens": "Input plus output only, for attempts with complete token reporting. An incomplete attempt retains a reservation and is not represented as a zero-use call. Cache read/write are disjoint input subsets; reasoning is already in output.",
            "curves": "Recorded verification events versus cumulative latest ledger accounting in dispatch order; endpoints include all known failure costs. Incomplete endpoints show known subtotals only.",
            "coordination": "Coordinator-purpose usage is a subset of total usage. Peer content in searcher inputs has no exact causal cost attribution.",
            "denominators": "Solved means the recorded worker lower bound meets the verified upper bound; a later failed attempt does not erase an earlier solution. Run status still records failures and truncation. Solved/attempted is descriptive; failed attempts remain in costs. Cost per solution is undefined at zero successes and incomplete with unknown cost.",
        },
        "totals": totals, "conditions": {condition: _group([row for row in rows if row["condition"] == condition]) for condition in CONDITIONS},
        "campaign_usage": {key: value for key, value in campaign_usage.items() if key not in {"groups", "timeline"}} if campaign_usage else None,
        "runs": rows,
    }
    return analysis, curves, _trace(rows, events_by_path)


def plots(analysis, curves, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = {1: "#2563eb", 2: "#0f766e", 3: "#9333ea", 4: "#c2410c", 5: "#475569"}
    endpoints = {"completed": "o", "budget_stopped": "s", "failed": "X", "interrupted": "X", "running": "^"}
    for field, label, filename in (("known_tokens", "Cumulative provider-reported tokens", "quality-vs-tokens.png"),
                                    ("known_cost_usd", "Cumulative calculated cost (USD)", "quality-vs-cost.png")):
        fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), sharex=True, sharey=True, layout="constrained")
        complete_key = "tokens_complete" if field == "known_tokens" else "cost_complete"
        for condition, ax in zip(CONDITIONS, axes.flat):
            selected = [curve for curve in curves if curve["condition"] == condition and curve["points"]]
            for curve in selected:
                points = curve["points"]
                xs = [float(point[field]) for point in points]
                ys = [point["lower_bound"] for point in points]
                color = colors.get(curve["repetition"], "#334155")
                ax.step(xs, ys, where="post", color=color, alpha=.8, linewidth=1.3)
                ax.scatter(xs[-1], ys[-1], marker=endpoints.get(curve["status"], "X"), color=color, s=48, zorder=3)
                if not points[-1][complete_key]:
                    ax.annotate("incomplete", (xs[-1], ys[-1]), xytext=(4, 7), textcoords="offset points", fontsize=8, color=color)
            bounds = {row["upper_bound"] for row in analysis["runs"] if row["oracle_status"] == "optimal" and row["upper_bound"] is not None}
            for bound in bounds:
                ax.axhline(bound, color="#0f172a", linestyle="--", linewidth=.8)
                ax.text(.01, bound, f"Exact optimum {bound}", transform=ax.get_yaxis_transform(), va="bottom", fontsize=8)
            group = analysis["conditions"][condition]
            ax.set(title=f"{condition.title()} · {group['attempted_runs']}/{group['planned_runs']} runs attempted",
                   xlabel=label, ylabel="Best verified worker cardinality L", ylim=(0, max(bounds or {10}) + 1))
            ax.grid(alpha=.15)
        handles = [Line2D([0], [0], color=color, label=f"Repetition {rep}") for rep, color in colors.items()]
        handles += [Line2D([0], [0], color="#334155", marker=marker, linestyle="none", label=label)
                    for label, marker in (("Completed", "o"), ("Budget stop", "s"), ("Failed/interrupted", "X"))]
        fig.legend(handles=handles, loc="outside lower center", ncols=4, fontsize=8)
        fig.suptitle("Terra m=24 comparison · recorded quality and resource use\n"
                     "No extension beyond run endpoints; incomplete endpoints show known subtotals", fontsize=12)
        fig.savefig(output / filename, dpi=180)
        plt.close(fig)


def export(campaign, output, make_plots=False):
    campaign, output = Path(campaign), Path(output)
    if output.resolve() == campaign.resolve() or output.resolve().is_relative_to(campaign.resolve()):
        raise ValueError("Export outside the source campaign to keep its artifacts immutable.")
    analysis, curves, trace = analyze(campaign)
    output.mkdir(parents=True, exist_ok=True)
    for filename, value in (("analysis.json", analysis), ("curves.json", curves)):
        (output / filename).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    (output / "trace-annotations.md").write_text(trace)
    if analysis["runs"]:
        with (output / "runs.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(analysis["runs"][0]))
            writer.writeheader()
            for row in analysis["runs"]:
                writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    if make_plots:
        plots(analysis, curves, output)
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    result = export(args.campaign, args.out, args.plots)
    print(json.dumps({"output": str(args.out), "totals": result["totals"]}, indent=2))


if __name__ == "__main__":
    main()
