#!/bin/bash
# run.sh MODE N FILL THREADS SUB_BATCH  (MODE: plain | fp | dwarf)
# One throwaway container of perf/batch-memory.py (header's command, the budget's variables), through cpu.py.
# fp: perf record -F 999 -g on the container's process, PYTHONPERFSUPPORT=1; dwarf: --call-graph dwarf, -X perf_jit.
# Needs the running test deployment (its network and embedding cache) and, for fp and dwarf, sudo for perf.
# Output (perf data, logs, the container's /tmp) goes to PERF_OUT, default /var/tmp/perf-wrap.
# The embedding profile was made with it (python/crawler/openspec/changes/cpu-budget/design.md,
# "Where the CPU time goes").
set -euo pipefail
mode=$1 n=$2 fill=$3 t=$4 sb=$5
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
out=${PERF_OUT:-/var/tmp/perf-wrap}
case_=$mode-$n-$fill-$t-$sb${TAG:+-$TAG}
tt=${t/#0/8}
extra=() pyx=()
mkdir -p "$out/tmp-$case_" && chmod 777 "$out/tmp-$case_"
extra=(-v "$out/tmp-$case_":/tmp)
for v in SORT ORT_PROFILE ORT_ARENA ORT_OPT BULK_OUT; do [ -n "${!v:-}" ] && extra+=(-e "$v=${!v}"); done
if [ "$mode" != plain ]; then
  extra+=(-e WAIT=3)
  if [ "$mode" = fp ]; then extra+=(-e PYTHONPERFSUPPORT=1); else pyx=(-X perf_jit); fi
fi
cid=$(docker run -d --rm --network search-stack_search -v "$repo/perf":/probe:ro -v "$here":/wrap:ro \
  -v search-stack_fastembed-airflow:/opt/airflow/cache/fastembed:ro \
  -e PYTHONPATH=/opt/airflow/project/src:/opt/airflow/project \
  -e EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 -e FASTEMBED_CACHE_DIR=/opt/airflow/cache/fastembed \
  -e POSTGRES_USER=chain_reader -e POSTGRES_PASSWORD=test-chain-reader -e POSTGRES_DB=datasetdb \
  -e POSTGRES_ADDRESS_DOCKER=postgres -e OPENSEARCH_ADDRESS_DOCKER=opensearch -e OPENSEARCH_PORT_DOCKER=9200 \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e RAYON_NUM_THREADS="$tt" \
  "${extra[@]}" \
  --entrypoint /opt/airflow/transform-venv/bin/python search-stack-airflow:3.3.2 "${pyx[@]}" /wrap/cpu.py /probe/batch-memory.py "$n" "$fill" "$t" "$sb")
pid=$(docker inspect -f '{{.State.Pid}}' "$cid")
echo "case $case_ container ${cid:0:12} pid $pid"
if [ "$mode" = fp ]; then
  sudo perf record -F 999 -g -p "$pid" -o "$out/$case_.data" 2>"$out/$case_.perf.log" &
elif [ "$mode" = dwarf ]; then
  sudo perf record -F 999 -k 1 --call-graph dwarf,16384 -p "$pid" -o "$out/$case_.data" 2>"$out/$case_.perf.log" &
fi
docker logs -f "$cid" 2>&1 || true
wait
if [ "$mode" != plain ]; then
  # the map files carry the container's pid (1): copy them under the host pid for perf report
  for f in "$out/tmp-$case_"/perf-*.map; do [ -e "$f" ] && sudo cp "$f" "/tmp/perf-$pid.map"; done
  ls "$out/tmp-$case_" | head
  echo "hostpid $pid" > "$out/$case_.pid"
fi
