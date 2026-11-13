#!/bin/bash
# EPU's sidecars of one image for a test fixture (change em-mrc-sidecars): <stem>.xml and
# <stem>_Fractions.xml whole (EPU's metadata, kilobytes), <stem>.jpg cut to its first 2048
# bytes (the preview; the format groups it by name and reads nothing of it). Copies those of
# them that exist into the target folder, which must exist (cut-header.sh makes it for the
# MRC files). The fixture epu_data (fixtures.toml) was cut with it.
#
#   bash cut-sidecars.sh <folder>/<stem> <target folder>
#   e.g. bash cut-sidecars.sh Data/FoilHole_4551075_Data_4541935_4541937_20220507_110208 ~/fixtures/epu_data
set -euo pipefail
stem="${1:?folder/stem}"
dst="${2:?target folder}"
[ -d "$dst" ] || { echo "$dst is not a folder" >&2; exit 1; }
name="${stem##*/}"
for xml in "$stem.xml" "${stem}_Fractions.xml"; do
    if [ -f "$xml" ]; then cp "$xml" "$dst/"; fi
done
if [ -f "$stem.jpg" ]; then head -c 2048 "$stem.jpg" > "$dst/$name.jpg"; fi
ls -l "$dst"
sha256sum "$dst"/*
