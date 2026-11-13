#!/usr/bin/env bash
# Embedding benchmark, best CPU against best GPU (README.md):
#   ./run.sh quick|full [all|cpu|gpu] [--force]
# --force: the GPU part even while other processes use the GPU.
# Environment (optional): VENV_CPU, VENV_GPU (default ./venv-cpu, ./venv-gpu), RESULTS (default
# ./results), FASTEMBED_CACHE_DIR (default ./cache: the model's files and our variants of it),
# GPU_MEM_FRACTION (default 0.5: of the GPU's memory, for all GPU workers together).
set -euo pipefail
force=()
if [ "${*: -1}" = --force ]; then
	force=(--force)
	set -- "${@:1:$#-1}"
fi
mode="${1:-}"
parts="${2:-all}"
case "$mode" in
quick) texts=4000 ;;
full) texts=20000 ;;
*) mode="" ;;
esac
case "$parts" in
all | cpu | gpu) ;;
*) mode="" ;;
esac
if [ -z "$mode" ]; then
	echo "usage: $0 quick|full [all|cpu|gpu] [--force]" >&2
	exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
venv_cpu="${VENV_CPU:-$here/venv-cpu}"
venv_gpu="${VENV_GPU:-$here/venv-gpu}"
export FASTEMBED_CACHE_DIR="${FASTEMBED_CACHE_DIR:-$here/cache}"
if [ ! -x "$venv_cpu/bin/python" ]; then
	echo "No CPU venv at $venv_cpu: see README.md, Setup." >&2
	exit 2
fi
out="${RESULTS:-$here/results}/$(hostname -s)-$(date +%Y%m%d-%H%M%S)-$mode-$parts"
mkdir -p "$out"
exec > >(tee -a "$out/run.log") 2>&1
echo "Results in $out"

for set in short:0 mixed:0.12 long:1; do
	"$venv_cpu/bin/python" "$here/gen_texts.py" "$out/texts-${set%%:*}.jsonl" --n "$texts" --long-share "${set#*:}"
done
"$venv_cpu/bin/python" "$here/prepare_model.py"

if [ "$parts" != gpu ]; then
	"$venv_cpu/bin/python" "$here/bench.py" cpu "$mode" "$out" cpu
fi
gpu_status=0
if [ "$parts" != cpu ]; then
	if [ -x "$venv_gpu/bin/python" ]; then
		"$venv_gpu/bin/python" "$here/bench.py" gpu "$mode" "$out" gpu "${force[@]}" || gpu_status=$?
	else
		echo "GPU part not run: no GPU venv at $venv_gpu (README.md, Setup)." >&2
		gpu_status=3
	fi
fi
"$venv_cpu/bin/python" "$here/bench.py" report "$out"
exit "$gpu_status"
