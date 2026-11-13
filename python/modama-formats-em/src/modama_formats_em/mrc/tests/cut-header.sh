#!/bin/bash
# The header of one MRC file for a test fixture (decision 293, 2026-11-13: public files, cut):
# the 1024-byte main header, and for an FEI extended header (exttyp FEI1 or FEI2) its first
# record, of the size the record states (768 or 888 bytes), what the format reads; no image data,
# no further records, no padding. Little-endian files only (machine stamp 0x44), as all seen.
# Reads the file, writes only into the target folder, which must not exist yet.
# The fixtures epu_falcon, epu_movie, fei1, particle_stack and emdb_tomogram (fixtures.toml)
# were cut with it.
#
#   bash cut-header.sh <file.mrc> <target folder>
#   e.g. bash cut-header.sh FoilHole_4551046_Data_4541935_4541937_20220507_103020.mrc ~/fixtures/epu_falcon
set -euo pipefail
src="${1:?file.mrc}"
dst="${2:?target folder}"
[ "$(head -c 211 "$src" | tail -c 3)" = "MAP" ] || { echo "$src: no MAP at byte 208" >&2; exit 1; }
[ "$(od -An -tx1 -j 212 -N 1 "$src" | tr -d ' ')" = "44" ] || { echo "$src: not little-endian" >&2; exit 1; }
nsymbt=$(od -An -td4 -j 92 -N 4 "$src" | tr -d ' ')
exttyp=$(head -c 108 "$src" | tail -c 4 | tr -d '\0')
size=1024
if [ "$exttyp" = "FEI1" ] || [ "$exttyp" = "FEI2" ]; then
    record=$(od -An -td4 -j 1024 -N 4 "$src" | tr -d ' ')
    [ "$record" -le "$nsymbt" ] || { echo "$src: record of $record bytes in $nsymbt" >&2; exit 1; }
    size=$((1024 + record))
fi
mkdir "$dst"
head -c "$size" "$src" > "$dst/${src##*/}"
ls -l "$dst"
sha256sum "$src" "$dst"/*
