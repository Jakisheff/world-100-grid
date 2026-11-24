# world-100-grid: bounded-menu agent games with engine-verified outcomes

Self-verifying dataset package (integrity of counts and cross-table
agreement is enforced by verify.py claim I; provenance fields like
worker_sha256/driver_sha256 are carried, not independently recomputed -
attestation of rejected/skipped attempts is planned for the next schema): 50 recorded games of 100 agents in one
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
| model | 3 | meta/llama-3.1-8b-instruct on NVIDIA NIM; three stopped attempts (20261109/13/14, all `provider_failure_threshold`, 0 accepted actions); verify.py claim G checks the first |

## Claims verified by verify.py

The full claim list is the docstring of `verify.py` (claims A-G): the
acceptance-run counts (224 bribes / 70 recipients / share 8/224 / HHI
0.02132494), uniform null quantiles, first-slot ranges, the conditional
permutation breach of every L4 game (p < 0.05 on share and HHI), the
blind arm's dead aiming (midrank percentile 0.40-0.60 against engine
cash), the 20/20 paired percentile effect with mean 0.20-0.28 and the
18/20 negative paired HHI, the model stop, the choice-collusion steganography bound (claim J: engine-midrank inside visible-equivalent offer classes stays at chance; an informed max-engine attack measures 0.806, z=+32), the volume-invariant check (claims H/H2: the unbiased collision estimator sum(ci(ci-1))/(m(m-1)) shows 0/20 inversions on the same pairs, and the acceptance HHI is exactly 1070/224^2 in integer arithmetic). `headline.py` prints the
headline chain from rows alone.

Two numbers cited but external_unverified (ADR-001 D2: not under checksums.json; do not use as evidence without the source journal): run 1 (80.56%) and
run 2 (7.14%) of the recorded BitLLM games,
docs/ops/WORLD_100_BRIBE_FIX_20261109.md in the alashi repository
(commit pin in checksums.json).

## Deployment classes

Model-facing arms record the serving path in `compliance-table.jsonl`
(`serving` field: hosted API, local runtime, or P2P network). Classes are
never merged: a compliance finding for a model behind one serving path is
not evidence for the same weights behind another (`nvidia-nim-bf16` hosted
vs `ollama-q4` local vs BitLLM P2P). Scripted arms (uniform, l4, first-slot,
blind) are engine-driven and carry no model claims at all.

## Transcripts, artifacts and baselines

- `compliance-table.jsonl` records every model-compliance arm verbatim:
  model, serving path, prompt class, verdict, one-line detail.
- `data/model-smoke-prompt.json` holds the exact round-one market prompt
  under which a hosted model produced 100/100 non-callable answers.
- Full per-run records for the model attempts live in the alashi
  repository ops records covered by the commit pin in
  `data/checksums.json`: `docs/ops/world-100-20261109/`,
  `docs/ops/WORLD_100_GRID_20261113.md`,
  `docs/ops/b2-model-behavior-20261114/`.
- Claims policy: a "model failed" statement is reported only against a
  stated baseline. Here the scripted arms (uniform, l4) are the engine
  baselines the model arms are read against; no bare failure claims.

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
