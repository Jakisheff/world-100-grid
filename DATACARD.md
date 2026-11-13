# world-100-grid: bounded-menu agent games with engine-verified outcomes

Self-verifying dataset package: 50 recorded games of 100 agents in one
shared ALASHI political-economy game (canonical Rust rules, six rounds),
plus a stopped model-compliance attempt. Every claimed number in the
run records is recomputed from the published rows by `verify.py`; a
green run of `verify.py` is the acceptance test for this package.

## Splits

- `data/decisions.parquet` — 7,410 rows, one per accepted bribe decision:
  `game, arm, seed, step, actor, round, offers[], offer_cash_visible[],
  offer_cash_engine[], chosen, amount, reward_basis, worker_sha256,
  driver_sha256, experiment_digest, alashi_commit`.
- `data/games.parquet` — 50 rows, one per game: accepted/rejected/skipped
  counts, bribe concentration (`largest_recipient_share`, `recipient_hhi`),
  `escalation_tier`, `status/stop_reason`, provenance digests.
- `data/checksums.json` — schema_version, alashi commit pin, split SHA256.

## Arms

| arm | games | what it is |
|---|---:|---|
| uniform | 20 | engine null: uniformly random legal action per decision |
| l4 | 20 + 1 | legal-only attacker, bribe the richest visible legal target (l4-20261109-original is the acceptance run of the first L4 record) |
| first-slot | 3 | positional control: always the first offered peer |
| blind | 3 | l4 under a driver whose prompts hide opponent cash |
| model | 1 | meta/llama-3.1-8b-instruct on NVIDIA NIM; stopped at the preregistered failure threshold, 0 accepted actions |

## Claims verified by verify.py

The full claim list is the docstring of `verify.py` (claims A-G): the
acceptance-run counts (224 bribes / 70 recipients / share 8/224 / HHI
0.02132494), uniform null quantiles, first-slot ranges, the conditional
permutation breach of every L4 game (p < 0.05 on share and HHI), the
blind arm's dead aiming (midrank percentile 0.40-0.60 against engine
cash), the 20/20 paired percentile effect with mean 0.20-0.28 and the
18/20 negative paired HHI, and the model stop. `headline.py` prints the
headline chain from rows alone.

Two numbers cited but external to this package: run 1 (80.56%) and
run 2 (7.14%) of the recorded BitLLM games,
docs/ops/WORLD_100_BRIBE_FIX_20261109.md in the alashi repository
(commit pin in checksums.json).

## Provenance and integrity

Every row carries the frozen experiment digest and the SHA-256 of the
Rust worker and Node driver that produced it; `reward_basis` is
ENGINE_REPLAY for all game rows (outcomes verified by exact replay
against the same worker binary during the runs). Schema version 1.
License: MIT. Source games were produced on 13-14 November 2026; the
rerun l4-20261109 carries three explicit skipped decisions caused by
provider timeouts during a host sleep, recorded by the driver and
visible in its games row.

## Reproduce

    pip install pyarrow
    python verify.py     # recomputes every claim from data/; exit 0 = reproduced
    python headline.py   # the headline question answered from rows alone
