Brief: the prompt summarised under "Brief" below (behaviour and document mode). Usage: 7.5 minutes, 101 k tokens in all (output not separable: `usage.py` found no transcript for this worktree), the session's model (Opus 5.5).

# Hallway test: the CPU budget's documentation and `cpu-budget.sh` (2026-11-12)

**For people.** A fresh agent, playing an ER-C admin new to the stack, had only the search stack's README and requirements-pipeline 2.4. It could say what each service runs on the VM and why, and the diagnostic matched the services' start lines, the CPU weights and the limits and overrides it tried. It found two bugs: the crawler took `MODAMA_CRAWLER_EXTRACT_WORKERS=-1` and ignored `0`, and `AIRFLOW_TASK_LIMIT=0` or `abc` gave a traceback instead of a message. It also found gaps in the README: where to set things, what restart applies them, the rounding, and that the diagnostic shows the next start, not the running one. All of these are fixed, with tests. Three proposals that would change @weber's design are open: TODO 1 to 3.

## Brief

Persona: an admin at ER-C other than the author, who knows Linux and Docker but not the stack (requirements-pipeline 1.4, "Admins at ER-C ... The others in particular need help"). There is no stakeholder record, so the persona comes from the requirements. Allowed reading: `prototypes/search-stack/README.md`, the 2.4 section of `requirements-pipeline.md`, and the usage header of `cpu-budget.sh`. Forbidden: the source, tests, specs, `openspec/`, design notes and git history. Allowed on the running test deployment: `./cpu-budget.sh` (also with `COMPOSE_FILE` and an override file in scratch), `docker compose ps/logs/config`, and read-only `cat` of `/proc` and `/sys` in containers. Up, down, build and writes were forbidden. Mandatory coverage: the defaults against the logs, the arithmetic for 48 CPUs and 24 cores with and without the task limit, a CPU limit, overrides good and malformed, the priority, and where to set what. Half of the effort was to go outside that list. The expectations were written at 09:14:00Z, before the first experiment; they are in `2026-11-12-cpu-budget/expectations.md`, and the override files are next to it. `2026-11-12-cpu-budget/rerun.sh` repeats the experiments.

## What held up

- E1: the defaults (8, 8 × 1, 8 workers) are the same in `./cpu-budget.sh` and in the start lines.
- E2: the arithmetic for AIRFLOW_TASK_LIMIT 3 and 16.
- E3: `cpus: 2` on three services.
- E4: the overrides, including "32 threads exceed the 8 CPUs".
- E6: the weights, 20 against 100.
- E7: cpusets.
- E11: the variables in the processes, 1 thread per batch process when idle.
- WORKERS=0, TRANSFORM_PROCESSES=abc and EMBEDDING_THREADS=1.5 each stop with a message naming the variable, exit 1.

## Fixed, each with its test

| Finding | Fix | Test | What would have caught it |
|---|---|---|---|
| `MODAMA_CRAWLER_EXTRACT_WORKERS` `-1` obeyed, `0` ignored, `abc`/`1.5` traceback | `cli._workers` exits 2 with a message, as `_threads` does | `test_cpus.py::test_a_setting_that_is_not_a_positive_integer` (4 values) | a spec scenario for a malformed crawler setting; the spec had one only for the stack's services |
| `AIRFLOW_TASK_LIMIT` `0` gave a ZeroDivisionError, `abc` a traceback | `budget._slot` checks both task limits and names AIRFLOW_TASK_LIMIT | `test_budget.py::test_a_task_limit_that_is_not_a_positive_integer` (3 values) | the same: the "Malformed input" requirement named files and overrides, not Airflow's settings |
| "1 CPUs usable" | singular in both counts | `test_one_cpu_is_singular`, `test_one_cpu_and_one_core_are_singular` | a test at the smallest count |
| "physical cores usable: 2 (topology)" when the quota gave the 2 | the line says "capped by the CPU quota" | (explain's text; read by eye) | none; wording |
| README: where to set AIRFLOW_TASK_LIMIT in the test deployment, what applies a change, what it interrupts, the rounding, P from T alone, next start against running, the script's exit codes | README, "CPU budget": "The arithmetic" and "To change it" | read again; the commands run as typed | a hallway test before the hand-over (this one) |
| `--help` printed only the usage | `--help` prints the header | run as typed | the CLI checklist's help point |

Not a defect: the tester's E9, a running crawler with a 4-CPU quota at 09:14 that the diagnostic did not show. That was task 4.1's run with `cpus: 4`, by the main session, restored at 09:14:54.

## Answers given during the run

The tester asked five questions. The main session's answers went further than the design in three places: rounding by pool kind, a memory warning, and a mismatch line in the diagnostic. These are leans of the main session, not decisions, so they were not built. They are TODOs for @weber below, and the hand-over lists the deviation from the answers.

## TODO for @weber

- **1** Fractional quotas: D2 rounds up (`cpus: 2.5` counts 3, as dask does), and the crawler's spec says so. For a math pool this means T × P up to 3 on 2.5 CPUs, against 2.4's "within the CPU quota". Lean: math pools (the transform worker's cores) round down, at least 1; I/O pools (the crawler, the search API's workers) round up.
- **2** No memory limit (159): on the VM the diagnostic expects up to 13.6 GB for 8 batch processes of 512-token texts, with about 12 GiB available, and gives no warning. Lean: one warning line in the diagnostic and the start log when P × 1.7 GB exceeds `MemAvailable`, naming `TRANSFORM_PROCESSES`, without changing P.
- **3** The diagnostic shows the next start only. Lean: leave it so; the README now says that the running choice is in the start log line. A line per service when the running container's limits differ from the next start would be extra, and nobody needs it yet.
- **4** Units: the 1.7 GB are decimal (10⁹), and `mem_limit: 4g` shows as 4.3 GB. The README says so. Lean: leave it.
- **5** The crawler gives no "exceeds the CPUs" warning for a setting above them, but the search API does. Lean: leave it; the crawler's setting above the CPUs is for measurements (spec), and its processes mostly wait on NFS.

## Not covered

SMT (the VM has 1 thread per core), `./cpu-budget.sh staging`, and the pool's size: the tester had no read-only way to see the pool. The main session checked it: `airflow pools list` shows `transform` 8 and `filemeta` 4.
