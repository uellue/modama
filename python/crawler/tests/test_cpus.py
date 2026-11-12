"""The CPUs the crawler may use (the `cpu-budget` spec: "The crawler counts the CPUs it may use", "The CPU quota is
read from the own cgroup v2 group"), with a fake /proc and /sys under tmp_path and a patched affinity."""

import os
import subprocess
import sys
from functools import partial

import pytest
import standin
from modama_crawler import cli, cpus, extraction, selection


def machine(
    root, monkeypatch, *, affinity=8, group="0::/", cpu_max="max 100000", unified=True
):
    """A fake machine under root: `affinity` CPUs, /proc/self/cgroup `group`, the group's `cpu.max` (None: no file),
    and `cgroup.controllers` at the root if the hierarchy is unified (not a hybrid host).

    The crawl's count (`extraction.default_workers`) then reads it."""
    monkeypatch.setattr(cpus.os, "sched_getaffinity", lambda pid: set(range(affinity)))
    (root / "proc/self").mkdir(parents=True)
    (root / "proc/self/cgroup").write_text(group + "\n")
    path = group.partition("0::/")[2]
    cgroup = root / "sys/fs/cgroup" / path
    cgroup.mkdir(parents=True)
    if unified:
        (root / "sys/fs/cgroup/cgroup.controllers").write_text("cpuset cpu io memory\n")
    if cpu_max is not None:
        (cgroup / "cpu.max").write_text(cpu_max + "\n")
    monkeypatch.setattr(cpus, "usable", partial(cpus.usable, root))


def test_the_vm(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=8, cpu_max="max 100000")
    assert extraction.default_workers() == 8


def test_the_dev_server(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=48, cpu_max="max 100000")
    assert extraction.default_workers() == 8


def test_a_container_with_a_cpu_quota(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=8, cpu_max="400000 100000")
    assert extraction.default_workers() == 4


def test_a_fractional_quota(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=8, cpu_max="250000 100000")
    assert cpus.usable().cpus == 3


def test_a_cpuset(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=4)
    assert extraction.default_workers() == 4


def test_python_cpu_count_is_not_an_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHON_CPU_COUNT", "3")
    machine(tmp_path, monkeypatch, affinity=8)
    assert extraction.default_workers() == 8


def test_the_hosts_cgroup(tmp_path, monkeypatch):
    machine(
        tmp_path, monkeypatch, group="0::/user.slice/user-1000.slice/session-5.scope"
    )
    assert not (tmp_path / "sys/fs/cgroup/cpu.max").exists()
    assert cpus.usable() == cpus.Usable(8, None, True)
    assert str(cpus.usable()) == "8 CPUs usable (affinity 8, no quota)"


def test_the_hosts_cgroup_namespace(tmp_path, monkeypatch):
    machine(
        tmp_path,
        monkeypatch,
        group="0::/system.slice/docker-abc.scope",
        cpu_max="200000 100000",
    )
    assert not (tmp_path / "sys/fs/cgroup/cpu.max").exists()
    assert cpus.usable().cpus == 2


def test_no_cgroup_v2(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, group="4:cpu,cpuacct:/", cpu_max="200000 100000")
    assert cpus.usable().cpus == 8
    assert (
        str(cpus.usable()) == "8 CPUs usable (affinity 8, quota not read: no cgroup v2)"
    )


def test_a_hybrid_host(tmp_path, monkeypatch):
    # Review 2026-11-12, finding 2: a 0:: line, but the CPU controller in v1 (no cgroup.controllers)
    machine(
        tmp_path,
        monkeypatch,
        group="0::/system.slice/containerd.service",
        cpu_max=None,
        unified=False,
    )
    assert (
        str(cpus.usable()) == "8 CPUs usable (affinity 8, quota not read: no cgroup v2)"
    )


@pytest.mark.parametrize(
    ("cpu_max", "line"),
    [
        ("400000 100000", "4 CPUs usable (affinity 8, quota 4)"),
        ("250000 100000", "3 CPUs usable (affinity 8, quota 2.5)"),
    ],
)
def test_the_quota_in_the_log_line(tmp_path, monkeypatch, cpu_max, line):
    machine(tmp_path, monkeypatch, cpu_max=cpu_max)
    assert str(cpus.usable()) == line


def test_the_running_machine():
    # No fake: the real /proc and /sys parse, and the count is within the affinity
    count = cpus.usable()
    assert 1 <= count.cpus <= len(os.sched_getaffinity(0))


# The crawl, in process: `records` runs the walk and the extraction as `crawl` does, without a database


@pytest.fixture
def records(tmp_path, monkeypatch):
    """Run `modama-crawler records` on a tree of `*.stand` files with the stand-in formats; returns the datasets."""
    monkeypatch.delenv("MODAMA_CRAWLER_EXTRACT_WORKERS", raising=False)
    calls = tmp_path / "calls"
    formats = standin.collection(calls).formats
    monkeypatch.setattr(
        cli, "_configure", lambda args: (selection.Config(), formats, "rules")
    )
    results = []
    real = extraction.extract

    def spy(result, *args, **kwargs):
        report = real(result, *args, **kwargs)
        results.append(result)
        return report

    monkeypatch.setattr(cli.extraction, "extract", spy)

    def run(contents: dict[str, str], *options: str) -> dict:
        root = tmp_path / "data"
        root.mkdir()
        for name, text in contents.items():
            (root / name).write_text(text)
        assert cli.main(["records", *options, str(root)]) == 0
        (result,) = results
        return {d.anchor: d.extraction for d in result.datasets}

    return run


def test_an_extractor_that_loads_numpy(records, monkeypatch):
    # 256 MiB of address space: enough with one OpenBLAS thread (about 143 MB),
    # not with OpenBLAS's default of one thread per CPU on 8 CPUs (about 430 MB)
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_MEMORY", "256")
    extracted = records({"a.stand": "threads"})["/a.stand"]
    assert extracted.error is None
    assert extracted.extracted.values["threads"] == 1


def test_a_replacement_worker(records, monkeypatch):
    monkeypatch.setattr(extraction, "TASKS_PER_WORKER", 1)
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", "1")
    by_anchor = records({"a.stand": "threads", "b.stand": "threads"})
    values = [by_anchor[a].extracted.values for a in ("/a.stand", "/b.stand")]
    assert values[0]["pid"] != values[1]["pid"]
    assert [v["threads"] for v in values] == [1, 1]


def test_the_crawlers_environment_is_restored(records, monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    extracted = records({"a.stand": "threads"})["/a.stand"]
    assert extracted.extracted.values["omp"] == "1"  # what the worker had
    assert os.environ["OMP_NUM_THREADS"] == "4"
    assert "OPENBLAS_NUM_THREADS" not in os.environ


def test_set_below_the_count(tmp_path, monkeypatch, records):
    machine(tmp_path / "machine", monkeypatch, affinity=48)
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", "2")
    assert cli._budget(cpus.usable()).startswith("CPU budget: 2 worker processes")
    pools = spy_pools(monkeypatch)
    records({"a.stand": "ok a"})
    assert pools == {"walk": 2, "extraction": 2}


def test_set_above_the_count(tmp_path, monkeypatch, records):
    machine(tmp_path / "machine", monkeypatch, affinity=8)
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", "12")
    pools = spy_pools(monkeypatch)
    records({"a.stand": "ok a"})
    assert pools == {"walk": 12, "extraction": 12}


def test_counted_by_default(tmp_path, monkeypatch, records):
    machine(tmp_path / "machine", monkeypatch, affinity=8)
    pools = spy_pools(monkeypatch)
    records({"a.stand": "ok a"})
    assert pools == {"walk": 8, "extraction": 8}


def spy_pools(monkeypatch) -> dict:
    """The number of processes the walk's matching pool and the extraction pool are started with."""
    pools = {}
    real_walk, real_run = cli.walk, extraction._run

    def walk(*args, processes, **kwargs):
        pools["walk"] = processes
        return real_walk(*args, processes=processes, **kwargs)

    def run(tasks, workers, *args, **kwargs):
        pools["extraction"] = workers
        return real_run(tasks, workers, *args, **kwargs)

    monkeypatch.setattr(cli, "walk", walk)
    monkeypatch.setattr(extraction, "_run", run)
    return pools


# The log line and the explanation (spec: "The crawl logs its CPU budget", "The crawler explains its CPU budget")


def test_the_log_line_counted(tmp_path, monkeypatch, records, caplog):
    machine(tmp_path / "machine", monkeypatch, affinity=8)
    records({"a.stand": "ok a"})
    assert (
        "CPU budget: 8 worker processes, 1 math thread each; 8 CPUs usable (affinity 8, no quota)"
        in caplog.messages
    )


def test_the_log_line_set(tmp_path, monkeypatch, records, caplog):
    machine(tmp_path / "machine", monkeypatch, affinity=8)
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", "2")
    records({"a.stand": "ok a"})
    assert (
        "CPU budget: 2 worker processes, 1 math thread each; set by MODAMA_CRAWLER_EXTRACT_WORKERS;"
        " 8 CPUs usable (affinity 8, no quota)"
    ) in caplog.messages


def test_the_log_line_on_the_dev_server_says_the_cap(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=48)
    assert cli._budget(cpus.usable()) == (
        "CPU budget: 8 worker processes, 1 math thread each; 48 CPUs usable (affinity 48, no quota); at most 8"
    )


def test_records_verbose_has_no_budget_line(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    run = subprocess.run(
        [sys.executable, "-m", "modama_crawler", "records", "--verbose", str(tmp_path)],
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    assert b"CPU budget:" not in run.stderr
    # and without --verbose it is there, as typed
    plain = subprocess.run(
        [sys.executable, "-m", "modama_crawler", "records", str(tmp_path)],
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert b"INFO CPU budget: " in plain.stderr


def test_explained_in_a_container_with_a_quota(tmp_path, monkeypatch, capsys):
    machine(tmp_path, monkeypatch, affinity=8, cpu_max="400000 100000")
    monkeypatch.delenv("MODAMA_CRAWLER_EXTRACT_WORKERS", raising=False)
    assert cli.main(["cpu-budget"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert (
        out[0]
        == "CPU budget: 4 worker processes, 1 math thread each; 4 CPUs usable (affinity 8, quota 4)"
    )
    assert "  override: none" in out
    assert any(line.startswith("  MODAMA_CRAWLER_EXTRACT_WORKERS=N ") for line in out)
    assert "  cgroup v2: yes; CPU quota: 4 CPUs (cpu.max of the own cgroup)" in out


@pytest.mark.parametrize("value", ["-1", "0", "abc", "1.5"])
def test_a_setting_that_is_not_a_positive_integer(monkeypatch, caplog, value):
    # Hallway test 2026-11-12: -1 was obeyed, 0 ignored, abc a traceback
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", value)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["cpu-budget"])
    assert stopped.value.code == 2
    assert (
        f"MODAMA_CRAWLER_EXTRACT_WORKERS must be a positive integer: {value!r}"
        in caplog.messages
    )


def test_a_crawl_logs_its_budget_and_restores_the_environment(
    conn, env, tree, monkeypatch, caplog
):
    # Review 2026-11-12, finding 8: the crawl itself, not only `records`
    monkeypatch.delenv("MODAMA_CRAWLER_EXTRACT_WORKERS", raising=False)
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    assert cli.main(["crawl", "--root", str(tree)]) == 0
    assert any(m.startswith("CPU budget: ") for m in caplog.messages)
    assert os.environ["OMP_NUM_THREADS"] == "4"
    assert "OPENBLAS_NUM_THREADS" not in os.environ


def test_a_malformed_setting_leaves_no_run(conn, env, tree, monkeypatch):
    # Review 2026-11-12, finding 1: it exited after the run was recorded, which then stayed "running"
    monkeypatch.setenv("MODAMA_CRAWLER_EXTRACT_WORKERS", "abc")
    with pytest.raises(SystemExit) as stopped:
        cli.main(["crawl", "--root", str(tree)])
    assert stopped.value.code == 2
    conn.commit()
    assert conn.execute("SELECT count(*) FROM crawl_runs").fetchone() == (0,)


def test_one_cpu_is_singular(tmp_path, monkeypatch):
    machine(tmp_path, monkeypatch, affinity=1)
    assert str(cpus.usable()) == "1 CPU usable (affinity 1, no quota)"
