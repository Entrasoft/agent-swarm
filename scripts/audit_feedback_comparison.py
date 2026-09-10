#!/usr/bin/env python3
"""Independent public math/accounting audit; no runtime imports, network or writes."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import uuid


ARMS = ['history_feedback', 'private_best_only', 'private_best_only',
        'history_feedback', 'history_feedback', 'private_best_only']
ZERO = Decimal(0)


def read(path):
    return json.loads(path.read_text())


def valid(candidate):
    if not isinstance(candidate, list) or any(type(x) is not int or not 1 <= x <= 24 for x in candidate):
        return False
    members = set(candidate)
    return len(members) == len(candidate) and not any(
        a < b and 2*b-a in members for a in members for b in members)


def audit(directory, source_root=None):
    directory = Path(directory)
    manifest = read(directory/'manifest.json')
    report = read(directory/'feedback-campaign.json')
    ledger = read(directory/'campaign-ledger.json')
    aggregate = read(directory/'campaign-summary.json')
    entries = ledger['entries']
    failures, checks = [], 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    check(manifest['authorization_id'] == 'terra-feedback-v02-2026-09-09', 'authorization identity')
    check(manifest['limits'] == dict(call_limit=72, token_limit=600000, cost_limit='6.00'), 'campaign limits')
    check(manifest['run_limits'] == dict(call_limit=12, token_limit=100000, cost_limit='1.00'), 'run limits')
    check(len(manifest['runs']) == len(report['runs']) == len(manifest['configs']) == 6, 'all six rows')
    check([row['arm'] for row in manifest['runs']] == ARMS, 'frozen order')
    check(len({row['run_id'] for row in manifest['runs']}) == 6, 'unique run identities')
    check(ledger['campaign_id'] == report['campaign_id'] == aggregate['campaign_id'] == manifest['campaign_id'], 'campaign linkage')
    check(report['usage'] == aggregate, 'report aggregate equality')
    check(report['status'] in {'completed', 'halted'}, 'terminal campaign')
    for name, document in manifest['documents'].items():
        check(hashlib.sha256(document['text'].encode()).hexdigest() == document['sha256'], 'document digest '+name)
    source_root = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    source = source_root/'swarm_lab' if (source_root/'swarm_lab').is_dir() else source_root
    actual_sources = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')}
    check(actual_sources == manifest['source_sha256'], 'frozen runtime source hashes')
    check(manifest.get('working_tree_dirty') is False, 'clean frozen preparation')
    price = manifest['configs'][0]['price']
    check(ledger['price'] == aggregate['price'] == price, 'frozen price identity')
    rates = [Decimal(price[key]) for key in ('input_per_million', 'cached_input_per_million',
                                           'cache_write_per_million', 'output_per_million')]
    costs, tokens, unknown_cost, unknown_tokens = {}, {}, 0, 0
    check(len({entry['attempt_id'] for entry in entries}) == len(entries), 'unique attempt identities')
    for entry in entries:
        label = entry['attempt_id']
        check(entry['run_id'] in {row['run_id'] for row in manifest['runs']}, label+' owned run')
        check(entry['attempt'] == 0 and entry['agent'] == 'agent-0' and entry['purpose'] == 'research', label+' no retry/coordinator')
        check(entry['model'] == 'gpt-5.6-terra' and entry['service_tier'] == 'default' and not entry['simulated'], label+' provider identity')
        check(entry['max_output'] == 25000, label+' fixed output allowance')
        usage = entry.get('usage') or {}
        inp, out = usage.get('input_tokens'), usage.get('output_tokens')
        complete = all(type(x) is int and x >= 0 for x in (inp, out))
        check(entry['complete'] == complete, label+' token completeness')
        tokens[label] = inp+out if complete else 0
        check(entry['total_tokens'] == (inp+out if complete else None), label+' inclusive total')
        unknown_tokens += not complete
        cached = (usage.get('input_tokens_details') or {}).get('cached_tokens')
        written = (usage.get('input_tokens_details') or {}).get('cache_write_tokens')
        reasoning = (usage.get('output_tokens_details') or {}).get('reasoning_tokens')
        for subset, whole, field in ((cached, inp, 'cache reads'), (written, inp, 'cache writes'), (reasoning, out, 'reasoning')):
            check(subset is None or type(subset) is int and subset >= 0 and (whole is None or subset <= whole), label+' '+field)
        if complete:
            check(cached is None or written is None or cached+written <= inp, label+' disjoint cache input')
            check(usage.get('total_tokens') in (None, inp+out), label+' provider total')
        calculated = None
        if complete and (inp == 0 or cached is not None and written is not None):
            cached, written = cached or 0, written or 0
            calculated = ((inp-cached-written)*rates[0]+cached*rates[1]+written*rates[2]+out*rates[3])/1000000
        actual = Decimal(entry['observed_cost']) if entry['observed_cost'] is not None else None
        check(calculated == actual, label+' independently calculated cost')
        costs[label] = calculated or ZERO
        unknown_cost += calculated is None
        check(entry['reconciled_cost'] is None, label+' billing remains unreconciled')
        partial_input = max(entry['input_estimate'], inp if type(inp) is int and inp >= 0 else 0)
        partial_output = max(entry['max_output'], out if type(out) is int and out >= 0 else 0)
        if not complete or calculated is None:
            minimum_hold = (partial_input*max(rates[:3])+partial_output*rates[3])/1000000
            check(Decimal(entry['reserved_cost']) >= minimum_hold, label+' unknown cost retains hold')
        if not complete:
            check(entry['reserved_tokens'] >= partial_input+partial_output, label+' unknown tokens retain hold')
        if complete and calculated is not None:
            check(entry['reserved_tokens'] == 0 and Decimal(entry['reserved_cost']) == 0, label+' known settlement')

    def check_usage(items, usage, call_limit, token_limit, cost_limit, label):
        total = sum(tokens[e['attempt_id']] for e in items)
        cost = sum((costs[e['attempt_id']] for e in items), ZERO)
        held_tokens = sum(e['reserved_tokens'] for e in items)
        held_cost = sum((Decimal(e['reserved_cost']) for e in items), ZERO)
        check(usage['attempts'] == usage['actual_calls'] == len(items), label+' attempt count')
        check(usage['total_tokens'] == total and Decimal(usage['observed_cost']) == cost, label+' known totals')
        check(usage['reserved_tokens'] == held_tokens and Decimal(usage['reserved_cost']) == held_cost, label+' reserves')
        check(usage['committed_tokens'] == total+held_tokens and Decimal(usage['committed_cost']) == cost+held_cost, label+' commitments')
        check(len(items) <= call_limit and total+held_tokens <= token_limit and cost+held_cost <= Decimal(cost_limit), label+' all ceilings')
        complete_cost = all(entry['observed_cost'] is not None for entry in items)
        calculated = usage.get('calculated_model_cost')
        check((Decimal(calculated) == cost if calculated is not None else not complete_cost)
              and (calculated is not None) == complete_cost, label+' calculated cost completeness')
        check(usage.get('actual_model_cost') == (None if items else '0')
              and usage.get('billing_status') == 'not_reconciled', label+' billing uncertainty')

    check_usage(entries, aggregate, 72, 600000, '6.00', 'campaign')
    check(aggregate['unknown_attempts'] == unknown_tokens and aggregate['unknown_cost_attempts'] == unknown_cost, 'unknown counts')
    check(not (unknown_tokens or unknown_cost) or report['status'] == 'halted', 'uncertainty halts campaign')
    output_rows, all_clients = [], set()
    for index, (planned, row, config) in enumerate(zip(manifest['runs'], report['runs'], manifest['configs'])):
        path = directory/planned['path']
        check(all(row.get(key) == value for key, value in planned.items() if key != 'status'), 'row identity '+str(index))
        check(config['memory_mode'] == ARMS[index] and config['decision_protocol'] == 'feedback-v0.2', 'arm configuration '+str(index))
        for key, value in dict(m=24, agents=1, condition='solo', steps=12, concurrency=1,
                               max_retries=0, max_output=25000, model='gpt-5.6-terra',
                               reasoning_effort='medium', history_limit=8, context_bytes=16384).items():
            check(config[key] == value, f'config {index} {key}')
        owned = [entry for entry in entries if entry['run_id'] == row['run_id']]
        check_usage(owned, aggregate['groups']['run_id'][row['run_id']], 12, 100000, '1.00', row['path'])
        if row['status'] == 'unstarted':
            check(not owned and not path.exists(), row['path']+' absent unstarted data')
            output_rows.append(dict(path=row['path'], status='unstarted', unique_valid_candidates=None, lower_bound=None))
            continue
        events_path = path/'events.jsonl'
        events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
        if (path/'config.json').is_file():
            saved = read(path/'config.json')
            check(all(saved.get(key) == value for key, value in config.items()), row['path']+' frozen configuration')
            check(saved.get('run_id') == row['run_id'] and saved.get('campaign_id') == manifest['campaign_id'], row['path']+' frozen runtime identity')
            check(saved.get('source_sha256') == manifest['source_sha256']
                  and saved.get('code_revision') == manifest['code_revision']
                  and saved.get('working_tree_dirty') is False, row['path']+' frozen runtime revision')
            starts = [event for event in events if event['event_type'] == 'run_started']
            check(len(starts) == 1 and starts[0]['payload'] == saved, row['path']+' run started metadata')
        else:
            check(not owned and row['status'] == 'interrupted', row['path']+' missing configuration requires pre-dispatch interruption')
        seen, candidates, count, verified_count, lower, requests = set(), set(), 0, 0, 0, {}
        for event in events:
            check(event['event_id'] == len(seen)+1 and all(p in seen for p in event['parent_event_ids']), row['path']+' causal event order')
            seen.add(event['event_id'])
            payload = event['payload']
            if event['event_type'] == 'provider_request':
                identity = payload['client_request_id']
                check(str(uuid.UUID(identity)) == identity and identity not in all_clients, 'unique client correlation')
                all_clients.add(identity)
                requests[payload['attempt_id']] = identity
            elif event['event_type'] in {'provider_result', 'provider_failure'}:
                check(requests.get(payload['attempt_id']) == payload['client_request_id'], 'response linked to prior dispatch')
            elif event['event_type'] == 'verification':
                verified_count += 1
                okay = valid(payload['candidate'])
                check(payload['valid'] == okay, 'independent mathematical verification')
                if okay:
                    candidates.add(tuple(sorted(payload['candidate'])))
                    count += 1
                    lower = max(lower, len(payload['candidate']))
                check(payload['lower_bound'] == lower, 'verified progress only')
        check(set(requests) == {e['attempt_id'] for e in owned}, row['path']+' every attempted dispatch recorded')
        if (path/'summary.json').is_file():
            summary = read(path/'summary.json')
            check(row.get('summary') == summary, row['path']+' published summary equality')
            check(summary['lower_bound'] == lower, row['path']+' terminal verified bound')
            for key, value in dict(unique_valid_candidates=len(candidates), verification_count=verified_count,
                                   valid_candidate_count=count, invalid_mathematical_candidates=verified_count-count).items():
                check(row.get(key) == value, row['path']+' published '+key)
            if any(e['event_type'] == 'run_finished' for e in events):
                check(summary['unique_valid_candidates'] == len(candidates), row['path']+' primary diversity')
                check(summary['duplicate_candidates'] == count-len(candidates), row['path']+' valid duplicates')
        output_rows.append(dict(path=row['path'], status=row['status'], unique_valid_candidates=len(candidates),
                                lower_bound=lower if count else None, valid_submissions=count))
    return dict(audit_passed=not failures, checks=checks, failures=failures,
                source_revision=manifest['code_revision'], campaign_status=report['status'], attempts=len(entries),
                known_tokens=sum(tokens.values()), independently_calculated_known_cost_usd=str(sum(costs.values(), ZERO)),
                unknown_token_attempts=unknown_tokens, unknown_cost_attempts=unknown_cost,
                client_correlations=len(all_clients), runs=output_rows,
                note='Public mathematical/accounting consistency audit, not log authentication or billing reconciliation. Runtime replay separately checks feedback observations and provenance.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    result = audit(args.campaign, args.source_root)
    print(json.dumps(result, indent=2))
    return 0 if result['audit_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
