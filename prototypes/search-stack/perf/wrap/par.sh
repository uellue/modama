#!/bin/bash
# par.sh P T FILL [SUB_BATCH]: P batch processes of 250 at once, each with T threads; one line per process, then the wall time.
here=$(cd "$(dirname "$0")" && pwd)
p=$1 t=$2 fill=$3 sb=${4:-0}
start=$(date +%s.%N)
for i in $(seq "$p"); do
  TAG=par$p-$i "$here/run.sh" plain 250 "$fill" "$t" "$sb" 2>&1 | grep -E 'transformed|Error|Traceback' | sed "s/^/[$i] /" &
done
wait
echo "P $p T $t FILL $fill: all done in $(python3 -c "print(round($(date +%s.%N) - $start, 1))") s"
