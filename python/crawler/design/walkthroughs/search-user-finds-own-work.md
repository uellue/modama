# Walk-through: a search user looks for their own recent work

Persona: the search user (`../stakeholders.md`): a scientist or research data manager at ER-C who looks for files in the institute's storage through the search's AI mode; knows their data and its jargon, not how the index is built. Situation: preparing a talk, they want their latest slides on a topic, then ask about something they can't find. Goal: open the right file within a minute and trust that nothing newer was missed. Done for them: the file is open, or they know why it isn't there.
Confidence: simulated by Claude on 2026-11-15, on paper, from @weber's queries on staging: "Find Merlin acquisitions" (2026-11-11), the AI mode conversation exported on 2026-11-14 ("the latest presentation of [a person] on RDM challenges", then "There should also be pptx datasets?"; part of the real preparation of the demo's slides), and a probe about a person who is not in the data. The stored queries (OpenSearch `top_queries-*`, all @weber's, permission given on 2026-11-15) are still to be read; real users have not been asked (`../stakeholders.md`, how to make it real).
What exists: the search's web page (AI mode without login, through a forwarded port on staging), its answers with "Datasets cited in this answer" and links into the management interface's browser, the records as the crawler publishes them (since 2026-11-14 with the text of `.docx`/`.pptx` files).

## Steps

1. **Open the search.** Does: opens the page; on staging through `ssh -L 13000:…`, in production at an institute URL. Goes wrong: on staging only as `localhost` (other host names send usage statistics, README "Open"). Would ask: "Is this the institute's search or some EU portal?" (the page is branded EOSC Data Commons).

2. **Ask for their latest presentation.** Does: types the question with their name and topic. Seen on 2026-11-14: the first answer said it searches "scientific datasets and research tools only" and can't find talks by a presenter, then offered a Word document and a video from the right folder; only after "There should also be pptx datasets?" did it list five decks, newest first, with the caveat that the records had "slide count, size and issue date, but not slide titles". Goes wrong: the assistant's instructions describe a public data portal, not an institute's file store, so it argues the question is out of scope; the decks' text was missing then (now in, from the 2026-11-14 crawl); the name was searched as a topic, not as the creator (page item 367 b). Would ask: "Why does it say it can't find presentations, and then finds five?"

3. **Open the cited file.** Does: clicks a link in the answer or in the cited list. Seen: links into the management interface's browser; two of five in the cited list were cut (one without `https://`, one with `fz-juelich.ddhoc`), and the export showed mojibake for dashes and umlauts (item 367 c, d; not yet located). Needs: the browser's login. Would ask: "Why does this link go nowhere?"

4. **Ask about the search itself.** Does: "Why don't I find my file from this morning?", "Where are my `._` files?", "How up to date is this?". Today: the assistant knows nothing about the index (which formats, which exclusions, the freshness time T); R46 asks for it. Would ask: "Is my file missing, or not indexed yet, or excluded?"

5. **Tell someone the answer was wrong.** Does: nothing possible; the page has no feedback. @weber asked for "a feature that allows quick feedback and retry to search chats" (2026-11-14, item 385) and for collecting such samples "easily, with user feedback and their permission" (2026-11-15). Would ask: "Who do I tell, and will it get better?"

6. **Check that it doesn't make things up.** Does: asks about a person who is not in the data. Expected: "nothing found", not an invented biography. Not yet observed in a saved answer. Would ask: "Can I quote this answer?"

## Product hat

What they want is their own files, found by the words they'd use (their name, the project, the instrument), opened in one click, and an honest "not there, because …". The demo's queries show the core works ("This will go to town once we have all the metadata in", @weber, 2026-11-12). They would complain about: being told their question is out of scope; links that go nowhere; no way to report a wrong answer; not knowing how fresh it is. "Done" includes trust: knowing what the search can't see.

## Developer hat

- **The assistant's instructions and model are upstream's**, written for a public catalogue; tailoring them per deployment (@weber, 2026-11-14: "we'll probably have to tailor these parts of the warehouse for modama, or even per modama deployment") is a fork point with upstream.
- **Meta-questions (R46)** need the facts about the index (formats, exclusions, T, counts) available to the assistant, as a tool or as context; the facts exist in the crawler and the status tool.
- **Who sees what:** the crawler reads with one account (@weber's on staging) and every visitor sees every record, owners' names included; per-user access comes later (`../requirements.md`). In production this decides what may be indexed at all.
- **Feedback with permission** stores questions and answers, which are personal data: retention, who may read them, and consent are open (2.9).
- **Links:** whether the cut links come from the model, the export or the page is unknown (item 367); a test with a saved answer would tell.

## Questions for the principal

- (1) Step 2: should the assistant's instructions say what this search is (the institute's file store: datasets, documents, presentations, code) per deployment, as our patch, and offer it upstream?
- (2) Step 4, R46: which facts about the search should the assistant know: formats read, exclusions, T, counts, what "dataset" means here?
- (3) Step 5: where is feedback kept, who reads it, for how long, and what does the user agree to (one checkbox, per answer)?
- (4) Who may see which records in production before per-user access exists: everything the crawl account can read, or only agreed areas?
- (5) Step 1: should the page say it is the institute's search (branding), and is that ours or upstream's?

## Answers from the principal

None yet (questions put on 2026-11-15).

## Gaps

- The assistant's instructions do not describe an institute file store (step 2).
- No facts about the index for meta-questions (step 4, R46).
- No feedback, retry or sample collection in the page (step 5, item 385).
- Cut links in the cited list, cause unknown (step 3, item 367).

## Acceptance examples

E10, E11, E12, E13 (in `../examples.md`).

## Questionnaire

Not answered for the search user yet: 1.4 (how many users, how often), 2.5 (what happens when an answer is wrong and nobody notices), 2.9 (personal data in queries, feedback and owners' names), 2.6 (how long a user waits for an answer: 2026-11-14's took several tool calls).
