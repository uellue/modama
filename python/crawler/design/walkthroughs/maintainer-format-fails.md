# Walk-through: a maintainer fixes a format that fails on real files

Persona: the maintainer (`../stakeholders.md`): a modama developer, or a coding agent briefed by one, who knows Python and the formats of their field, works in the development VM without access to the real data, and reaches staging through the shared checkout, the drop box `.claude/field-tests/` and a person with a shell there. Situation: the morning review lists failed extractions on real files. Goal: the files read correctly in the search. Done for them: the previously failing examples succeed on staging, a test keeps them working, and anything that belongs upstream is noted.
Confidence: simulated by Claude on 2026-11-15, on paper, from the cases of 2026-11-12 to 14 (the Merlin header's UTF-8 error, AppleDouble files, 96-byte HDF5 headers, the office documents) and tonight's open failures (`run-5/review-2026-11-14.md`: 20 MAT 5 files with a TypeError, UTF-16 `.ini` files, 20 dm3 files with RosettaSciIO's `DMNTagIDError`, 18 PDFs in one backup folder). A measured walk (a fresh agent with only the docs and one seeded case) is planned; the developer-docs hallway test of 2026-11-13 covered part of it (`../hallway/`).
What exists: `modama-chain review` and `browse` (live and stored views, "Save for Claude"), `field-test/failed-headers.sh`, `modama-crawler crawl --path` (one folder), `src/modama_crawler/formats/TEMPLATE.md`, the `format-collection` skill (builder and reviewer briefs), the extractor identity (only changed formats are re-extracted), the staging runbook's "Upgrade", BACKLOG's upstream section.

## Steps

1. **Get the night's failures.** Does: asks the person on the server for `modama-chain review --browse … > review.md` into the drop box; reads it. Seen: on 2026-11-14 the review held every flagged file, grouped by the agent into "test tree", "AppleDouble", and a tail of real formats. Needs to know: per format and error, how many, which are new, one example each. Goes wrong: the grouping by error is manual; a broken format and a broken file look the same; nothing says "new since the last crawl". Would ask: "Which of these are our bugs, and which are just broken files?"

2. **See why one file fails.** Does: opens the example in browse on staging (live view: the extractor from the current checkout, run on the real file), reads the error. Asks for `failed-headers.sh REVIEW.md DATA_ROOT matlab` to see size and first 16 bytes. Needs to know: the reader's version, the full traceback, what the file is (empty, a header only, another format under the same extension). Goes wrong: the stored record holds the error message, not the traceback; on 2026-11-14 the AppleDouble files were found to be another format only from their magic bytes. Would ask: "Is this really a MAT 5 file, and which line of the reader fails?"

3. **Reproduce it in the VM.** Does: needs a file with the same structure. The real file is private data (rules: samples are read as data, never committed; fixtures are public or self-made). Options seen: @weber copies a sample into the drop box and deletes it afterwards (the HDF5 master file, the workspaces); a fixture script run on the server writes a synthetic copy of the structure without the data (`k2is-fixture.sh`, `blo-fixture.sh`); public test files (RosettaSciIO's, LiberTEM's). Goes wrong: each case needs a person on the server; whether a sample may be copied is asked each time; a header-only reproducer may not trigger the bug. Would ask: "May I have this file, or what part of it can I have?"

4. **Fix and test.** Does: writes the failing test from the fixture, fixes the collection (or works around the upstream reader, "get it done somehow and take note", @weber 2026-11-12), runs the collection's tests and the suites, gets a review by another agent. Needs to know: whether to fix here or upstream, and how the record should read (the representation decisions: values as the reader gives them, no editorialising for scientific data; office text may be rendered, decision 369). Goes wrong: the person is asked "should I do A or B?" without examples of what each would look like (@weber's debrief note of 2026-11-15). Would ask: "Is a workaround here acceptable, and what will the record look like?"

5. **Get it onto staging.** Does: merges into `crawler`; the person rebuilds staging (`./upstaging.sh --build`, not during harvest or indexing); the 19:00 crawl re-extracts the files of the changed format (identity), or the whole tree when shared code changed (2026-11-14: identity `0a3e56fe36ad`, every format). Goes wrong: the turn-around is a night; whether the whole tree or one format will be re-extracted is known only from `upstaging.sh`'s last line; a rebuild must wait for a quiet chain. Would ask: "When will I see the result, and does this rebuild re-extract everything?"

6. **See the result before the night.** Does: browse's live view shows the new extraction at once; `crawl --path FOLDER` crawls one folder, and the crawl starts a harvest. Needs to know: whether the record is then in the search too (harvest and indexing of that folder). Asked for on 2026-11-12: re-run extraction, harvest and indexing for one path, for all files of one kind, and for a subtree. Goes wrong: "all files of one kind" has no command; the indexing after a subtree crawl is the normal DAG, with its wait. Would ask: "Can I push just this format through the whole chain now?"

7. **Check after the night.** Does: the next review; compares by hand whether the examples from step 1 now succeed. Goes wrong: no before-and-after per format; a fix that turned failures into wrong values would not show. Would ask: "Did the fix work on all of them, and did it break anything else?"

8. **Report upstream.** Does: notes the reader's bug (RosettaSciIO, LiberTEM, the harvester) in BACKLOG's upstream section, drafts an issue in `.claude/drafts/` for the person to post. Goes wrong: the state of each upstream item (found, patched here, posted, merged, released, our workaround removed) is tracked by hand. Would ask: "Where do I note this so that we drop our workaround once upstream releases the fix?"

## Product hat

The maintainer wants the shortest loop from "this file fails" to "it reads right in the search", and most of the loop exists (review, browse, identity, subtree crawl). What costs time is the person in the middle: every sample, every server command and every decision goes through @weber, and decisions arrive as questions without examples. "Done" for them includes knowing that the fix held on all the files, not just the example.

## Developer hat

- **Grouping by error** needs the error class and the reader's version stored with the failure, not only the message.
- **Samples:** a fixture script per format that copies the structure without the data is safe and reusable; a general one (headers and metadata blocks only, payload zeroed) would need a format-specific notion of "payload" and is not general.
- **"All files of one kind now"** means a crawl that re-extracts one format everywhere without walking unchanged folders; the identity mechanism re-extracts by format already, so the gap is the trigger, not the logic.
- **Before-and-after** needs the previous night's flags, the same history step 5 of the operator's walk needs.
- **Drop box limits:** the person decides what may be copied; an MCP server on staging that enforces read-only access to agreed subtrees (page items 370, 372, 373) would remove the person from steps 2 and 3 for those subtrees.

## Questions for the principal

- (1) Step 1: who triages the review each morning, the operator or a maintainer, and where does a "this is a broken file, not our bug" verdict get recorded so it isn't triaged again?
- (2) Step 3: which subtrees may agents read directly (item 370: the infrastructure project, LiberTEM's test data), and may a sample from elsewhere ever be copied, or only fixture output?
- (3) Step 4: when an upstream reader fails on real files, is a workaround here the default, with the upstream report as a courtesy ("fire and forget"), or do we wait for upstream?
- (4) Step 6: is "push one format through the whole chain now" worth a command, or is a night's turn-around fine after the demo?
- (5) Step 7: should a record whose extraction failed say so in the search ("metadata could not be read"), or only carry the basic file facts?

## Answers from the principal

None yet (questions put on 2026-11-15).

## Gaps

- The review does not group failures by format and error, and has no "new since" (step 1).
- No standard way to get a reproducer from a private file (step 3).
- No command for "all files of one kind, through the whole chain, now" (step 6).
- No before-and-after per format after a fix (step 7).
- Upstream items have no tracked state (step 8).

## Acceptance examples

E6, E7, E8, E9 (in `../examples.md`).

## Questionnaire

Not answered for the maintainer yet: 2.2 (which formats come next, and who asks for them), 2.7 (how many maintainers, and does an agent maintain formats unattended), 2.11 (what an agent may read on staging without a person).
