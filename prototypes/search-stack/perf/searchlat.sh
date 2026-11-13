#!/bin/bash
# 100 searches against the test deployment's search API, one at a time; prints median, p90, max in ms
set -euo pipefail
for i in $(seq 100); do
    curl -s -o /dev/null -w '%{time_total}\n' "http://127.0.0.1:8000/search?q=ferritin+sample+$i&resource=datasets"
done | sort -n | awk '{t[NR]=$1*1000} END {printf "n %d  median %.0f ms  p90 %.0f ms  max %.0f ms\n", NR, t[int(NR/2)], t[int(NR*0.9)], t[NR]}'
