# Analogy scout, first run (O36, W17), 2026-11-16

Question: does a fresh agent, without this project's vocabulary, name the established things this project reuses when it gets only a neutral description of the problem? And does @weber's fuzzing method (synonyms, inversion, structural operations; O37) help?

Set-up: `answer-key.md` written at 08:01:54 UTC, before any run; the four problems in `cases.md`; arm A got the cases only, arm B `method-b.md` plus the cases. Each arm one headless Claude Code session (`claude -p … --tools ""`, default model), started in an empty folder outside the repository, so no project instructions, memory or tools. Arm A ran 08:02:03 to 08:03:34 UTC; arm B, first lost to a race in the starting command, 08:03:46 to 08:06:01 UTC. Answers unedited in `answer-a.md`, `answer-b.md`.

Distortion: both answers mention electron microscopy and Helmholtz, which the cases do not. The organisation's instructions about its users load into every session, also in an empty folder; they carry no analogy from the project, but the scouts were not context-free.

## Result

| Case | Known answer | Arm A (neutral) | Arm B (fuzzing method) |
|---|---|---|---|
| C1 skip rules | gitignore via `pathspec` | 2: first, with `pathspec` | 2: first, with `pathspec` |
| C2 enabling handlers | ruff/flake8 `select`/`ignore` | 2: second, after entry points | 2: first |
| C3 finding files | the tree as a data repository over OAI-PMH, plus an existing dataset search | 1: enterprise search, OpenSearch with FSCrawler, storage catalogues | 1: same kind of candidates; but its inversion step wrote "'Find' becomes 'publish so that others can find': research data management catalogues. 'Files stay' becomes 'register in place'", and led only to iRODS |
| C4 file access | WebDAV, SMB, NFS | 2: SMB, WebDAV, Nextcloud; the custom interface called a rebuild | 2: SMB, WebDAV, Nextcloud |
| Usage | | 89 s, $0.20, 8.3 k output tokens | 133 s, $0.28, 12.8 k output tokens |

Both arms said where each fit breaks; neither forced an analogy that does not hold.

## Reading

- One run per arm; no conclusion about the method from these numbers.
- The near analogies (C1, C2, C4), whose descriptions carry the structure, were found without a hint by both arms. The far one, the idea modama is built on, was found by neither, as the research predicts (section 8b).
- Arm B's inversion produced the right reframing for C3 and then matched it against the wrong known things. That is the half of O37 the prompt cannot supply: a library of known things described in the same neutral, structural words (OAI-PMH: a provider publishes dated records, harvesters pull what changed). The next run should test exactly that.

## Next run (proposed, not run)

Arm C: arm B plus a short library of about twenty known things in neutral structural descriptions, OAI-PMH among them and the rest decoys (for example RSS, sitemaps, LDAP, DNS zone transfers, rsync, a message queue), fuzzed the same way; graded by the same key, with three runs per arm to see the spread. Destination: the kaizen plugin (draft issue in `/.claude/drafts/`).
