# Acceptance examples

Concrete situations and the outcome people can observe, collected from walk-throughs (`walkthroughs/`) and hallway tests. Each has an ID, a priority (must, should, could; the walk-through's proposal until the principal confirms) and its source. Specs and tests cite the ID. Started 2026-11-15; earlier walk-throughs keep their examples inline.

## Operator

- **E1** (should; `walkthroughs/operator-morning-after.md`, step 1): when an operator logs in to the server and wants the night's status, then one documented command run from any folder prints it, without defining a shell function first.
- **E2** (must; step 2): when the night's crawl, harvest and indexing all succeeded but an earlier night's indexing failed or a re-index ran by hand, then the status says the search is fresh as of the last complete chain and names the earlier gap, instead of `unknown`.
- **E3** (should; step 3): when the night's failed extractions or dataset count differ from the night before by more than an agreed margin, then the status shows both numbers next to each other and marks the change.
- **E4** (must; step 4): when the search index holds records the crawler no longer publishes (on 2026-11-15: 1,452,360 against 1,313,385), then the status shows the count per stage and the difference, and points to the command that removes them.
- **E5** (should; steps 7 and 8): when indexing failed during the night, then the status says which run failed and the one command that re-runs it, and that command refuses while a crawl, harvest or indexing is running.

## Maintainer

- **E6** (must; `walkthroughs/maintainer-format-fails.md`, step 1): when the night's crawl failed to extract files of one format, then the review groups them by format and error with a count and one browse link per example, and says which failures are new since the last crawl.
- **E7** (should; step 3): when a maintainer needs a failing file to reproduce the error but may not copy it into the repository, then a documented command writes what the fix needs (size, first bytes, the error, the reader's version) to the drop box, without the file's content beyond its header.
- **E8** (must; step 5): when a fix for a format is merged and staging is rebuilt, then the next crawl re-extracts exactly the files of that format (extractor identity), and the review afterwards shows whether each previously failing example now succeeds.
- **E9** (should; step 6): when a maintainer wants to see the fixed record in the search before the night, then one command crawls, harvests and indexes a single path, and browse shows the record as the search does.

## Search user

- **E10** (must; `walkthroughs/search-user-finds-own-work.md`, step 2): when a user asks AI mode for their own recent presentation by person and topic, then the answer lists their decks newest first with the browse link, and says what it could and could not see in them (titles, text).
- **E11** (must; step 4, R46): when a user asks why a file of theirs is not found and the file is of a type the deployment excludes (for example an AppleDouble `._*` file), then the answer says that such files are not in the index, and why.
- **E12** (should; step 4): when a user asks how fresh the search is, then the answer gives the freshness time T in their local time.
- **E13** (should; step 5): when a user finds an answer wrong or incomplete, then they can say so in the page with one click and an optional comment, and agree that the question, the answer and their comment are kept for the maintainers.
