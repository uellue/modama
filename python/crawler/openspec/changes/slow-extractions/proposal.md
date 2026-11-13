# Proposal

## Why

An extraction over the time limit (60 s) is stopped, recorded as failed and tried again; every extraction's time is stored (`extract_seconds`), and the crawl's line sums the time per format. A successful extraction that is slow, but under the limit, is flagged nowhere: nobody sees which files cost a night's crawl its time until they fail. @weber (2026-11-13, item 352, "go with your leans") approved flagging them and naming the slowest of a crawl.

## What Changes

- **A slow extraction is flagged for review**: a successful extraction over 10 s (`extraction.SLOW`) leaves its dataset with the warning `<format> extraction took <seconds> s; slow extraction`, stored with the dataset. `slow extraction` (`extraction.SLOW_EXTRACTION`) is a fixed marker like `two formats want it` (decision 344) and `not inspected` (340), and `modama-chain review` lists it as a kind of its own (change `chain-browse`). The warning follows the stored extraction: a reused extraction keeps it, one run again is flagged by its own time. A failed extraction is warned as failed only.
- **A success is timed in its worker**, from the extractor's call: starting a worker process and the imports of unpickling its task do not count, so a worker's first task gets no warning for them (review S3). A failure keeps the time the pool measured from the task's start, as the time limit does. This is also the time stored (`extract_seconds`) and summed per format.
- **The crawl names its 10 slowest extractions** (`extraction.SLOWEST`), those it ran, as path, format and seconds, slowest first, a failure marked `(failed)` (review S1): one line of the report after its first, `slowest extractions: /a/x.emd em/emd 60.0 s (failed), /a/b.dm4 em/dm4 23.4 s, …`. Like pytest's `--durations`, it is printed, not stored; the slow files stay listed for review by their warnings.

Behaviour towards the user: the crawl's log has one more report line and a warning per slow extraction, counted in the run's warnings; `modama-chain review` one more kind; the times stored and summed per format leave out the worker's start. What a harvester or a searcher sees does not change: the warnings are not part of the records.

Out of scope: the slowest extractions in the run, on the line of `runs` or in `modama-chain status` (built first with a migration, dropped by main on the review as not needed: @weber may reverse it, decision log); a threshold per format or set by configuration; the slowest spot-check extractions (the spot check's time is not counted in the time per format either); imports an extractor makes on its first call (RosettaSciIO's DM reader, under 1 s here) still count.

Serves: @weber's request 352; R12 ("The crawl reports the slowest handlers, like pytest's `--durations`", here for the extractors); R23 (a failing or slow extractor does not stop the crawl), and the review of flagged files (D17 of `chain-browse`).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `extraction`: a slow extraction is flagged; the crawl reports its slowest extractions.
- `chain-browse` (pending change): one more kind in `modama-chain review`, edited in that change's spec.

## Impact

`src/modama_crawler/extraction.py` (constants, `_timed`, `Report.slowest`, the warning); `python/search-chain/src/modama_chain/review.py` (`MARKERS`). README, "What to look out for" and the crawl's report; the decision log. No schema change, no new dependency.
