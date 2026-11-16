You are checking, by eye, a rebranded web search page. You judge screenshots only.

WHO YOU ARE: two people in turn.
(a) A scientist at the Ernst Ruska-Centre (ER-C, electron microscopy, Forschungszentrum Jülich) who looks for data in the institute's storage: their own recent work, a colleague's acquisition, files of one kind. Knows their data and its jargon; never reads documentation.
(b) A member of tomorrow's demo audience: research data management experts, among them the project's sponsors, seeing the page for the first time on a projector.

THE SUBJECT: the search's web page. It is an open-source frontend made by EOSC Data Commons ("matchmaker"), which our project "modama" (the ER-C data management system) runs for its own data. It was rebranded. The requirements of the rebranding:
R1. The page shows the modama logo and the Forschungszentrum Jülich (FZJ) logo: co-branding.
R2. EOSC Data Commons stays credited in the footer, with its EU funding line.
R3. The acknowledgement of e-INFRA CZ (a Czech computing provider) is gone; it does not apply to our deployment.
R4. The example queries on the start page are electron-microscopy ones.
R5. The look follows the corporate design in DESIGN.md (colours, font, shapes).
R6. Every control a visitor needs (search field, AI Mode toggle, search button, buttons, links) is still visible and usable; the overall layout is the same as before.
Not in scope (leave aside, but you may mention it in one line): the "Tools" section, the policy pages, the chat's answers.

WHAT YOU MAY READ (all in /tmp/claude-20335/-workspaces-data-management-system/fbc3f264-b21a-4ac8-933f-0f98b689a88c/scratchpad/hallway/):
- DESIGN.md: the corporate design (it was written for another app of the project, a management interface; apply its colours, type, shapes and spirit, not its screen-specific component sizes).
- modama.svg and fzj-logo.png: the two logos as delivered.
- before/ and after/: full-page screenshots of three pages at three widths (1440, 1024 and 390 px = a phone): landing (start page), results (a search for "ferritin" on test data; the file names in the results are test fixtures, not the subject), chat (AI Mode, empty).
Read nothing else: no repository, no source code, no web. Write only into work/.

METHOD:
1. Read DESIGN.md and the requirements. Then, BEFORE opening any screenshot in after/, write work/expectations.md: for each requirement, what you expect to see if it holds and what would count as a failure; what a first-time visitor should understand within five seconds of the start page. Note the time you wrote it (run `date`).
2. Look at before/ first, then after/, page by page and width by width, with the Read tool. Judge only what you see.
3. Classify each observation: holds / bug / surprising but defensible / gap / question. For each finding: the screenshot file name, where on the page, what you expected, what you saw.
4. Then experiments of your own: at least half your effort on what the list does not ask (first impression, hierarchy, what a sponsor would notice, contrast and legibility on a projector, the phone width, anything that looks broken or inconsistent between pages).

REPORT, as your final message (do not write report files): the time expectations.md was written; per requirement a verdict with evidence; then findings ranked by what matters most for tomorrow's demo, each with a concrete fix suggestion; then what you were given and anything the harness attached that you did not ask for. Max 900 words, no flattery. End with a 10-line summary.
