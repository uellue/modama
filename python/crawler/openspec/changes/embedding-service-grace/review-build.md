# Review of the build (task 8.1), 2026-11-13

By an agent that did not write the code, given the code, the change's proposal, design,
specs and tasks, the setup page and the project rules, not the author's conclusions; against
f115de64 and the working tree then. Attached unreviewed by a person. Each finding was
checked by the author before acting; what became of it is in the last column.

| # | Severity | Finding | Checked | Done |
|---|---|---|---|---|
| R1 | must-fix | `server.py` creates the CUDA session without `onnxruntime.preload_dlls()`, which the benchmark calls (`perf/grace-embedding/bench.py`, worker); the CUDA and cuDNN libraries of the venv's nvidia wheels may not load, and the service would refuse to start ("fell back") | yes: bench.py calls it before every GPU session; not testable without the GPU | `Model` calls it for `cuda`; to be seen on grace (runbook steps 5, 6) |
| R2 | should-fix | runbook step 7 put the token on curl's command line, readable in `/proc/*/cmdline` by other users on grace | yes (the reviewer read curl's cmdline) | the header through `curl -K -` from `printf`, a shell builtin |
| R3 | should-fix | the by-hand checks "`-L` to another destination is refused" could not fail: curl fails on an SSH banner too | yes | the runbook and the tunnel README look for ssh's `administratively prohibited`; `test/run.sh` checks that message too |
| R4 | should-fix | `test_check.py` still set the removed `MODAMA_EMBED_MODEL_FILE` | yes (working tree in flux) | already changed to an `EMBEDDING_MODEL_PATH` folder with the int8 graph |
| R5 | should-fix (guess) | the tiny limit of step 7, 50 MB, is below the weights (66 MB): the step might test a failed start | plausible, not testable here | 300 MB; the step names the failed start as a case to report |
| R6 | nit | `check.py snapshot` keyed records by `record_identifier`, unique only with `endpoint_id` | yes (`tables.sql`) | `records.id`, the primary key |
| R7 | nit | no test of the request order across sub-batches with different texts | yes (a mutation that put the vectors back in sorted order failed only the 3-text test) | `test_the_order_across_sub_batches`: 300 texts; fails against that mutation |
| R8 | nit | a fixed `sleep 45` after `kill -9` in step 7 | yes | polls up to 90 s |
| R9 | nit | the tunnel README's far-end block hard-coded the destinations, appended a second `Match` block when run twice; the `-R` checks by hand hung | yes | a `destinations` variable, guards for `useradd` and the `Match` block, `timeout` and `ExitOnForwardFailure` in the checks; `ssh-keyscan -p` named |
| R10 | nit | the answer's JSON (2,000 vectors, about 15 MB, 0.48 s) was rendered on the worker's event loop; a request whose client has given up is still computed | yes for the rendering | rendered in the thread pool; the abandoned request is left as is (at design D8's load the GPU idles; noted) |
| R11 | nits | task 5.4's "runtest.sh's token check on staging" cannot reach the staging project; the service README mixed root's and the user's home; the tracked empty `testconf/secrets/embed.env`; `onnx` installed for a test without a lock; the compose version for `required: false` on staging unchecked | yes | 5.4: the runbook's step 11 runs the spec's two commands instead (noted in the task); the README says `sudo -s` in the copied folder and why CUDA's cache is not written as yourself; `embed.env` stays tracked and empty as design D11 and task 5.2 say, the runbook's step 9 keeps the token outside the checkout; `onnx` is named in the hand-over as a test-only dependency; step 11 checks `docker compose version` |

Correct as found by the review: the compose rendering with tokens in both files (the worker
gets `embed.env`'s, `search-api` `""`, a missing `embed.env` works); patch 0005's retry and
fallback paths and the masked token in upstream's log; `lazy_load` keeps the threads in
fastembed 0.8.0; the session options match fastembed's; uvicorn 0.54 stops the parent when a
worker fails at start.
