Brief: `2026-11-16-matchmaker-branding/brief.md`. Usage: under 1 minute (43 s), 4,669 output tokens, Sonnet 5.5.

# Hallway test: the co-branded search page (2026-11-16)

**Summary.** A fresh agent judged screenshots of matchmaker's start, results and chat pages at 1440, 1024 and 390 px, before and after patches 0004 (DESIGN.md's colours and fonts) and 0005 (co-branding), as an ER-C scientist and as a member of the demo audience of 2026-11-17. The requirements held: modama and FZJ logos, EOSC credited with its funding line, e-INFRA CZ gone, electron-microscopy examples, DESIGN.md's look, every control still there. Its top finding was real and fixed the same day: FZJ's logo was missing in AI Mode, the demo's page, since the chat page has no footer. The cramped word spacing it saw is Plus Jakarta Sans' own narrow space, the same in mgmtinterface-new; a question for DESIGN.md, not a bug. The rest was upstream's, unchanged by the patches.

Run without the person (@weber away until staging, 2026-11-16): the leans were mine and are listed below. Mode: by eye, on screenshots taken by `./runtest.sh brand` (`prototypes/search-stack/README.md`, "Branding check"); the skill's xterm driver does not apply to a web page, and the screenshots were the tester's only view. The controls themselves (visible, reachable by Tab, usable) were checked by that script, not by the tester: 9 of 9 PASS before and after the fix.

## Leans taken (no one to ask)

- **Persona:** "Search user" of `design/stakeholders.md` plus a member of the demo audience (same file, "Seen doing"). Implemented as stated.
- **Reading:** DESIGN.md, the requirements R1 to R6 in the brief, the two logos, the screenshots. Nothing else. The tester named what the harness attached (instruction files, memory index, git status) and said it did not use it.
- **Model:** Sonnet, enough for judging by eye. As stated.
- **Coverage:** R1 to R6, plus half its effort on its own experiments. It opened 9 of the 18 screenshots and said which (not `before/results-*`, most `before/` narrow widths, `after/results-1024`, `after/chat-1024`).

## Expectations

Written at 11:37:17 UTC, before the first `after/` screenshot (`2026-11-16-matchmaker-branding/expectations.md`).

## Findings and what became of them

| # | Finding | Verified | Outcome | What would have caught it |
|---|---|---|---|---|
| 1 | Chat page (AI Mode) shows no FZJ logo; it has no footer | yes, `after/chat-1440.png` | Fixed: FZJ's logo next to modama's, with a divider, in the chat header; `./runtest.sh brand` 9/9 PASS | A requirement saying on which pages co-branding must show; R1 said only "the page" |
| 2 | Results header has no FZJ logo | yes | Fixed on phones and from 1280 px; between 640 and 1280 px it would take 210 px from the search field (530 → 320 px at 1024, measured), so there only the footer has it | The same |
| 3 | Word spacing cramped | measured: a space is 3.0 px at 16 px in Plus Jakarta Sans, 4.45 px in the fallback sans; CSS sets no letter or word spacing | Not changed: DESIGN.md's font, the same in mgmtinterface-new. Question below | — |
| 4 | Phone: AI Mode toggle icon only, placeholder "Ask AI…" | yes, the same in `before/landing-390.png` | Upstream's, unchanged | — |
| 5 | FZJ small top left, modama large in the middle: intended hierarchy? | — | Question below | — |
| 6 | Empty "Dataset Statistics" box | the same before; the test stack has no statistics | Not in scope; check on staging | — |
| 7 | Subtitle and Tools not about electron microscopy | — | Tools out of scope (@weber); subtitle unchanged | — |
| 8 | Play / Source / Cite in three colours; "ERC" unexplained | upstream's | Not in scope | — |
| 9 | Footer tall on the phone; grant text small and light | upstream's sizes | Not in scope | — |

## TODO for @weber

- **T1 Site name.** The title says "modama search"; CONTEXT.md has no term for the search. Lean: keep it until there is one, then change `root.tsx` in 0005.
- **T2 Word spacing.** Plus Jakarta Sans has a narrow space; on a projector words seem to run together. Lean: leave it (one font in all of modama's pages); if it bothers, change DESIGN.md, and both apps with it.
- **T3 Hierarchy.** FZJ top left, modama as the large logo, EOSC in the footer. Lean: keep (FZJ hosts, modama is the product, EOSC built the software).
- **T4 Example queries.** Chosen without seeing staging's data: "Electron energy-loss spectra (EELS) of oxide interfaces", "4D-STEM scans recorded with the EMPAD detector", "Atomic-resolution HAADF STEM images". Lean: try them on staging and replace any that find nothing.

## Re-run

`2026-11-16-matchmaker-branding/prepare.sh DIR` copies the inputs from the last `./runtest.sh brand baseline` and `./runtest.sh brand` and writes the brief for DIR.
