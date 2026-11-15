# Walk-through: a search user looks for their own recent work

Persona: the search user (`../stakeholders.md`): a scientist or research data manager at ER-C who looks for files in the institute's storage through the search's AI mode; knows their data and its jargon, not how the index is built. Situation: preparing a talk, they want their latest slides on a topic, then ask about something they can't find. Goal: open the right file within a minute and trust that nothing newer was missed. Done for them: the file is open, or they know why it isn't there.
Confidence: simulated by Claude on 2026-11-15, on paper, from @weber's queries on staging: "Find Merlin acquisitions" (2026-11-11), the AI mode conversation exported on 2026-11-14 ("the latest presentation of [a person] on RDM challenges", then "There should also be pptx datasets?"; part of the real preparation of the demo's slides), and a probe about a person who is not in the data; and the search API's log of the assistant's search calls on staging (37 calls, 2026-11-12 to 14, all @weber's questions, read with permission on 2026-11-15; summarised below without colleagues' names). Real users have not been asked (`../stakeholders.md`, how to make it real).

## Questions seen in the search API's log

Eleven conversations, as the model restated each question (`user_question`), with the number of searches it ran:

| When (UTC) | Question (names replaced) | Searches | What it shows |
|---|---|---|---|
| 11-12 14:01 | Find DM4 files by [a colleague] | 4 | the name goes into `creator_name`; one call used a different surname than asked |
| 11-14 05:10 | find dm4 please | 3 | after two searches it looked for "DM4 emtansine antibody-drug conjugate" and "DM4 dosimetry": the assistant treats DM4 as ambiguous across all sciences |
| 11-14 05:56 | Latest presentation of [@weber] on RDM challenges, then "Are there pptx …?" | 4 | step 2 below |
| 11-14 08:55 | [@weber]'s latest pptx datasets on the RDM challenge | 2 | the same, asked again after the office text was in |
| 11-14 08:57, 09:01 | Datasets by or about [a person], "the artist, chemist and teacher" | 2 + 3 | the probe of step 6, twice |
| 11-14 08:58 | Find a good exemplary electron holography dataset, a nice variety from different projects | 6 | six searches, the limit raised from 20 to 30, each restating the question more narrowly |
| 11-14 09:02 | Overview of recent datasets by [@weber] | 2 | the first search used generic words ("survey and experimental data") |
| 11-14 17:28 | find all npy datasets created in 2025 | 3 | a date filter (`start_date`, `end_date`) |
| 11-14 17:29 | Who else besides [A] has created npy datasets in 2025, I saw [B], are there more creators? | 5 | a question about a list of people, answered by repeated searches of 20 to 30 hits |
| 11-14 17:36 | what type of data was collected on the Spectra microscope? | 3 | the model searched "Spectra Raman microscope" and "Spectra JEOL": it doesn't know the institute's instruments |
What exists: the search's web page (AI mode without login, through a forwarded port on staging), its answers with "Datasets cited in this answer" and links into the management interface's browser, the records as the crawler publishes them (since 2026-11-14 with the text of `.docx`/`.pptx` files).

## Steps

1. **Open the search.** Does: opens the page; on staging through `ssh -L 13000:…`, in production at an institute URL. Goes wrong: on staging only as `localhost` (other host names send usage statistics, README "Open"). Would ask: "Is this the institute's search or some EU portal?" (the page is branded EOSC Data Commons).

2. **Ask for their latest presentation.** Does: types the question with their name and topic. Seen on 2026-11-14: the first answer said it searches "scientific datasets and research tools only" and can't find talks by a presenter, then offered a Word document and a video from the right folder; only after "There should also be pptx datasets?" did it list five decks, newest first, with the caveat that the records had "slide count, size and issue date, but not slide titles". Goes wrong: the assistant's instructions describe a public data portal, not an institute's file store, so it argues the question is out of scope; the decks' text was missing then (now in, from the 2026-11-14 crawl); the name was searched as a topic, not as the creator (page item 367 b). Would ask: "Why does it say it can't find presentations, and then finds five?"

3. **Open the cited file.** Does: clicks a link in the answer or in the cited list. Seen: links into the management interface's browser; two of five in the cited list were cut (one without `https://`, one with `fz-juelich.ddhoc`), and the export showed mojibake for dashes and umlauts (item 367 c, d; not yet located). Needs: the browser's login. Would ask: "Why does this link go nowhere?"

4. **Ask about the search itself.** Does: "Why don't I find my file from this morning?", "Where are my `._` files?", "How up to date is this?". Today: the assistant knows nothing about the index (which formats, which exclusions, the freshness time T); R46 asks for it. Would ask: "Is my file missing, or not indexed yet, or excluded?"

5. **Tell someone the answer was wrong.** Does: nothing possible; the page has no feedback. @weber asked for "a feature that allows quick feedback and retry to search chats" (2026-11-14, item 385) and for collecting such samples "easily, with user feedback and their permission" (2026-11-15). Would ask: "Who do I tell, and will it get better?"

6. **Check that it doesn't make things up.** Does: asks about a person who is not in the data. Expected: "nothing found", not an invented biography. Not yet observed in a saved answer. Would ask: "Can I quote this answer?"

7. **Ask for a list or a count.** Does (log, 11-14 17:29): "Who else besides [A] has created npy datasets in 2025 … are there more creators?". Seen: five searches of 20 to 30 hits each; a list of creators over all matching records is not what a ranked search returns. Would ask: "Can it just tell me everyone, or how many there are?"

8. **Use the institute's own words.** Does (log, 11-14 17:36): "what type of data was collected on the Spectra microscope?". Seen: the model guessed a Raman microscope and a JEOL instrument; at the institute, "Spectra" is a known microscope. Likewise "find dm4 please" drifted into pharmacology. Would ask: "Doesn't it know our microscopes?"

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
- No way to answer list or count questions over all matching records (step 7).
- The assistant doesn't know the deployment's vocabulary: its instruments, groups, projects, file formats (step 8).

## Acceptance examples

E10, E11, E12, E13, E14, E15 (in `../examples.md`).

## Questionnaire

Not answered for the search user yet: 1.4 (how many users, how often), 2.5 (what happens when an answer is wrong and nobody notices), 2.9 (personal data in queries, feedback and owners' names), 2.6 (how long a user waits for an answer: 2026-11-14's took several tool calls).
