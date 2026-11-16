#!/bin/bash
# Nine scout sessions in parallel: arms a, b, c, three runs each, each in its own empty folder.
set -u
base=/var/tmp/analogy-scout-2
cases=$(cat "$base/cases.md")
method=$(cat "$base/method-b.md")
library=$(cat "$base/library.md")
for arm in a b c; do
  for i in 1 2 3; do
    mkdir -p "$base/run-$arm$i"
  done
done
date -u +%FT%TZ > "$base/times.txt"
for arm in a b c; do
  case "$arm" in
    a) prompt="$cases" ;;
    b) prompt="$method"$'\n\n'"$cases" ;;
    c) prompt="$method"$'\n\n'"$library"$'\n\n'"$cases" ;;
  esac
  for i in 1 2 3; do
    (cd "$base/run-$arm$i" && claude -p "$prompt" --tools "" --output-format json > out.json 2> err.txt) &
  done
done
wait
date -u +%FT%TZ >> "$base/times.txt"
