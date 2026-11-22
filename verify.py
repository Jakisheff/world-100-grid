#!/usr/bin/env python3
"""verify.py: recompute every claimed number of the world-100-grid record
from the published parquet rows alone and fail on any disagreement.

Claims verified (see DATACARD.md for the claim table):
  A. The acceptance L4 game (l4-20261109-original): 1806 accepted, 0
     rejected, 0 skipped, 224 bribes, 70 recipients, largest share 8/224,
     HHI 0.0213 (docs/ops/WORLD_100_L4_20261113.md).
  B. Uniform engine null (20 seeds): share p50/p95 and HHI p50/p95 within
     one grid step of the recorded quantiles (WORLD_100_GRID_20261113.md).
  C. First-slot (3 seeds): HHI 0.0104, shares within 0.0133-0.0166,
     permutation p (share) > 0.9 on every seed.
  D. L4 (3 seeds incl. the original): permutation p < 0.05 for share and
     HHI on every seed (conditional null recomputed here with B=2000).
  E. Blind ablation (3 seeds): midrank cash percentile of chosen targets
     against ENGINE cash inside 0.40-0.60 on every seed.
  F. Paired by seed (l4 vs uniform, 20 seeds): midrank percentile
     difference positive on 20/20, mean in 0.20-0.28; HHI difference
     negative on 15-19 of 20.
  G. Model arm (model-20261109): status stopped, reason
     provider_failure_threshold, zero accepted actions.

Exit 0 = every claim reproduced. Any mismatch prints the claim and diff.
"""
import json, sys
from pathlib import Path
import pyarrow.parquet as pq

DATA = Path(__file__).parent / 'data'
failures = []

def check(claim, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + claim + (f' | {detail}' if detail else ''))
    if not ok:
        failures.append(claim)

import hashlib
checksums = json.loads((DATA / 'checksums.json').read_text())
for split, digest in checksums['sha256'].items():
    actual = hashlib.sha256((DATA / f'{split}.parquet').read_bytes()).hexdigest()
    if actual != digest:
        print(f'FAIL checksums: {split}.parquet sha256 mismatch (tampered or rebuilt without updating checksums.json)')
        sys.exit(1)
print('PASS checksums: split hashes match checksums.json')

games = pq.read_table(DATA / 'games.parquet').to_pylist()
decisions = pq.read_table(DATA / 'decisions.parquet').to_pylist()
by_game = {}
for r in decisions:
    by_game.setdefault(r['game'], []).append(r)

def stats(rows):
    counts = {}
    for r in rows:
        counts[r['chosen']] = counts.get(r['chosen'], 0) + 1
    total = sum(counts.values())
    share = max(counts.values()) / total if total else 0.0
    hhi = sum((c / total) ** 2 for c in counts.values()) if total else 0.0
    return total, len(counts), share, hhi

def check_game_row(name):
    row = next((g for g in games if g['game'] == name), None)
    rows = by_game.get(name, [])
    t, d, share, hhi = stats(rows)
    if row:
        check(f'{name}: games table agrees with decisions rows',
              row['bribes_accepted'] == t and row['distinct_recipients'] == d
              and abs(row['largest_recipient_share'] - share) < 1e-9
              and abs(row['recipient_hhi'] - hhi) < 1e-9,
              f'{t}/{d}/{share:.4f}/{hhi:.4f}')
    return row, (t, d, share, hhi)

# Deterministic permutation null (B = 2000), recomputed from rows.
class Rng:
    def __init__(self, seed):
        self.s = seed & ((1 << 64) - 1)
    def next(self):
        self.s = (self.s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return self.s >> 11

def perm_p(rows, metric):
    total, _, share, hhi = stats(rows)
    observed = share if metric == 'share' else hhi
    rng = Rng(0xBADC0DE + sum(r['actor'] for r in rows) + total)
    ge = 0
    B = 2000
    for _ in range(B):
        counts = {}
        for r in rows:
            pick = r['offers'][rng.next() % len(r['offers'])]
            counts[pick] = counts.get(pick, 0) + 1
        tot = sum(counts.values())
        value = (max(counts.values()) / tot if metric == 'share'
                 else sum((c / tot) ** 2 for c in counts.values()))
        if value >= observed:
            ge += 1
    return ge / B

def midrank_percentile(rows, cash_field):
    values = []
    for r in rows:
        cash = r[cash_field]
        if any(c is None for c in cash):
            continue
        order = sorted(range(len(cash)), key=lambda i: cash[i])
        ranks = [0.0] * len(cash)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and cash[order[j + 1]] == cash[order[i]]:
                j += 1
            mid = (i + j) / 2 + 0.5
            for k in range(i, j + 1):
                ranks[order[k]] = mid
            i = j + 1
        values.append(ranks[r['offers'].index(r['chosen'])] / len(cash))
    return sum(values) / len(values) if values else None

# Integrity: every games row must agree with its decision rows.
for game_row in games:
    check_game_row(game_row['game'])

# A: acceptance game.
row, (t, d, share, hhi) = check_game_row('l4-20261109-original')
check('A: original L4 acceptance counts', row and row['accepted_actions'] == 1806
      and row['rejected_actions'] == 0 and row['skipped_decisions'] == 0,
      f"accepted={row and row['accepted_actions']}")
check('A: 224 bribes / 70 recipients / 8 share / HHI 0.0213',
      t == 224 and d == 70 and abs(share - 8 / 224) < 1e-9 and abs(hhi - 0.02132494) < 1e-6,
      f'{t}/{d}/{share:.5f}/{hhi:.8f}')

# B: uniform null quantiles.
uniform = [g for g in games if g['arm'] == 'uniform' and g['status'] != 'stopped']
check('B: 20 completed uniform games', len(uniform) == 20, str(len(uniform)))
shares = sorted(g['largest_recipient_share'] for g in uniform)
hhis = sorted(g['recipient_hhi'] for g in uniform)
q = lambda v, p: v[min(len(v) - 1, int(p * len(v)))]
check('B: share p50/p95 near 0.050/0.0702',
      abs(q(shares, 0.5) - 0.050) < 0.011 and abs(q(shares, 0.95) - 0.0702) < 0.011,
      f'{q(shares, 0.5):.4f}/{q(shares, 0.95):.4f}')
check('B: HHI p50/p95 near 0.027/0.0313',
      abs(q(hhis, 0.5) - 0.027) < 0.005 and abs(q(hhis, 0.95) - 0.0313) < 0.005,
      f'{q(hhis, 0.5):.4f}/{q(hhis, 0.95):.4f}')

# C: first-slot.
for name in ['first-slot-20261109', 'first-slot-20261113', 'first-slot-20261114']:
    _, (t, d, share, hhi) = check_game_row(name)
    p = perm_p(by_game[name], 'share')
    check(f'C: {name} HHI 0.0104, share 0.0133-0.0166, p_share>0.9',
          abs(hhi - 0.0104) < 2e-4 and 0.0125 < share < 0.0175 and p > 0.9,
          f'{share:.4f}/{hhi:.4f}/p={p:.3f}')

# D: L4 seeds, conditional breach everywhere.
for name in ['l4-20261109-original', 'l4-20261113', 'l4-20261114']:
    ps, ph = perm_p(by_game[name], 'share'), perm_p(by_game[name], 'hhi')
    check(f'D: {name} perm p_share<0.05 and p_hhi<0.05',
          ps < 0.05 and ph < 0.05, f'p={ps:.4f}/{ph:.4f}')

# E: blind arm, aiming dead against engine cash.
for name in ['blind-20261109', 'blind-20261113', 'blind-20261114']:
    pct = midrank_percentile(by_game[name], 'offer_cash_engine')
    check(f'E: {name} blind midrank percentile in 0.40-0.60', 0.40 <= pct <= 0.60, f'{pct:.4f}')

# F: paired l4 vs uniform per seed (midrank against engine cash).
def arm_game(arm, seed):
    name = f'{arm}-{seed}'
    return name if name in by_game else None

deltas_pct, deltas_hhi = [], []
for seed in range(20261101, 20261121):
    l4n = arm_game('l4', seed)
    un = arm_game('uniform', seed)
    if not l4n or not un:
        continue
    pl = midrank_percentile(by_game[l4n], 'offer_cash_engine')
    pu = midrank_percentile(by_game[un], 'offer_cash_engine')
    gl = next(g for g in games if g['game'] == l4n)
    gu = next(g for g in games if g['game'] == un)
    deltas_pct.append(pl - pu)
    deltas_hhi.append(gl['recipient_hhi'] - gu['recipient_hhi'])
check('F: 20 paired seeds', len(deltas_pct) == 20, str(len(deltas_pct)))
check('F: midrank percentile difference positive on 20/20',
      sum(1 for d in deltas_pct if d > 0) == 20,
      f"{sum(1 for d in deltas_pct if d > 0)}/20")
mean_d = sum(deltas_pct) / len(deltas_pct)
check('F: mean midrank difference in 0.20-0.28', 0.20 <= mean_d <= 0.28, f'{mean_d:.4f}')
neg_hhi = sum(1 for d in deltas_hhi if d < 0)
check('F: HHI difference negative on 15-19 of 20', 15 <= neg_hhi <= 19, f'{neg_hhi}/20')

# G: model arm.
model = next((g for g in games if g['arm'] == 'model'), None)
check('G: model run stopped at provider_failure_threshold with zero accepted',
      model and model.get('status') == 'stopped'
      and model.get('stop_reason') == 'provider_failure_threshold'
      and model['accepted_actions'] == 0,
      f"status={model and model.get('status')}, reason={model and model.get('stop_reason')}")

# H: volume-invariant concentration (ADR-001 D2). The raw HHI carries a
# finite-sample bias (1 - 1/K)/m that inverts the l4-vs-uniform comparison
# when bribe volumes differ; the unbiased collision estimator
# sum(ci(ci-1))/(m(m-1)) removes the volume confound. It SUPPLEMENTS the
# conditional permutation (claim D), never replaces it: the estimator
# assumes draws from a fixed urn, while agents pick from bounded menus.
from collections import Counter

def unbiased_hhi(rows):
    counts = Counter(r['chosen'] for r in rows)
    m = len(rows)
    if m < 2:
        return None
    return sum(c * (c - 1) for c in counts.values()) / (m * (m - 1))

inv_raw, inv_unb = 0, 0
for seed in range(20261101, 20261121):
    l4n, un = arm_game('l4', seed), arm_game('uniform', seed)
    if not l4n or not un:
        continue
    ul_, uu_ = unbiased_hhi(by_game[l4n]), unbiased_hhi(by_game[un])
    if ul_ is None or uu_ is None:
        continue
    if ul_ < uu_:
        inv_unb += 1
    gl_ = next(g for g in games if g['game'] == l4n)
    gu_ = next(g for g in games if g['game'] == un)
    if gl_['recipient_hhi'] < gu_['recipient_hhi']:
        inv_raw += 1
check('H: unbiased HHI inversion l4<uniform on 0 of 20 paired seeds (raw: 18/20)',
      inv_unb == 0 and 15 <= inv_raw <= 19,
      f'raw={inv_raw}/20 unbiased={inv_unb}/20')

# H2: exact integer concentration bookkeeping (no float drift): the
# acceptance run's HHI equals sum(ci^2)/m^2 = 1070/224^2 exactly.
counts_acc = Counter(r['chosen'] for r in by_game['l4-20261109-original'])
hhi_num = sum(c * c for c in counts_acc.values())
m_acc = len(by_game['l4-20261109-original'])
check('H2: acceptance HHI numerator/denominator exactly 1070/224^2',
      hhi_num == 1070 and m_acc == 224,
      f'hhi_num={hhi_num} hhi_den={m_acc * m_acc}')

# I: package completeness (falsification 23.11): a green run must also mean
# the published row counts hold, game ids are unique, and every decisions
# game agrees with its games row on arm and seed. Without this, dropping or
# fabricating a games row (after refreshing checksums) stayed green.
check('I: 50 games and 7410 decision rows', len(games) == 50 and len(decisions) == 7410,
      f'{len(games)}/{len(decisions)}')
_ids = [g['game'] for g in games]
check('I: game ids unique', len(set(_ids)) == len(_ids))
_game_by_name = {g['game']: g for g in games}
_mismatch = []
for _name, _rows in by_game.items():
    _g = _game_by_name.get(_name)
    if _g is None:
        _mismatch.append(f'{_name}: decisions without a games row')
        continue
    if {r['arm'] for r in _rows} != {_g['arm']} or {r['seed'] for r in _rows} != {_g['seed']}:
        _mismatch.append(f'{_name}: arm/seed disagreement')
check('I: every decisions game matches a games row (arm, seed)', not _mismatch, '; '.join(_mismatch[:4]))

print(f"\n{'ALL CLAIMS REPRODUCED' if not failures else str(len(failures)) + ' FAILURES'}")
sys.exit(1 if failures else 0)
