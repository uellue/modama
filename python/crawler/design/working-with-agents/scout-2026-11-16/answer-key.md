# Analogy scout (O36): answer key, written before any run

Written by the main session on 2026-11-16, before either arm ran. Cases are this project's known
equivalences, described without the project's words. Grade per case: 2 = names the known answer
(any listed form) among its first three suggestions; 1 = names it later, or names a close relative
only; 0 = not named. Also noted: wrong or forced analogies (over-mapping), and whether it says
where the analogy breaks.

- C1 skip rules for a tree walk. Known: gitignore syntax (matched by pathspec / gitwildmatch).
  Close relatives (1): .dockerignore, rsync filter rules, .npmignore, hgignore.
- C2 enabling handlers per installation. Known: a linter's rule selection (ruff or flake8
  `select`/`ignore`/`extend-select`, with code prefixes). Close relatives (1): pylint
  enable/disable, eslint rules config, Python entry points alone (discovery, not selection).
- C3 finding files in a large shared tree. Known: expose the tree as a data repository over a
  harvesting protocol (OAI-PMH) and reuse an existing research-data / dataset search portal or
  catalogue (for example a harvester plus a dataset search engine; CKAN, InvenioRDM, EOSC/OpenAIRE
  style). Close relatives (1): generic enterprise or desktop search over files (Elasticsearch with
  FSCrawler, Recoll, Apache Tika plus Solr), which reuse tools but not the dataset-search idea.
- C4 network file access with institute accounts. Known: an existing file protocol: WebDAV, SMB,
  NFS (any of them; SFTP counts as a close relative). A custom HTTP API should be named as
  reinventing.

Arms: A = neutral descriptions only; B = the same descriptions plus @weber's fuzzing method
(synonyms, inversion of relations, logical operations on the ontology). Same model, no tools,
each arm a separate headless session started in an empty folder outside the repository, so that
no project instructions, memory or vocabulary load.
