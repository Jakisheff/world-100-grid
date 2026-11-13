#!/usr/bin/env python3
"""Export world-100 game directories to the self-verifying dataset package.

Reads local world-run directories (calls/, phases/, snapshots/, frozen.json)
and writes two parquet splits plus checksums:

- decisions.parquet: one row per accepted bribe decision with the full
  offered menu, visible opponent cash, chosen target, verified receipt and
  provenance (seed, arm, digests). Everything the permutation and paired
  analyses need is in the rows.
- games.parquet: one row per game with accepted/rejected/skipped counts,
  recomputed concentration metrics, digests and escalation tier.

Schema: world-100-grid v1 (see DATACARD.md). reward_basis: ENGINE_REPLAY.
"""
import json, hashlib, sys, glob, os
from pathlib import Path

GRID = Path(sys.argv[1] if len(sys.argv) > 1 else
            '/var/folders/ym/7w5t9pjn0l9fslyn7bznw78c0000gn/T/opencode/alashi-grid')
EXTRA = {'/var/folders/ym/7w5t9pjn0l9fslyn7bznw78c0000gn/T/opencode/alashi-l4/world':
         ('l4', 20261109, 'l4-20261109-original')}
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else
           '/var/folders/ym/7w5t9pjn0l9fslyn7bznw78c0000gn/T/opencode/world-100-grid/data')
OUT.mkdir(parents=True, exist_ok=True)
ALASHI_COMMIT = sys.argv[3] if len(sys.argv) > 3 else 'unknown'

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    sys.exit('pyarrow required: pip3 install pyarrow')

TIER = {'uniform': 'null', 'first-slot': 'L-positional', 'l4': 'L4',
        'blind': 'L4-blind', 'model': 'model'}

def game_dirs():
    for d in sorted(GRID.iterdir()):
        if d.is_dir() and (d / 'frozen.json').exists():
            name = d.name
            arm, seed = name.rsplit('-', 1)
            yield arm, int(seed), d, name
    for path, (arm, seed, name) in EXTRA.items():
        yield arm, seed, Path(path), name

decisions_rows, games_rows = [], []
for arm, seed, d, game_name in game_dirs():
    frozen = json.loads((d / 'frozen.json').read_text())
    receipts = {}
    for p in sorted((d / 'phases').glob('[0-9]' * 4 + '.json')):
        phase = json.loads(p.read_text())
        for r in (phase.get('response') or {}).get('receipts', []):
            receipts[(phase['request']['expected_step'], r['actor'])] = r
    accepted = sum(1 for r in receipts.values() if r['accepted'] and not r['skipped'])
    rejected = sum(1 for r in receipts.values() if not r['accepted'] and not r['skipped'])
    skipped = sum(1 for r in receipts.values() if r['skipped'])
    bribe_counts = {}
    engine_cash = {}
    for sp in sorted((d / 'snapshots').glob('[0-9][0-9][0-9][0-9].json')):
        snap = json.loads(sp.read_text())
        engine_cash[snap['step']] = {row['actor']: row['cash']
                                     for row in snap['world']['public_state']}
    for p in sorted((d / 'calls').glob('[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9].json')):
        call = json.loads(p.read_text())
        action = (call.get('result') or {}).get('action') or {}
        if call.get('phase') != 'action' or action.get('action') != 'bribe':
            continue
        receipt = receipts.get((call['step'], call['actor']))
        if not receipt or not receipt['accepted'] or receipt['skipped']:
            continue
        prompt = json.loads(call['messages'][1]['content'])
        offers = [a['params']['to'] for a in prompt['allowed_actions']
                  if a['action'] == 'bribe']
        if action['params']['to'] not in offers:
            continue
        cash = {row[0]: row[1] for row in prompt['selected_opponents']}
        target = action['params']['to']
        decisions_rows.append({
            'game': game_name, 'arm': arm, 'seed': seed,
            'step': call['step'], 'actor': call['actor'],
            'round': prompt.get('round'), 'offers': offers,
            'offer_cash_visible': [cash.get(t) for t in offers],
            'chosen': target, 'amount': action['params']['amount'],
            'offer_cash_engine': [(engine_cash.get(call['step']) or {}).get(t) for t in offers],
            'reward_basis': 'ENGINE_REPLAY',
            'worker_sha256': frozen['config']['worker_sha256'],
            'driver_sha256': frozen['config']['driver_sha256'],
            'experiment_digest': frozen['digest'], 'alashi_commit': ALASHI_COMMIT})
        bribe_counts[target] = bribe_counts.get(target, 0) + 1
    total = sum(bribe_counts.values())
    share = max(bribe_counts.values()) / total if total else 0.0
    hhi = sum((c / total) ** 2 for c in bribe_counts.values()) if total else 0.0
    games_rows.append({
        'game': game_name, 'arm': arm, 'seed': seed,
        'escalation_tier': TIER.get(arm, arm), 'reward_basis': 'ENGINE_REPLAY',
        'accepted_actions': accepted, 'rejected_actions': rejected,
        'skipped_decisions': skipped, 'bribes_accepted': total,
        'distinct_recipients': len(bribe_counts),
        'largest_recipient_share': round(share, 10),
        'recipient_hhi': round(hhi, 10),
        'invariant_flags': {'agg_power': total > 0, 'agg_cooperation': False},
        'worker_sha256': frozen['config']['worker_sha256'],
        'driver_sha256': frozen['config']['driver_sha256'],
        'experiment_digest': frozen['digest'], 'alashi_commit': ALASHI_COMMIT})
    summary_path = d / 'summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        games_rows[-1].update({'status': summary['status'], 'stop_reason': summary.get('reason'),
                               'recorded_calls': summary['calls']})

def write(name, rows):
    table = pa.Table.from_pylist(rows)
    path = OUT / name
    pq.write_table(table, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f'{name}: {len(rows)} rows, sha256 {digest[:16]}')
    return digest

digests = {'decisions': write('decisions.parquet', decisions_rows),
           'games': write('games.parquet', games_rows)}
(OUT / 'checksums.json').write_text(json.dumps({
    'schema_version': 1, 'alashi_commit': ALASHI_COMMIT, 'sha256': digests}, indent=2))
print(f'games: {len(games_rows)}, bribe decisions: {len(decisions_rows)}')
