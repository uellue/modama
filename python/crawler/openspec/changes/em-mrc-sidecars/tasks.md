# Tasks

## 1. The 1:1 question

- [x] 1.1 The stems of EMPIAR-12652's EPU tree, by extension (proposal, "Is there a 1:1 match?"). Verify: the table from `stems.py` over the HTTPS listings.

## 2. Grouping

- [x] 2.1 Fixture `epu_data` (one stem of EMPIAR-12652, five files: the MRC files cut by `cut-header.sh`, the XML whole, the JPEG cut by `cut-sidecars.sh`), with `fixtures.toml` and `LICENSE.fixtures`. Verify: `test_manifest`, `expected/epu_data.json` reviewed.
- [x] 2.2 Tests from the four scenarios of "EPU's sidecars belong to their MRC file", red first. Verify: `pytest src/modama_formats_em/mrc`.
- [x] 2.3 `Mrc.recognize`: the sidecars as members, `d.claimed_elsewhere` for a claimed one; recognition version 2. Verify: the tests green.
- [x] 2.4 README row; `fei1`'s licence line as decided (298). Verify: by eye.

## 3. Checks

- [x] 3.1 em `pytest src` (also `TZ=Europe/Berlin`), common, crawler; `uvx pre-commit run --all-files` after `git add`. Verify: their output in the hand-over.
- [ ] 3.2 Real EPU folders in `modama-chain browse` before and after (the main session; images need the rebuild for `mrcfile`).
