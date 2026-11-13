# Answers given to the hallway tester (for the record)

2026-11-13 ~07:10 UTC, tester's first round (format skill step 1), 7 questions:
- 1 programs and versions: stock answer (maps/stacks); versions not in the key → "decide, assumption with lean" (noted: not answerable from the key)
- 2 grouping: its lean accepted as an open question (stock: "anything else: decide, number it")
- 3 mrcfile: stock (approved, pin current, hand-over)
- 4 summary line: stock
- 5 private/GUI: stock; extended header: its lean as assumption (not in the key)
- 6 .map lies: stock; content check left to it
- 7 real files: stock (none)
- told up front: review skipped, no stack/browse/Docker, OpenSpec CLI fallback (stock)

~07:15, step 2 leans 8–11 (type application/x.mrc, content check for every name, summary line, original_metadata from the 1024-byte header minus extra1/extra2): stock answer only ("leans that follow TEMPLATE.md: yes; anything else: decide, open question"), no coaching.

~07:20, (b) question 12: the docs (crawler README worked example, em README, BACKLOG, TEMPLATE) say the Latin-1 fix and `not_utf8` exist, the code doesn't → "reverted on purpose? which code does staging run?". Stock answer (image installs pyproject's pins; the live column ran the checkout's code) + "decide, assumption". Finding for the record: the docs' worked example names the very fix, so (b) measures how the docs lead to it, not discovery from scratch; the tester checked rsciio 0.15.0 fails the same way (good method). Its lean: regression, re-add fix with fixture and test.
