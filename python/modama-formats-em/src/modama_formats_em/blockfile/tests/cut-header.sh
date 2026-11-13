#!/bin/bash
# The header of one NanoMegas block file (.blo) for a test fixture (decision 232, 2026-11-12:
# header yes, data no): the first 4,096 bytes, up to where RosettaSciIO and LiberTEM expect the
# virtual bright-field image (Data_offset_1 = 0x1000), no diffraction patterns.
# Reads the file, writes only into the target folder, which must not exist yet.
# The fixture stingray (fixtures.toml) was cut with it.
#
#   bash cut-header.sh <file.blo> <target folder>
#   e.g. bash cut-header.sh /path/to/Stingray16bit_7_11.blo ~/field-test/blo-stingray
set -euo pipefail
src="${1:?file.blo}"
dst="${2:?target folder}"
[ "$(head -c 6 "$src")" = "IMGBLO" ] || { echo "$src does not start with IMGBLO" >&2; exit 1; }
mkdir "$dst"
head -c 4096 "$src" > "$dst/${src##*/}"
ls -l "$dst"
sha256sum "$dst"/*
