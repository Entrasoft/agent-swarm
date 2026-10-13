"""Coordination v0.3, Stage 0: table snapshot and frozen target selection.

`snapshot` downloads the best-known linear code bounds for GF(3) and GF(4) from
codetables.de and stores the parsed entries with page hashes. `select` applies
the rule fixed in docs/coordination-v03-proposal.md to that snapshot: open
entries (lower < upper) within the verification limits and 2k <= n <= 4k, drawn
in a seeded random order, keeping the first six whose entry pages show no sign
of an AI-produced or recent record. Page content is parsed as data only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import random
import re
import time
import urllib.request

from .store import write_json

SOURCE = 'https://www.codetables.de'
TABLE_URL = SOURCE + '/BKLC/Tables.php?q={q}&n0=1&n1={n1}&k0=1&k1={k1}'
ENTRY_URL = SOURCE + '/BKLC/BKLC.php?q={q}&n={n}&k={k}'
TABLE_RANGES = {3: (243, 14), 4: (256, 12)}

# Exact enumeration takes at most about one second per candidate at these
# dimensions (profiled 2026-10-10, Apple M3 Max, Python 3.12.8): GF(3) k=14
# 0.48 s and k=15 1.4 s; GF(4) k=12 0.59 s and k=13 2.3 s.
VERIFY_LIMITS = {3: 14, 4: 12}
SELECTION_SEED = 20261010
TARGET_COUNT = 6
RECENT_CUTOFF = '2023-01-01'
AI_TERMS = re.compile(
    r'language model|\bLLM|\bGPT|AlphaEvolve|FunSearch|Evolve\b|neural|machine learning|'
    r'artificial intelligence|\bAI\b|reinforcement learning', re.IGNORECASE)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'agent-swarm-lab/0.3 (research snapshot)'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def page_text(raw: bytes) -> str:
    text = re.sub(r'<[^>]+>', ' ', raw.decode('latin-1'))
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def parse_table(q: int, raw: bytes) -> list[dict]:
    """Every (n, k) cell: a single value d, or a range lower-upper."""
    entries = []
    pattern = r'title="n=(\d+), k=(\d+)"[^>]*>\s*(\d+)\s*(?:-\s*(\d+))?\s*</A>'
    for n, k, lower, upper in re.findall(pattern, raw.decode('latin-1')):
        entries.append(dict(q=q, n=int(n), k=int(k), lower=int(lower),
                            upper=int(upper) if upper else int(lower)))
    return entries


def parse_entry(raw: bytes) -> dict:
    """Bounds, last-modified date and construction text from one entry page."""
    text = page_text(raw)
    bounds = re.search(r'lower bound:\s*(\d+)\s*upper bound:\s*(\d+)', text)
    modified = re.search(r'last modified:\s*(\d{4}-\d{2}-\d{2})', text)
    construction = text.split('Construction', 1)[-1].split(' Notes ', 1)[0]
    return dict(lower=int(bounds.group(1)) if bounds else None,
                upper=int(bounds.group(2)) if bounds else None,
                last_modified=modified.group(1) if modified else None,
                ai_terms=sorted({match.group(0) for match in AI_TERMS.finditer(construction)}))


def qualifies(entry: dict) -> bool:
    q, n, k = entry['q'], entry['n'], entry['k']
    return (q in VERIFY_LIMITS and entry['lower'] < entry['upper']
            and k <= VERIFY_LIMITS[q] and 2 * k <= n <= 4 * k)


def entry_rejection(entry: dict, details: dict) -> str | None:
    if details['lower'] != entry['lower'] or details['upper'] != entry['upper']:
        return 'entry page bounds differ from the table snapshot'
    if details['ai_terms']:
        return 'construction mentions ' + ', '.join(details['ai_terms'])
    if details['last_modified'] is None:
        return 'no last-modified date'
    if details['last_modified'] >= RECENT_CUTOFF:
        return f'modified on or after {RECENT_CUTOFF}'
    return None


def select(snapshot: dict, fetch_entry=None) -> dict:
    """Apply the frozen rule. fetch_entry(q, n, k) returns raw entry-page bytes."""
    fetch_entry = fetch_entry or (lambda q, n, k: fetch(ENTRY_URL.format(q=q, n=n, k=k)))
    pool = sorted((e for e in snapshot['entries'] if qualifies(e)),
                  key=lambda e: (e['q'], e['n'], e['k']))
    order = list(pool)
    random.Random(SELECTION_SEED).shuffle(order)
    selected, examined = [], []
    for entry in order:
        if len(selected) == TARGET_COUNT:
            break
        raw = fetch_entry(entry['q'], entry['n'], entry['k'])
        details = parse_entry(raw)
        reason = entry_rejection(entry, details)
        record = dict(entry, url=ENTRY_URL.format(**entry), sha256=hashlib.sha256(raw).hexdigest(),
                      last_modified=details['last_modified'], rejection=reason)
        examined.append(record)
        if reason is None:
            selected.append(record)
    return dict(rule=dict(seed=SELECTION_SEED, count=TARGET_COUNT, verify_limits=VERIFY_LIMITS,
                          length_range='2k <= n <= 4k', recent_cutoff=RECENT_CUTOFF,
                          ai_terms=AI_TERMS.pattern),
                snapshot_retrieved=snapshot['retrieved'], qualifying=len(pool),
                selected_at=datetime.now(timezone.utc).isoformat(),
                examined=examined, targets=selected,
                fallback_required=len(selected) < TARGET_COUNT)


def take_snapshot() -> dict:
    tables, entries = [], []
    for q, (n1, k1) in TABLE_RANGES.items():
        url = TABLE_URL.format(q=q, n1=n1, k1=k1)
        raw = fetch(url)
        parsed = parse_table(q, raw)
        tables.append(dict(q=q, url=url, sha256=hashlib.sha256(raw).hexdigest(), cells=len(parsed)))
        entries.extend(parsed)
        time.sleep(1)
    return dict(source=SOURCE, retrieved=datetime.now(timezone.utc).isoformat(),
                tables=tables, entries=entries)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='swarm_lab.v03_targets', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot', help='Download and store the bounds tables')
    snap.add_argument('--out', type=Path, required=True)
    pick = sub.add_parser('select', help='Apply the frozen target rule to a stored snapshot')
    pick.add_argument('--snapshot', type=Path, required=True)
    pick.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.exit(2, f'Error: {args.out} already exists; snapshots and selections are write-once.\n')
    if args.command == 'snapshot':
        result = take_snapshot()
        write_json(args.out, result)
        print(json.dumps({'out': str(args.out), 'entries': len(result['entries'])}))
    else:
        result = select(json.loads(args.snapshot.read_text()))
        write_json(args.out, result)
        print(json.dumps({'out': str(args.out), 'qualifying': result['qualifying'],
                          'targets': [(t['q'], t['n'], t['k'], t['lower'], t['upper']) for t in result['targets']],
                          'fallback_required': result['fallback_required']}, indent=2))


if __name__ == '__main__':
    main()
