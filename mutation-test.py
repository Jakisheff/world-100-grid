#!/usr/bin/env python3
"""Mutation test for verify.py: controlled corruption of the parquet
rows must turn specific checks red. A check that stays green under a
mutation of the number it certifies is blind, and this script names it.

Usage: python3 mutation-test.py [package-dir]   (default: this repo)
Writes mutation-journal.json next to the package and prints a table.
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import pyarrow.parquet as pq
import pyarrow as pa

PKG = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)
DATA = PKG / 'data'

def load():
    return pq.read_table(DATA / 'decisions.parquet').to_pylist(), pq.read_table(DATA / 'games.parquet').to_pylist()

def save(decisions, games, target, refresh_hashes=False):
    import hashlib
    (target / 'data').mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(decisions), target / 'data/decisions.parquet')
    pq.write_table(pa.Table.from_pylist(games), target / 'data/games.parquet')
    if refresh_hashes:
        checks = json.loads((DATA / 'checksums.json').read_text())
        for split in checks['sha256']:
            checks['sha256'][split] = hashlib.sha256((target / f'data/{split}.parquet').read_bytes()).hexdigest()
        (target / 'data/checksums.json').write_text(json.dumps(checks, indent=2))
    else:
        shutil.copy(DATA / 'checksums.json', target / 'data/checksums.json')

def run_verify(target):
    result = subprocess.run([sys.executable, 'verify.py'],
                            cwd=target, capture_output=True, text=True)
    fails = [line[5:] for line in result.stdout.splitlines() if line.startswith('FAIL ')]
    return result.returncode, fails

MUTATIONS = {}

def mutation(name):
    def register(fn): MUTATIONS[name] = fn
    return register

@mutation('M1 swap one chosen target in the acceptance game')
def _(decisions, games):
    for row in decisions:
        if row['game'] == 'l4-20261109-original' and len(row['offers']) > 1:
            row['chosen'] = next(o for o in row['offers'] if o != row['chosen'])
            return 'one bribe decision retargeted'

@mutation('M2 inflate acceptance share in games.parquet')
def _(decisions, games):
    for g in games:
        if g['game'] == 'l4-20261109-original':
            g['largest_recipient_share'] = 0.05
            return 'games row share 0.0357 -> 0.05'

@mutation('M3 scale engine cash in one uniform game')
def _(decisions, games):
    for row in decisions:
        if row['game'] == 'uniform-20261105':
            row['offer_cash_engine'] = [c * 3 + 7 if c is not None else c for c in row['offer_cash_engine']]
    return 'uniform-20261105 engine cash transformed'

@mutation('M4 drop one offer from L4 decisions')
def _(decisions, games):
    for row in decisions:
        if row['game'] == 'l4-20261113' and len(row['offers']) > 1:
            keep = row['offers'][1:]
            if row['chosen'] in keep:
                row['offers'] = keep
                row['offer_cash_engine'] = row['offer_cash_engine'][1:]
                row['offer_cash_visible'] = row['offer_cash_visible'][1:]
                return 'offers shrunk by one in l4-20261113'
    return 'no row mutated (unexpected)'

@mutation('M5 corrupt visible cash everywhere (unused field)')
def _(decisions, games):
    for row in decisions:
        row['offer_cash_visible'] = [42] * len(row['offers'])
    return 'offer_cash_visible set to constant 42'

@mutation('M6 flip accepted_actions of a uniform game')
def _(decisions, games):
    for g in games:
        if g['game'] == 'uniform-20261102':
            g['accepted_actions'] = 999
            return 'uniform-20261102 accepted_actions -> 999'

@mutation('M7 small drift inside tolerance bands (null quantiles)')
def _(decisions, games):
    for g in games:
        if g['arm'] == 'uniform':
            g['largest_recipient_share'] = min(g['largest_recipient_share'] + 0.008, 0.99)
            g['recipient_hhi'] = min(g['recipient_hhi'] + 0.004, 0.99)
    return 'uniform shares +0.008 / HHI +0.004'

@mutation('M8 renumber distinct_recipients in games only')
def _(decisions, games):
    for g in games:
        if g['game'] == 'first-slot-20261113':
            g['distinct_recipients'] = 55
            return 'first-slot-20261113 recipients -> 55'

@mutation('M3b permute engine cash inside offer sets')
def _(decisions, games):
    for row in decisions:
        if row['game'] == 'uniform-20261105' and len(row['offer_cash_engine']) > 1:
            row['offer_cash_engine'] = list(reversed(row['offer_cash_engine']))
    return 'uniform-20261105 engine cash reversed within offers'

@mutation('M9 regenerate checksums after tampering')
def _(decisions, games):
    for g in games:
        if g['game'] == 'l4-20261114':
            g['largest_recipient_share'] = 0.9
    globals()['REFRESH_HASHES'] = True
    return 'l4-20261114 share -> 0.9 with checksums.json regenerated (logic layer must catch)'

journal = []
with tempfile.TemporaryDirectory() as tmp:
    for name, corrupt in MUTATIONS.items():
        decisions, games = load()
        target = Path(tmp) / name.split()[0]
        detail = corrupt(decisions, games)
        save(decisions, games, target, refresh_hashes=globals().get('REFRESH_HASHES', False))
        globals()['REFRESH_HASHES'] = False
        shutil.copy(PKG / 'verify.py', target / 'verify.py')
        code, fails = run_verify(target)
        journal.append({'mutation': name, 'detail': detail,
                        'verify_exit': code, 'failed_checks': fails})

out = PKG / 'mutation-journal.json'
out.write_text(json.dumps(journal, indent=2) + '\n')
for entry in journal:
    verdict = 'CAUGHT' if entry['verify_exit'] != 0 else 'BLIND'
    print(f"{verdict:6} {entry['mutation']}")
    for fail in entry['failed_checks']:
        print(f"        - {fail[:100]}")
sys.exit(0)
