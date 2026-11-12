# Proposal: recognition checks the content

Renamed from `extractor-rejects-type` (decision 168, 2026-11-12); the branch keeps its name, `worktree-agent-acfa97ac4ec4925f5`.

## In short

A file whose name says one type but whose content says another should not be published under the name's type. Example: a text file `notes.gtg` is published today as "Gatan Digital Micrograph .gtg tag file", because the name `*.gtg` decides without the file being read.

With this change, the format that knows the type checks the file's first bytes while it recognises the directory, and can say "this file is not of my type". The file then gets the type it would have had without that name rule, in the same pass: `notes.gtg` becomes a plain text file, with no warning. The other formats see the new type: a DM3 image misnamed `conditions.dmw` is recognised and extracted as a DM3 image.

This separates "not actually K2IS" from "something is broken" (@weber, 2026-11-12). A text `X_.gtg` next to 8 sector files is not a K2IS capture: K2IS checks the tag file before it groups. A `.gtg` with the right header whose tags cannot be read is still a broken capture: its extraction fails and is reported as today.

A file typed by its content, not by its name, keeps its type. Nothing new is stored. The reason ("em/k2is: not application/x.dm-gtg, no DM4 header") shows in `records --verbose` and in `modama-chain trace`.

## Why

A file that only one name rule matches is typed by its name alone. Detection returns before it reads the file (`mime.py:179-184`). With `dm-containers-and-k2is`, a text or empty `notes.gtg` or `x.dmw` is therefore described as a Gatan file (that change's review, finding 1). That is a false statement to a searcher, the problem staging finding F15 set out to fix. The review proposed giving these names a second rule (the globs on `application/octet-stream`), so that the content always decides. @weber prefers that the format says "this is not, in fact, a Gatan gtg file". This works for name collisions nobody knows about yet, and the name keeps its fast match for every other format.

The first version of this change rejected the file at extraction. @weber's follow-up (2026-11-12, question 149, "149 sounds sensible!"): decide it during recognition. Recognition can already read a file's first bytes (`Directory.read`, `formats/__init__.py:175-184`, 1 MiB per format call), and EMPAD uses that in its `recognize`. What is missing is a way for a format to say, while recognising, "this file is not of the type its name gave it".

Serves R25 (honest types), R30 (records that don't mislead a searcher), R23/R8 (a failure stays a reported failure), R10 (a re-crawl does no work for an unchanged file).

## What Changes

- While recognising a directory, a format can say that one of its files is **not of the type the file's name gave it**, with a reason.
- **Only a file typed by its name alone qualifies**: exactly one best name rule gave it the type. Its type becomes what detection gives without that rule: another name rule, else the content, else `text/plain` or `application/octet-stream`. This takes effect at once, for the formats that run after it in the same directory and for the file as a single file. A format for the new type can claim it if it runs later. A format that drops types must therefore run before the formats of the types its files may fall back to. The format's priority says that.
- A file typed by its content keeps its type. The crawl warns, naming the format and the reason: a content match that a format contradicts points at a weak content rule (decision 145, flow D).
- The reason goes into the **basis** of the dataset that holds the file ("single file; em/k2is: not application/x.dm-gtg, no DM4 header"). `records --verbose` shows it, also for a single file, and the crawler line of `modama-chain trace` shows every dataset's basis. No warning, and no count in the crawl report (decision 148).
- **Nothing new is stored.** The type and basis are stored with the dataset as they are today. An unchanged directory keeps them on the next crawl without reading a file. A changed file is checked again.
- **In `modama-formats-em`** (to be folded into `dm-containers-and-k2is`, decision 144): a small format `em/dmw` checks each `.dmw` file's 16-byte DM4 header. K2IS checks each `.gtg` file's header before it groups a capture. Both run before the DM3 and DM4 formats. Files without the header lose the name's type. The section "To fold into dm-containers-and-k2is" in design.md and tasks.md holds this part.

Behaviour towards the user:
- A searcher or harvester sees a stray `notes.gtg` holding text as `dc:format` `text/plain`, described as a plain text document. An empty `x.dmw` becomes `text/plain`, as an empty file without a name rule is today. A DM3 image named `conditions.dmw` becomes a DM3 record with its image metadata. Their datestamps move once.
- A text `X_.gtg` next to 8 sector files gives 9 single files and the existing warning about sector files without a tag file. Today it gives a K2IS record and an extraction failure.
- An admin sees the reason in `records --verbose` (a comment before that file's record) and in `modama-chain trace` (the crawler line's basis). The crawl report has no new warning or count.
- No schema change, and no database recreation for this part.

Out of scope:
- Rejecting files typed by their content.
- Checking the fallback type again: one drop per file per crawl.
- Calling formats that already ran on a directory again after a drop.
- A count of rejections in the crawl report.
- Metadata from `.dmw` files.
- The DM3 header for `.dmw` and `.gtg` (decision 147).
- Generic extractors on subtypes (Q15).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `recognition`: a format can say that a file is not of the type its name gave it. The file then gets the type detection gives without it, at once. A file typed by its content keeps its type, with a warning. A failed or over-budget format call leaves every type as it was.
- `records-cli`: a single file whose name type a format dropped gets a recognition comment with its basis.
- `chain-trace`: the crawler line shows the basis of the dataset that holds the item.

## Impact

- Crawler:
  - `formats/__init__.py`: `Directory.not_of_type`, and `run_post` reading the entries' current types.
  - `mime.py`: `by_name`, the type a name alone gives, and detection with a type excluded.
  - `cli.py`: the `records` comment.
  - Docs: `formats/TEMPLATE.md`, `README.md` (Walk and recognise), `BACKLOG.md`.
- `python/search-chain`: the trace's crawler line reads `datasets.basis`. Its README, "What it reads", says so.
- `modama-formats-em` on branch `dm-containers`: the format `em/dmw`, the header check in K2IS, and the priority 61 for both. Fixtures and that change's D1, spec requirements and XML comments (design.md, "To fold into dm-containers-and-k2is").
- No new dependency. No schema change.

## Decisions by @weber, 2026-11-12 (questions 144 to 149, answered on the open-items page)

- **144, where the `em` part goes:** "yes let's group the changes together". It is folded into `dm-containers-and-k2is` as its fix for review finding 1, and the two land together. Until it is moved, the em part is written here in a marked section.
- **145, files typed by their content:** they do not fall back (flow D in design.md). A format that says such a file is not of its type gets a warning, not a new type.
- **146, the fallback type's own extractor:** resolved by 149. The new type is set during recognition, so a format of that type that runs later claims the file, and its extractor runs as for any of its files (flow C). The order rule is in design.md, D3.
- **147, the DM3 header:** "that depends on what we find in the wild. DMW should/could also exist as DM3, I think." @weber makes fresh `.dmw` files with a current GMS (his TODO, open item 155). Until then the checks accept the DM4 header only, to be revisited with those files.
- **148, showing rejections:** "a normal rejection is business as usual. It should go into the per-item tracing / observability". So: no count in the crawl report, and no warning. The reason is in the dataset's basis, shown by `records --verbose` (spec `records-cli`) and by `modama-chain trace` (spec `chain-trace`).
- **149, check during recognition instead of at extraction:** "149 sounds sensible!" This revision of the change.
- **D2's case of the first version** (a single file in a subdirectory that a collection format adopted as a part): "Let's go with your lean until we find a specific example where that is wrong". It holds without a rule of its own. The subdirectory is recognised before its parent, so the file already has its new type when the parent adopts it.
- **165, the order rule:** "yes, go with your lean please!": a format that drops types runs before the formats its files fall back to (`em/dmw` and K2IS at priority 61, D3).
- **166, the re-detection and the read budget:** "yes, please change. First we make it work, and we fix the 'big ticket items'. This sounds like a keyhole case where we focus on it working correctly. We fix when it shows up as a real world drain in monitoring or benchmarking." Read as: the re-detection is not charged to the format's 1 MiB budget (the alternative), so a folder of many misnamed files cannot push a format over its budget and put every type back; its reads are the walk's ordinary reads.
- **167, the trace shows every dataset's basis:** "Yes, longer line is OK. we adjust when we encounter it in the real world."
- **168, the name:** "user facing yes, but we don't need to muck with branch names as long as we know what is what." The change is renamed `recognition-checks-content` (its directory and title, what people read); the branch keeps its name.
- Also from @weber, for later (backlog): "it would be good to be able to scan a real world crawl result for 'suspicious' results. Maybe the crawling, recognition and extraction logic could tag 'interesting' results for manual follow-up?"
