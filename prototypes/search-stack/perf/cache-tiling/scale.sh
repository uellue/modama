#!/bin/bash
# Throughput at 1, 2, 4 and 8 processes (throughput.py) under perf stat, with the cache counters per record.
#
#   [REF=ref.npy] [TOKENS=N] prototypes/search-stack/perf/cache-tiling/scale.sh METHOD TEXTS SUB_BATCH [NS...]
#
# from the repository root; REF and TOKENS are passed on as throughput.py's --ref and --tokens.
# Needs sudo for perf (perf_event_paranoid is 3 in the VM). Counts every process of the run, the model
# loading and the warm-up pass included (divided by twice the records; loading is about 1 % of a pass). Prints throughput.py's line and, per record: instructions, L2 demand misses of data
# (l2_cache_req_stat.ls_rd_blk_c), L2-prefetcher misses served by L3 and by memory, and the lines the L1
# filled from memory (demand plus L1 prefetcher); "DRAM MB/record" sums the three fills from memory × 64 B.
# The VM exposes 4 core counters (perf multiplexes the 7 events) and no L3 or memory-controller PMU.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
V=${V:-/var/tmp/embed-research-trials/venv/bin/python}
method=$1 texts=$2 sb=$3
shift 3
ns=${*:-1 2 4 8}
n_texts=$(wc -l <"/var/tmp/embed-research-trials/texts/$texts")
ev=instructions,l2_cache_req_stat.ls_rd_blk_c,l2_pf_miss_l2_hit_l3,l2_pf_miss_l2_l3
ev=$ev,ls_refills_from_sys.ls_mabresp_lcl_dram,ls_hw_pf_dc_fill.ls_mabresp_lcl_dram,ls_refills_from_sys.ls_mabresp_lcl_cache
out=$(mktemp -p /var/tmp/embed-research-trials/tmp perfstat.XXXXXX)
for n in $ns; do
    cpus=$(seq -s, 0 $((n - 1)))
    sudo perf stat -x, -o "$out" -e "$ev" -- sudo -u "$USER" TMPDIR="${TMPDIR:-/var/tmp/embed-research-trials/tmp}" \
        "$V" "$here/throughput.py" "$method" "$n" "$texts" --sub-batch "$sb" --cpus "$cpus" ${REF:+--ref "$REF"} ${TOKENS:+--tokens "$TOKENS"}
    # the counters include throughput.py's warm-up, one more pass over the texts: twice the records
    awk -F, -v r=$((2 * n * n_texts)) '
        /^[0-9]/ { v[$3] = $1 }
        END {
            dram = v["ls_refills_from_sys.ls_mabresp_lcl_dram"] + v["ls_hw_pf_dc_fill.ls_mabresp_lcl_dram"] + v["l2_pf_miss_l2_l3"]
            printf "  per record: %.1f G instructions, L2 demand misses %.1f M, L2-pf hit L3 %.1f M, L2-pf from memory %.1f M,",
                v["instructions"] / r / 1e9, v["l2_cache_req_stat.ls_rd_blk_c"] / r / 1e6, v["l2_pf_miss_l2_hit_l3"] / r / 1e6,
                v["l2_pf_miss_l2_l3"] / r / 1e6
            printf " L1 fills from memory %.1f M (demand) %.1f M (prefetch), from L3/other caches %.1f M; DRAM %.0f MB/record\n",
                v["ls_refills_from_sys.ls_mabresp_lcl_dram"] / r / 1e6, v["ls_hw_pf_dc_fill.ls_mabresp_lcl_dram"] / r / 1e6,
                v["ls_refills_from_sys.ls_mabresp_lcl_cache"] / r / 1e6, dram * 64 / r / 1e6
        }' "$out"
done
rm -f -- "$out"
