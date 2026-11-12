# Expectations (written before any experiment), from README "CPU budget" and requirements 2.4

E1 Defaults on this VM (8 CPUs). cpu-budget.sh and logs agree:
 - crawler/crawl-timer: 8 processes (min(8 logical, cap 8)), 1 BLAS/OpenMP thread; "8 CPUs usable (affinity 8, no quota)".
 - airflow-worker-transform: P = min(physical cores, 1024 task slots, mem/1.7GB if limit). If VM shows 8 cores: 8 x 1. If 4 cores (SMT exposed): 4 x 1. Pool transform = P. No memory limit -> memory not a factor.
 - search-api: 8 workers x 1 thread.
 - logs: transform and search-api lines in `docker compose logs`, same numbers as the script. Crawler: only on stderr of a crawl (maybe in crawl-timer logs).
E2 Arithmetic from README alone:
 - 48 logical / 24 cores, no limits: crawler 8 (cap), transform 24 x 1, search-api 48 workers (~22 GB).
 - same + AIRFLOW_TASK_LIMIT=16: transform P=16, T=24/16 -> 1 (README does not say floor vs round; expect floor), pool 16. crawler, search-api unchanged.
E3 `cpus: 2` on crawler -> 2 processes, quota shown as 2; on search-api -> 2 workers. Transform with cpus: 2 -> P=2, T=1.
E4 Overrides: TRANSFORM_PROCESSES=3 -> 3 x (8/3=2) threads, override named; WORKERS=2 -> 2 workers, override named.
   Malformed (0, -1, abc, 1.5): script prints a message naming the variable, service would not start. Exit status nonzero (README does not say -> gap if not stated).
E5 Priority: cpu.weight 20 in crawler, crawl-timer, airflow-worker, airflow-worker-transform, transform; 100 in search-api, matchmaker. Others (opensearch, postgres, broker, scheduler...) not stated, expect 100. cpu-budget.sh prints each of its three services' weight.
E6 Where to set: env of the service via extra compose file (measurement); AIRFLOW_TASK_LIMIT in the deployment's env file (staging.env; for the test deployment unclear: .env?). Restart needed: not documented; expect recreation of the service (`docker compose up -d <svc>`) since the budget is counted at start.
Own:
E7 cpuset "0,1" on crawler -> affinity 2 -> 2 processes.
E8 mem_limit 4g on transform -> P = floor(4/1.7) = 2, T = 8/2 = 4 (or cores/2).
E9 fractional cpus 1.5 -> unclear: floor 1 or ceil 2 (question).
E10 EMBEDDING_THREADS=16 on 8 cores -> accepted as override (operator in control), maybe a warning of oversubscription.
E11 MODAMA_CRAWLER_EXTRACT_WORKERS=20 > cap 8 -> 20 (override wins), named.
E12 --help and wrong argument: usage shown, wrong arg exit nonzero. `staging` arg uses staging env file.
E13 Running containers: OMP/OPENBLAS threads = 1 in env or threads per batch process <= T; search-api has 8 worker processes.
