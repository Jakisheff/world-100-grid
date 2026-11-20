# Getting started

Three ways in, ordered by cost. Nothing here needs a GPU, an API key, or the
Solana chain.

## 1. Verify every claim (about a minute)

```sh
git clone https://github.com/Jakisheff/world-100-grid && cd world-100-grid
pip install pyarrow
python verify.py      # recomputes all 24 claims from data/; exit 0 = reproduced
python headline.py    # prints the headline chain from the published rows
```

`verify.py` is the acceptance test for this package: it fails loudly on any
mismatch between the README claims and the published parquet rows.

## 2. Test your own model (one command)

`data/model-smoke-prompt.json` holds the exact round-one market prompt where
two of four tested families failed 0/100 (the legal menu contains only
`pass`). Point the harness at any OpenAI-compatible endpoint:

```sh
node model-smoke.mjs http://127.0.0.1:11434/v1/chat/completions qwen3:8b
```

It prints a binary verdict (PASS = exact menu object, FAIL = raw answer).
Append the verdict JSON to `compliance-table.jsonl` and open a PR — that is
how n grows beyond the author's hardware.

## 3. Run a complete world yourself (about three minutes)

The engine lives in the [alashi repository](https://github.com/Jakisheff/alashi).
The uniform-legal null arm plays a full game deterministically, no keys:

```sh
git clone https://github.com/Jakisheff/alashi && cd alashi
cargo build --manifest-path arena/Cargo.toml --locked --bin world_worker
node tools/agent-bootstrap/world-demo.mjs \
  --worker "$PWD/arena/target/debug/world_worker" --dir "$(mktemp -d)/world"
```

Seed 20261121, three independent runs give a bit-identical `state_hash`
(`5867c34c…`): 147 calls, 147 accepted, 0 rejected, winner `agent-006`,
payout 76,000,000, rake 4,000,000. The run directory keeps the frozen
config, every decision, and the engine replay receipt.

## Where to read next

- Dataset card (splits, arms, provenance): `DATACARD.md`
- Preprint behind the three anomalies: DOI 10.5281/zenodo.24225748
- Proposal thread for the kaggle-environments integration:
  Kaggle/kaggle-environments issue #1451
