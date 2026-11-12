"""budget.py against the scenarios of the cpu-budget spec (python/crawler/openspec/changes/cpu-budget/), with a fake
/proc and /sys under tmp_path and a patched affinity. Standard library and pytest only; no Airflow:

  ~/.venv/bin/pytest prototypes/search-stack/cpu-budget
"""

import budget
import pytest

GB = 1_000_000_000
NO_LIMIT = (1024, 1024)  # the base compose file's AIRFLOW_TASK_LIMIT


def fake(
    root,
    monkeypatch,
    *,
    cpus=range(8),
    siblings=None,
    name="core_cpus_list",
    group="0::/",
    cpu_max="max 100000",
    memory_max="max",
    unified=True,
):
    """A machine under root: the affinity `cpus`; `siblings` maps a CPU to its core's CPU list (default: its own
    core; None for no topology at all); the own group's cpu.max and memory.max (None: no file); `cgroup.controllers`
    at the root if the hierarchy is unified (not a hybrid host)."""
    monkeypatch.setattr(budget.os, "sched_getaffinity", lambda pid: set(cpus))
    (root / "proc/self").mkdir(parents=True)
    (root / "proc/self/cgroup").write_text(group + "\n")
    cgroup = root / "sys/fs/cgroup" / group.partition("0::/")[2]
    cgroup.mkdir(parents=True)
    if unified:
        (root / "sys/fs/cgroup/cgroup.controllers").write_text("cpuset cpu io memory\n")
    for file, text in (("cpu.max", cpu_max), ("memory.max", memory_max)):
        if text is not None:
            (cgroup / file).write_text(text + "\n")
    if siblings is not False:
        for cpu in cpus:
            topology = root / f"sys/devices/system/cpu/cpu{cpu}/topology"
            topology.mkdir(parents=True)
            (topology / name).write_text((siblings or {}).get(cpu, str(cpu)) + "\n")
    try:
        return budget.machine(root)
    except budget.Malformed:
        return None  # the test runs main() or machine() itself


def smt(n_cores):
    """Two threads per core, numbered as Linux does: CPU c and c + n_cores share core c."""
    return {c: f"{c % n_cores},{c % n_cores + n_cores}" for c in range(2 * n_cores)}


DEV = {"cpus": range(48), "siblings": smt(24)}


# The transform worker counts the physical cores it may use


def test_cores_the_vm(tmp_path, monkeypatch):
    assert fake(tmp_path, monkeypatch).cores == 8


def test_cores_the_dev_server(tmp_path, monkeypatch):
    assert fake(tmp_path, monkeypatch, **DEV).cores == 24


def test_cores_a_container_with_a_cpu_quota(tmp_path, monkeypatch):
    assert fake(tmp_path, monkeypatch, **DEV, cpu_max="400000 100000").cores == 4


def test_cores_a_cpuset_of_8_cpus_on_8_cores(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpus=[0, 2, 4, 6, 8, 10, 12, 14], siblings=smt(24))
    assert m.cores == 8


def test_cores_a_cpuset_of_8_cpus_on_4_cores(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpus=[0, 1, 2, 3, 24, 25, 26, 27], siblings=smt(24))
    assert m.cores == 4


def test_cores_only_the_old_topology_name(tmp_path, monkeypatch):
    m = fake(
        tmp_path,
        monkeypatch,
        cpus=range(8),
        siblings=smt(4),
        name="thread_siblings_list",
    )
    assert m.cores == 4


def test_cores_no_topology(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, siblings=False)
    assert (m.cores, m.topology) == (8, False)
    line = budget.transform(m, slots=NO_LIMIT).line
    assert (
        "8 cores usable (8 logical CPUs, no quota; cores are logical CPUs: no topology)"
        in line
    )


# The CPU quota is read from the own cgroup v2 group (the crawler's scenarios, for budget.py's own reading)


def test_quota_the_hosts_cgroup(tmp_path, monkeypatch):
    m = fake(
        tmp_path, monkeypatch, group="0::/user.slice/user-1000.slice/session-5.scope"
    )
    assert not (tmp_path / "sys/fs/cgroup/cpu.max").exists()
    assert (m.logical, m.quota, m.cgroup_v2) == (8, None, True)


def test_quota_the_hosts_cgroup_namespace(tmp_path, monkeypatch):
    m = fake(
        tmp_path,
        monkeypatch,
        group="0::/system.slice/docker-abc.scope",
        cpu_max="200000 100000",
    )
    assert (m.logical, m.cores) == (2, 2)


def test_quota_no_cgroup_v2(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, group="4:cpu,cpuacct:/", cpu_max="200000 100000")
    assert (m.logical, m.cgroup_v2) == (8, False)
    assert "quota not read: no cgroup v2" in budget.search_api(m).line


def test_quota_a_hybrid_host(tmp_path, monkeypatch):
    # Review 2026-11-12, finding 2: a 0:: line, but the controllers in v1 (no cgroup.controllers)
    m = fake(
        tmp_path,
        monkeypatch,
        group="0::/system.slice/x.service",
        cpu_max=None,
        memory_max=None,
        unified=False,
    )
    assert (m.cgroup_v2, m.quota, m.memory) == (False, None, None)
    assert "quota not read: no cgroup v2" in budget.search_api(m).line


def test_quota_fractional(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpu_max="250000 100000")
    assert (m.logical, m.cores) == (3, 3)


def test_quota_missing_cpu_max(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpu_max=None)
    assert (m.logical, m.quota) == (8, None)


# Malformed input stops the start of a search-stack service


def start(monkeypatch, tmp_path, environ, service="transform"):
    """main() as the container runs it; returns its status and the commands it would have run."""
    ran = []
    monkeypatch.setattr(budget, "_slots", lambda: NO_LIMIT)
    monkeypatch.setattr(budget.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    monkeypatch.setattr(budget.os, "execvpe", lambda file, args, env: ran.append(args))
    command = (
        ["celery", "worker", "--queues", "transform"]
        if service == "transform"
        else ["uvicorn", "app"]
    )
    return budget.main([service, "--", *command], environ, tmp_path), ran


def test_a_malformed_quota(tmp_path, monkeypatch, capsys):
    fake(tmp_path, monkeypatch, cpu_max="unlimited")
    status, ran = start(monkeypatch, tmp_path, {})
    err = capsys.readouterr().err
    assert status == 2 and ran == []
    assert "cpu.max" in err and "'unlimited'" in err


def test_not_a_number(tmp_path, monkeypatch, capsys):
    fake(tmp_path, monkeypatch)
    status, ran = start(monkeypatch, tmp_path, {"TRANSFORM_PROCESSES": "four"})
    assert status == 2 and ran == []
    assert (
        "TRANSFORM_PROCESSES must be a positive integer: 'four'"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize("file", ["memory.max", "topology"])
def test_other_malformed_files(tmp_path, monkeypatch, file):
    if file == "memory.max":
        fake(tmp_path, monkeypatch, memory_max="lots")
    else:
        fake(tmp_path, monkeypatch, siblings={0: "zero"})
    with pytest.raises(
        budget.Malformed,
        match="memory.max: .*'lots'" if file == "memory.max" else "core_cpus_list",
    ):
        budget.machine(tmp_path)


# The transform worker sizes its processes and threads


def size(b):
    return b.processes, b.threads


def test_sizes_the_dev_server(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    assert size(budget.transform(m, slots=(16, 16))) == (16, 1)


def test_sizes_the_dev_server_without_the_limit(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    assert size(budget.transform(m, slots=NO_LIMIT)) == (24, 1)


def test_sizes_the_vm(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch)
    assert m.memory is None
    assert size(budget.transform(m, slots=NO_LIMIT)) == (8, 1)


def test_sizes_memory_is_the_limit(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV, memory_max=str(16 * GB))
    assert size(budget.transform(m, slots=NO_LIMIT)) == (9, 2)


def test_sizes_parallelism_is_the_limit(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpus=range(64))
    assert size(budget.transform(m, slots=(1024, 32))) == (32, 2)


# The transform worker's budget can be set


def test_processes_set(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    b = budget.transform(m, slots=NO_LIMIT, processes=4)
    assert size(b) == (4, 6)
    assert "4 processes × 6 threads" in b.line and "TRANSFORM_PROCESSES=4 set" in b.line


def test_both_set_beyond_the_cores(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    b = budget.transform(m, slots=NO_LIMIT, processes=24, threads=2)
    assert size(b) == (24, 2)
    assert "48 threads exceed the 24 cores" in b.line


def test_threads_set(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    assert size(budget.transform(m, slots=(16, 16), threads=3)) == (8, 3)


# The transform worker logs its CPU budget


def test_log_line_the_dev_server(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV)
    assert budget.transform(m, slots=(16, 16)).line == (
        "CPU budget: 16 processes × 1 thread; 24 cores usable (48 logical CPUs, no quota); no memory limit; "
        "16 task slots (max_active_tasks_per_dag 16, parallelism 16); no override"
    )


def test_log_line_a_memory_limit(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, **DEV, memory_max=str(16 * GB))
    assert (
        "memory for 9 (memory.max 16.0 GB, 1.7 GB each)"
        in budget.transform(m, slots=NO_LIMIT).line
    )


def test_log_line_an_override(tmp_path, monkeypatch, capsys):
    fake(tmp_path, monkeypatch, **DEV)
    start(monkeypatch, tmp_path, {"TRANSFORM_PROCESSES": "4"})
    line = capsys.readouterr().err
    assert (
        line.startswith("CPU budget: 4 processes × 6 threads;")
        and "TRANSFORM_PROCESSES=4 set" in line
    )


# The start: the pool, the variables, the exec (D5, D6 (i))


def test_the_start_of_the_transform_worker(tmp_path, monkeypatch):
    fake(tmp_path, monkeypatch)
    environ = {"OMP_NUM_THREADS": "8"}
    _, (pool, command) = start(monkeypatch, tmp_path, environ)
    assert pool[:5] == ["airflow", "pools", "set", "transform", "8"]
    assert command == [
        "/entrypoint",
        "celery",
        "worker",
        "--queues",
        "transform",
        "--concurrency",
        "8",
    ]
    assert {k: environ[k] for k in budget.BLAS} == dict.fromkeys(budget.BLAS, "1")
    assert (environ["EMBEDDING_THREADS"], environ["RAYON_NUM_THREADS"]) == ("1", "1")


def test_the_pool_cannot_be_set(tmp_path, monkeypatch, capsys):
    # Review 2026-11-12, finding 4: Airflow's database not up yet after a host restart
    fake(tmp_path, monkeypatch)
    monkeypatch.setattr(budget, "_slots", lambda: NO_LIMIT)

    def fail(cmd, **kw):
        raise budget.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(budget.subprocess, "run", fail)
    started = []
    monkeypatch.setattr(budget.os, "execvpe", lambda *a: started.append(a))
    assert budget.main(["transform", "--", "celery", "worker"], {}, tmp_path) == 2
    assert started == []
    assert "setting the pool transform failed" in capsys.readouterr().err


def test_the_start_of_the_search_api(tmp_path, monkeypatch):
    fake(tmp_path, monkeypatch)
    environ = {"WORKERS": ""}  # our Dockerfile clears upstream's WORKERS=6
    _, ran = start(monkeypatch, tmp_path, environ, service="search-api")
    assert ran == [["uvicorn", "app", "--workers", "8"]]  # no pool
    assert (
        environ["EMBEDDING_THREADS"] == "1" and environ["OPENBLAS_NUM_THREADS"] == "1"
    )


# The search API sizes its workers and their threads; its budget can be set; it logs it


def test_search_api_the_vm(tmp_path, monkeypatch):
    assert size(budget.search_api(fake(tmp_path, monkeypatch))) == (8, 1)


def test_search_api_a_container_with_a_cpu_quota(tmp_path, monkeypatch):
    assert size(
        budget.search_api(fake(tmp_path, monkeypatch, cpu_max="200000 100000"))
    ) == (2, 1)


def test_search_api_the_dev_server(tmp_path, monkeypatch):
    assert size(budget.search_api(fake(tmp_path, monkeypatch, **DEV))) == (48, 1)


def test_search_api_workers_set(tmp_path, monkeypatch, capsys):
    fake(tmp_path, monkeypatch)
    _, ran = start(monkeypatch, tmp_path, {"WORKERS": "2"}, service="search-api")
    assert ran == [["uvicorn", "app", "--workers", "2"]]
    assert "CPU budget: 2 workers × 1 thread;" in capsys.readouterr().err


def test_search_api_log_line_the_vm(tmp_path, monkeypatch):
    assert budget.search_api(fake(tmp_path, monkeypatch)).line == (
        "CPU budget: 8 workers × 1 thread; 8 CPUs usable (affinity 8, no quota); no override"
    )


# explain (D11): the start's line, the inputs, how to set; a malformed file fails


@pytest.mark.parametrize(
    ("machine", "slots"),
    [({**DEV}, (16, 16)), ({}, NO_LIMIT)],
    ids=["dev server", "vm"],
)
def test_explain_prints_the_starts_line(tmp_path, monkeypatch, capsys, machine, slots):
    m = fake(tmp_path, monkeypatch, **machine)
    monkeypatch.setattr(budget, "_slots", lambda: slots)
    assert budget.main(["explain", "transform"], {}, tmp_path) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == budget.transform(m, slots=slots).line
    assert any(line.startswith("  TRANSFORM_PROCESSES=N ") for line in out)
    assert any(line.startswith("  expected memory: up to ") for line in out)
    assert budget.main(["explain", "search-api"], {}, tmp_path) == 0
    assert capsys.readouterr().out.splitlines()[0] == budget.search_api(m).line


def test_explain_a_malformed_quota(tmp_path, monkeypatch, capsys):
    fake(tmp_path, monkeypatch, cpu_max="unlimited")
    assert budget.main(["explain", "search-api"], {}, tmp_path) == 2
    assert "cpu.max" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "abc", "-3"])
def test_a_task_limit_that_is_not_a_positive_integer(
    tmp_path, monkeypatch, capsys, value
):
    # Hallway test 2026-11-12: AIRFLOW_TASK_LIMIT=0 gave a ZeroDivisionError, abc a traceback
    fake(tmp_path, monkeypatch)
    monkeypatch.setattr(
        budget, "_slots", lambda: (budget._slot(value, "max_active_tasks_per_dag"), 16)
    )
    assert budget.main(["explain", "transform"], {}, tmp_path) == 2
    assert (
        f"AIRFLOW_TASK_LIMIT) must be a positive integer: {value!r}"
        in capsys.readouterr().err
    )


def test_one_cpu_and_one_core_are_singular(tmp_path, monkeypatch):
    m = fake(tmp_path, monkeypatch, cpus=[0])
    assert "; 1 CPU usable (affinity 1" in budget.search_api(m).line
    assert "; 1 core usable (1 logical CPUs" in budget.transform(m, slots=NO_LIMIT).line


def test_the_running_machine():
    # No fake: this machine's /proc and /sys parse
    m = budget.machine()
    assert 1 <= m.cores <= m.affinity
