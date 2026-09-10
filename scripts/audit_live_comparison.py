#!/usr/bin/env python3
"""Read-only, independent audit. No swarm_lab imports, credentials or network.

Enumerates all valid subsets independently, then checks frozen scope, public
exports, candidate verification and observation isolation. The raw SQLite
ledger is additionally audited when present; --require-sqlite makes it required.
The campaign must already be completed or halted. Nothing is written. Runtime
sources must match the frozen hashes; --source-root can identify their checkout.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import time


EXPECTED_REVISION = "4a30a2519491f355c60bcaa19799ab14010e71ab"
ORDER = ["independent", "fixed", "adaptive", "solo", "fixed", "adaptive", "independent", "solo",
         "independent", "solo", "adaptive", "fixed", "solo", "adaptive", "fixed", "independent",
         "fixed", "solo", "independent", "adaptive"]
ZERO = Decimal(0)
MILLION = Decimal(1_000_000)


def enumerate_subsets(m=24):
    """Every increasing valid prefix appears once; prune only a forbidden AP."""
    counts = [0] * (m + 1)
    largest = []
    best = 0
    started = time.perf_counter()

    def visit(chosen, first, forbidden):
        nonlocal best, largest
        size = len(chosen)
        counts[size] += 1
        if size > best:
            best, largest = size, [chosen]
        elif size == best:
            largest.append(chosen)
        for b in range(first, m + 1):
            if forbidden & (1 << b):
                continue
            blocked = forbidden
            for a in chosen:
                c = 2 * b - a
                if c <= m:
                    blocked |= 1 << c
            visit(chosen + (b,), b + 1, blocked)

    visit((), 1, 0)
    return dict(m=m, optimum=best, maximum_subsets=counts[best],
                valid_subsets=sum(counts), counts_by_cardinality=counts,
                maximum_candidates=[list(values) for values in largest],
                elapsed_seconds=time.perf_counter() - started)


def candidate_valid(candidate, m=24):
    if not isinstance(candidate, list) or any(type(a) is not int or not 1 <= a <= m for a in candidate):
        return False
    if len(set(candidate)) != len(candidate):
        return False
    values = set(candidate)
    return not any(2 * b - a in values for a in values for b in values if a < b)


def read_json(path):
    return json.loads(path.read_text())


def amount(value):
    return Decimal(str(value)) if value is not None else ZERO


def counters_and_cost(raw, price):
    """Calculate inclusive totals and disjoint cache pricing from raw usage."""
    if not isinstance(raw, dict):
        return None, None
    counters = {}
    for name in ("input_tokens", "output_tokens"):
        value = raw.get(name)
        if type(value) is not int or value < 0:
            return None, None
        counters[name] = value
    input_details = raw.get("input_tokens_details") or {}
    output_details = raw.get("output_tokens_details") or {}
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        return None, None
    for name, value in (("cached_input_tokens", input_details.get("cached_tokens")),
                        ("cache_write_tokens", input_details.get("cache_write_tokens")),
                        ("reasoning_tokens", output_details.get("reasoning_tokens"))):
        if value is not None and (type(value) is not int or value < 0):
            return None, None
        counters[name] = value
    total_input, total_output = counters["input_tokens"], counters["output_tokens"]
    cached, written, reasoning = (counters[key] for key in
                                  ("cached_input_tokens", "cache_write_tokens", "reasoning_tokens"))
    if (cached or 0) + (written or 0) > total_input or (reasoning or 0) > total_output:
        return None, None
    counters["total_tokens"] = total_input + total_output
    if total_input and (cached is None or written is None):
        return counters, None
    cached, written = cached or 0, written or 0
    calculated = ((total_input - cached - written) * amount(price["input_per_million"])
                  + cached * amount(price["cached_input_per_million"])
                  + written * amount(price["cache_write_per_million"])
                  + total_output * amount(price["output_per_million"])) / MILLION
    return counters, calculated


def find_source_root(directory, requested=None):
    if requested is not None:
        repository = Path(requested).resolve()
        source = repository if repository.name == "swarm_lab" else repository / "swarm_lab"
        if not source.is_dir():
            raise ValueError("--source-root does not contain the frozen swarm_lab runtime sources.")
        return source
    for location in (directory, Path(__file__).resolve().parent):
        for ancestor in (location, *location.parents):
            if (ancestor / "swarm_lab").is_dir():
                return ancestor / "swarm_lab"
    raise ValueError("Runtime sources were not found; provide --source-root for a checkout of the frozen revision.")


def audit(directory, *, require_sqlite=False, source_root=None):
    directory = Path(directory).resolve()
    manifest = read_json(directory / "manifest.json")
    report = read_json(directory / "comparison.json")
    if report.get("status") not in {"completed", "halted"}:
        raise RuntimeError("Campaign is still active; run the audit only after final completion or halt.")
    independent = enumerate_subsets()
    failures = []
    checks = 0

    def check(condition, explanation):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(explanation)

    check(manifest["code_revision"] == EXPECTED_REVISION, "Unexpected frozen source revision")
    check(manifest["limits"] == dict(call_limit=240, token_limit=2_000_000, cost_limit="20.00"), "Campaign ceiling changed")
    check(manifest["run_limits"] == dict(call_limit=12, token_limit=100_000, cost_limit="1.00"), "Run allocation changed")
    check(manifest["schedule_seed"] == 20260909, "Schedule seed changed")
    check(len(manifest["runs"]) == len(report["runs"]) == 20, "Not all twenty planned rows retained")
    check([row["condition"] for row in manifest["runs"]] == ORDER, "Frozen order differs from approval")
    check([row["condition"] for row in report["runs"]] == ORDER, "Actual report rows differ from frozen order")
    check(hashlib.sha256(manifest["protocol"].encode()).hexdigest() == manifest["protocol_sha256"], "Frozen protocol digest differs")
    source_root = find_source_root(directory, source_root)
    for name, digest in manifest["source_sha256"].items():
        source_path = source_root / name
        check(source_path.is_file() and hashlib.sha256(source_path.read_bytes()).hexdigest() == digest,
              "Runtime source missing or changed: " + name)

    campaign_ledger = read_json(directory / "campaign-ledger.json")
    campaign_summary = read_json(directory / "campaign-summary.json")
    price = campaign_ledger["price"]
    for field, expected in (("input_per_million", "2"), ("cached_input_per_million", "0.2"),
                            ("cache_write_per_million", "2.5"), ("output_per_million", "12")):
        check(amount(price[field]) == amount(expected), "Frozen tariff differs: " + field)
    check(price["model"] == "gpt-5.6-terra" and price["service_tier"] == "default", "Model/tier tariff mismatch")
    check(campaign_summary == report["usage"], "Final campaign summary differs from final report")

    expected_ids = {row["run_id"] for row in manifest["runs"]}
    exported = {row["attempt_id"]: row for row in campaign_ledger["entries"]}
    check(len(exported) == len(campaign_ledger["entries"]) <= 240, "Duplicate exported attempts or attempt ceiling exceeded")
    check(set(campaign_ledger["run_ids"]) == expected_ids, "Export dropped unstarted allocations")
    groups = campaign_summary["groups"]["run_id"]
    check(set(groups) == expected_ids, "Campaign summary dropped planned allocations")
    for row in groups.values():
        check(row["token_limit"] == 100_000 and amount(row["cost_limit"]) == 1 and not row["simulated"],
              "Unequal or simulated exported allocation")

    sqlite_path = directory / "usage.sqlite3"
    sqlite_audited = sqlite_path.is_file()
    if require_sqlite and not sqlite_audited:
        raise ValueError("--require-sqlite was specified but usage.sqlite3 is absent.")
    receipt = None
    if sqlite_audited:
        # Read-only URI: no ledger constructors, journal resets, exports or migrations.
        with sqlite3.connect(sqlite_path.as_uri() + "?mode=ro", uri=True) as database:
            database.row_factory = sqlite3.Row
            database.execute("BEGIN")
            raw_runs = [dict(row) for row in database.execute("SELECT * FROM runs")]
            entries = [dict(row) for row in database.execute("SELECT * FROM attempts ORDER BY created_at,attempt_id")]
            membership = [dict(row) for row in database.execute("SELECT * FROM campaign_runs")]
            stored_campaign = dict(database.execute("SELECT * FROM campaigns WHERE campaign_id=?", (manifest["campaign_id"],)).fetchone())
            receipt = database.execute("SELECT * FROM comparison_preparations").fetchone()
        check(stored_campaign["call_limit"] == 240 and stored_campaign["token_limit"] == 2_000_000
              and amount(stored_campaign["cost_limit"]) == 20, "SQLite campaign ceilings differ")
        check(not stored_campaign["simulated"], "Live campaign incorrectly marked simulated")
        check(len(raw_runs) == len(membership) == 20, "SQLite does not retain twenty run allocations")
        check({row["run_id"] for row in raw_runs} == expected_ids, "SQLite run IDs differ from manifest")
        check({row["run_id"] for row in membership} == expected_ids, "SQLite membership differs from manifest")
        check(all(row["campaign_id"] == manifest["campaign_id"] for row in membership), "Unexpected campaign membership")
        for row in raw_runs:
            check(row["token_limit"] == 100_000 and amount(row["cost_limit"]) == 1 and not row["simulated"],
                  "Unequal or simulated SQLite allocation")
        check(set(exported) == {row["attempt_id"] for row in entries}, "SQLite/export attempt identities differ")
        check(len(exported) == len(entries) <= 240, "Duplicate SQLite attempts or attempt ceiling exceeded")
        for entry in entries:
            entry["usage"] = json.loads(entry.pop("usage_json")) if entry["usage_json"] else None
            entry["normalized"] = json.loads(entry.pop("normalized_json"))
    else:
        entries = sorted(campaign_ledger["entries"], key=lambda entry: (entry["created_at"], entry["attempt_id"]))

    # The integrity receipt freezes all manifest fields, not just controls.
    if receipt is not None:
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        receipt_values = dict(receipt).values()
        check(hashlib.sha256(canonical).hexdigest() in receipt_values, "Durable manifest receipt differs")

    by_run = defaultdict(list)
    total_tokens = 0
    total_cost = ZERO
    unknown_tokens = unknown_cost = 0
    returned_usage = {}
    per_run_totals = defaultdict(lambda: dict(tokens=0, cost=ZERO, unknown_tokens=0, unknown_cost=0))
    for entry in entries:
        label = entry["attempt_id"]
        by_run[entry["run_id"]].append(entry)
        public = exported[label]
        check(entry["attempt"] == 0, "Retry appeared: " + label)
        check(entry["model"] == "gpt-5.6-terra" and entry["service_tier"] == "default", "Ledger model/tier changed: " + label)
        check(entry["max_output"] == 25_000, "Output headroom changed: " + label)
        estimate = entry["input_estimate"] + entry["max_output"]
        estimate_cost = (entry["input_estimate"] * max(amount(price[k]) for k in
                         ("input_per_million", "cached_input_per_million", "cache_write_per_million"))
                         + entry["max_output"] * amount(price["output_per_million"])) / MILLION
        check(entry["estimated_tokens"] == estimate, "Reservation token arithmetic differs: " + label)
        check(amount(entry["estimated_cost"]) == estimate_cost, "Reservation cost arithmetic differs: " + label)
        known_run = per_run_totals[entry["run_id"]]
        # Dispatch is globally sequential; every earlier charge has settled.
        check(known_run["tokens"] + estimate <= 100_000, "Attempt admitted without run token headroom: " + label)
        check(known_run["cost"] + estimate_cost <= 1, "Attempt admitted without run cost headroom: " + label)
        check(total_tokens + estimate <= 2_000_000, "Attempt admitted without campaign token headroom: " + label)
        check(total_cost + estimate_cost <= 20, "Attempt admitted without campaign cost headroom: " + label)
        check(not unknown_tokens and not unknown_cost, "Dispatch continued after unresolved usage: " + label)
        usage = entry.get("usage")
        normalized = entry["normalized"]
        counts, calculated = counters_and_cost(usage, price)
        check(normalized["complete"] == (counts is not None), "Raw usage completeness differs from normalized ledger: " + label)
        if counts is not None:
            for field, value in counts.items():
                check(normalized[field] == value and public[field] == value, "Raw/exported token accounting differs: " + label + " " + field)
            total_tokens += counts["total_tokens"]
            known_run["tokens"] += counts["total_tokens"]
        else:
            unknown_tokens += 1
            known_run["unknown_tokens"] += 1
            check(entry["reserved_tokens"] > 0, "Unknown attempt has no token reservation: " + label)
        check((entry["observed_cost"] is None) == (calculated is None), "Calculated cost completeness differs: " + label)
        if calculated is not None:
            check(amount(entry["observed_cost"]) == calculated == amount(public["observed_cost"]), "Independent price arithmetic differs: " + label)
            total_cost += calculated
            known_run["cost"] += calculated
        else:
            unknown_cost += 1
            known_run["unknown_cost"] += 1
            check(amount(entry["reserved_cost"]) > 0 or entry["reconciled_cost"] is not None, "Unknown cost has no reservation: " + label)
        for field in ("run_id", "agent", "task_id", "purpose", "attempt", "outcome", "status", "reserved_tokens"):
            check(entry[field] == public[field], "SQLite/export field differs: " + label + " " + field)
        returned_usage[(entry["run_id"], entry["task_id"])] = usage

    check(total_tokens == campaign_summary["total_tokens"], "Independent campaign token sum differs")
    check(total_cost == amount(campaign_summary["observed_cost"]), "Independent campaign calculated-cost sum differs")
    check(unknown_tokens == campaign_summary["unknown_attempts"], "Independent unknown-token count differs")
    check(len(entries) == campaign_summary["actual_calls"] == campaign_summary["attempts"], "Campaign attempt total differs")
    check(campaign_summary["retry_attempts"] == 0 and campaign_summary["simulated_calls"] == 0, "Retry or simulated calls present")
    check(total_tokens <= 2_000_000 and total_cost <= 20, "Observed campaign ceiling exceeded")

    candidate_count = invalid_candidates = delivered_count = 0
    row_results = []
    for position, (planned, row, config) in enumerate(zip(manifest["runs"], report["runs"], manifest["configs"])):
        name = row["path"]
        for key, value in planned.items():
            check(row.get(key) == value, "Report changed frozen run field: " + name + " " + key)
        check(planned["repetition"] == position // 4 + 1 and planned["seed"] == position // 4, "Run block or seed changed: " + name)
        check(config["m"] == 24 and config["steps"] == 12 and config["max_retries"] == 0
              and config["concurrency"] == 1 and config["max_output"] == 25_000
              and config["reasoning_effort"] == "medium" and config["timeout_seconds"] == 120,
              "Controlled run settings changed: " + name)
        run_entries = by_run[row["run_id"]]
        check(len(run_entries) <= 12, "Run attempt ceiling exceeded: " + name)
        expected_agents = ["agent-0"] * len(run_entries) if row["condition"] == "solo" else ["agent-" + str(i % 4) for i in range(len(run_entries))]
        check([entry["agent"] for entry in run_entries] == expected_agents, "Attempt order or allocation changed: " + name)
        check([entry["task_id"] for entry in run_entries] == ["task-" + str(i) for i in range(len(run_entries))], "Decision task sequence differs: " + name)
        for entry in run_entries:
            coordination = row["condition"] in {"fixed", "adaptive"} and entry["agent"] == "agent-0"
            check(entry["purpose"] == ("coordination" if coordination else "research"), "Coordinator accounting differs: " + name)
        if row["status"] == "unstarted":
            check(not run_entries and "summary" not in row, "Unstarted run acquired attempts or invented quality: " + name)
            row_results.append(dict(path=name, status="unstarted", attempts=0, lower_bound=None, gap=None))
            continue
        run_directory = directory / name
        events_path = run_directory / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()] if events_path.exists() else []
        summary = row.get("summary") or (read_json(run_directory / "summary.json") if (run_directory / "summary.json").exists() else {})
        ids = [event["event_id"] for event in events]
        check(ids == sorted(set(ids)), "Public events repeat or reverse: " + name)
        events_by_id = {event["event_id"]: event for event in events}
        private_best = defaultdict(list)
        per_agent_calls = Counter()
        completed = Counter()
        best = []
        verified = 0
        seen = set()
        duplicates = 0
        for event in events:
            kind, payload = event["event_type"], event.get("payload", {})
            actor = event.get("actor")
            if kind == "observation":
                check(set(payload) == {"m", "agent_id", "role", "round", "private_best", "mailbox", "peers", "condition", "task_id"}, "Observation exposes unapproved fields: " + name)
                check(payload["private_best"] == private_best[actor], "Private context differs from own prior candidate: " + name)
                check(payload["round"] == per_agent_calls[actor], "Outcome-dependent scheduling or round changed: " + name)
                if row["condition"] in {"solo", "independent"}:
                    check(payload["mailbox"] == [], "Information delivered in isolated condition: " + name)
                for message in payload["mailbox"]:
                    delivered = events_by_id.get(message["event_id"], {})
                    check(delivered.get("event_type") == "message_delivered" and delivered.get("recipient") == actor
                          and message["event_id"] < event["event_id"], "Observation message was not delivered earlier to receiver: " + name)
            elif kind == "provider_result":
                if payload.get("outcome") not in {"unexpected_model", "unexpected_service_tier"}:
                    check(payload.get("model") == "gpt-5.6-terra" and payload.get("service_tier") == "default", "Unresolved returned model/tier: " + name)
            elif kind == "verification":
                candidate_count += 1
                candidate = payload.get("candidate")
                valid = candidate_valid(candidate)
                check(valid == payload.get("valid"), "Independent candidate verification disagrees: " + name + " event " + str(event["event_id"]))
                verified += 1
                if valid:
                    values = sorted(candidate)
                    key = tuple(values)
                    duplicates += key in seen
                    seen.add(key)
                    receiver = event["recipient"]
                    if len(values) > len(private_best[receiver]):
                        private_best[receiver] = values
                    if len(values) > len(best):
                        best = values
                else:
                    invalid_candidates += 1
                check(payload.get("lower_bound") == len(best), "Recorded lower-bound progression differs: " + name)
            elif kind in {"task_completed", "task_failed"}:
                per_agent_calls[actor] += 1
                if kind == "task_completed":
                    completed[actor] += 1
            elif kind == "message_sent":
                check(row["condition"] in {"fixed", "adaptive"}, "Forbidden message sent in isolated condition: " + name)
                if row["condition"] == "fixed":
                    check(actor == "agent-0" or event.get("recipient") == "agent-0", "Fixed topology violated: " + name)
                content = payload.get("content")
                if isinstance(content, dict) and "candidate" in content:
                    check(candidate_valid(content["candidate"]), "Invalid candidate passed trusted message validation: " + name)
            elif kind == "message_delivered":
                delivered_count += 1
                sent = [events_by_id.get(parent, {}) for parent in event.get("parent_event_ids", [])]
                check(any(parent.get("event_type") == "message_sent" and parent.get("actor") == actor
                          and parent.get("recipient") == event.get("recipient") for parent in sent), "Delivery lacks matching send event: " + name)
        if summary:
            check(summary.get("lower_bound") == len(best), "Final worker quality differs from verified events: " + name)
            if summary.get("gap") is not None:
                check(summary.get("upper_bound") == independent["optimum"], "Run oracle upper bound differs from independent enumeration: " + name)
                check(summary["gap"] == independent["optimum"] - len(best), "Final gap differs from independent quality: " + name)
            if "best_candidate" in summary:
                check(candidate_valid(summary["best_candidate"]) and len(summary["best_candidate"]) == len(best), "Final best candidate invalid or wrong length: " + name)
            if "decisions_completed" in summary:
                check(summary["decisions_completed"] == sum(completed.values()), "Completed decision count differs: " + name)
            if "duplicate_candidates" in summary:
                check(summary["duplicate_candidates"] == duplicates, "Duplicate count differs: " + name)
            if row["status"] == "completed":
                check(len(run_entries) == 12, "Completed run lacks twelve calls: " + name)
            if row["status"] == "failed":
                check(bool(row.get("failure")), "Failed row lost failure despite measurable quality: " + name)
            run_summary = campaign_summary["groups"]["run_id"][row["run_id"]]
            independently = per_run_totals[row["run_id"]]
            check(run_summary["total_tokens"] == independently["tokens"], "Per-run independent token sum differs: " + name)
            check(amount(run_summary["observed_cost"]) == independently["cost"], "Per-run independent cost sum differs: " + name)
        row_results.append(dict(path=name, status=row["status"], attempts=len(run_entries),
                                lower_bound=summary.get("lower_bound"), gap=summary.get("gap"),
                                candidate_verifications=verified, per_agent_calls=dict(per_agent_calls)))

    return dict(audit_passed=not failures, checks=checks, failures=failures,
                sqlite_audited=sqlite_audited, manifest_receipt_audited=receipt is not None,
                independent_enumeration=independent, campaign_status=report["status"],
                attempts=len(entries), provider_tokens=total_tokens,
                independently_calculated_cost_usd=str(total_cost), unknown_token_attempts=unknown_tokens,
                unknown_calculated_cost_attempts=unknown_cost, candidate_verifications=candidate_count, valid_candidates=candidate_count-invalid_candidates,
                invalid_candidates=invalid_candidates, delivered_messages=delivered_count, runs=row_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]/"examples"/"terra-comparison")
    parser.add_argument("--optimum-only", action="store_true")
    parser.add_argument("--require-sqlite", action="store_true",
                        help="Require the local raw SQLite ledger in addition to public evidence.")
    parser.add_argument("--source-root", type=Path,
                        help="Repository checkout or swarm_lab directory matching the frozen source hashes.")
    args = parser.parse_args()
    if args.optimum_only:
        print(json.dumps(enumerate_subsets(), indent=2))
    else:
        result = audit(args.campaign, require_sqlite=args.require_sqlite, source_root=args.source_root)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["audit_passed"] else 1)
