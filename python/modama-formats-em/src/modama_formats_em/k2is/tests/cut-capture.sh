#!/bin/bash
# Metadata of one K2IS capture for a test fixture (decision 73, 2026-11-12: metadata yes, data no):
# the .gtg tag file as it is, and of each .bin sector file only its first block's 40-byte header
# (sync word, block counter, width, height: LiberTEM's DataBlock header), no pixel data.
# Reads the capture, writes only into the target folder, which must not exist yet.
# The fixture capture52 (fixtures.toml) was cut with it.
#
#   bash cut-capture.sh <capture folder> <target folder>
#   e.g. bash cut-capture.sh /storage/er-c-data/adhoc/libertem/libertem-test-data/Capture52 ~/field-test/k2is-capture52
set -euo pipefail
src="${1:?capture folder}"
dst="${2:?target folder}"
gtg=("$src"/*.gtg)
[ "${#gtg[@]}" -eq 1 ] && [ -f "${gtg[0]}" ] || { echo "expected one .gtg in $src" >&2; exit 1; }
size=$(stat -c %s "${gtg[0]}")
# a tag file is small; a large one may hold image data: stop rather than copy it
[ "$size" -le 1048576 ] || { echo "${gtg[0]} is $size bytes: not copied, check what it holds" >&2; exit 1; }
mkdir "$dst"
cp "${gtg[0]}" "$dst/"
for f in "$src"/*.bin; do
    head -c 40 "$f" > "$dst/${f##*/}"
done
ls -l "$dst"
sha256sum "$dst"/*
