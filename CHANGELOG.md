# Changelog

world-100-grid package history. Data files (`data/*.parquet`,
`data/checksums.json`) are immutable once published; entries below record
package-level changes only. Format added 2026-11-24 as part of the
trust-format import (see DATACARD "Deployment classes" and "Transcripts,
artifacts and baselines").

- 2026-11-24 — docs: deployment-class section, transcripts/artifacts
  pointers, baselines claims policy, this changelog. Data unchanged.
  (Untracked `zk_proof_package.json` predates this entry and is not part
  of this change.)
- 2026-11-24 — zk: unified proof package, third party verifies without
  loading data (0229651).
- 2026-11-23 — verify: claim J choice-collusion steganography bound
  (6ec2576).
- 2026-11-23 — verify: completeness claim I; DATACARD honesty frame for
  provenance (88b4e75).
- 2026-11-23 — verify: volume-invariant HHI claims H/H2; model arm
  recorded as 3 stopped runs; BitLLM numbers marked external_unverified
  (2d83263).
- 2026-11-21 — getting-started guide: three entry paths, honest timing,
  fresh-clone reproduction result (af81db1, 3e8f569).
- 2026-11-14 — compliance table: clean eight-row record, four families
  x two prompts (9d53111); model compliance smoke with the recorded
  failing prompt (f97b885).
- 2026-11-14 — verify: hash the splits, cross-check every games row,
  mutation journal (20cc452).
- 2026-11-14 — world-100-grid v1: 50 engine-replayed agent games,
  self-verifying (55be71d).
