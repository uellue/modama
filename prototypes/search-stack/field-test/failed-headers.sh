#!/bin/bash
# What the files of failed extractions start with: for each file listed under "extraction failed"
# in a `modama-chain review` file, its format, size, first 16 bytes in hex, and whether the file
# is all zero bytes (read in full only up to 64 MiB; larger: "big"). Read-only.
#
#   bash field-test/failed-headers.sh REVIEW.md DATA_ROOT [FORMAT...] > failed-headers.txt
#
# REVIEW.md as `modama-chain review` writes it; DATA_ROOT the tree the crawler sees as / (staging:
# STAGING_DATA in staging.env); FORMATs to keep (e.g. common/jpeg common/tiff), all if none.
set -uo pipefail
review="${1:?REVIEW.md}"; root="${2:?DATA_ROOT}"; shift 2
want=" $* "
section=""; fmt=""
while IFS= read -r line; do
    case "$line" in
        "## "*) section="${line#\#\# }" ;;
        "### "*) fmt="${line#\#\#\# }"; fmt="${fmt%% *}" ;;
        "- [\`"*)
            [ "$section" = "extraction failed" ] || continue
            [ "$want" = "  " ] || [[ "$want" == *" $fmt "* ]] || continue
            path="${line#- [\`}"; path="${path%%\`]*}"
            f="$root$path"
            if [ ! -f "$f" ]; then echo "$fmt  missing  $path"; continue; fi
            size=$(stat -c %s "$f")
            head16=$(head -c 16 "$f" | od -An -tx1 | tr -s ' ' | sed 's/^ //')
            if [ "$size" -gt 67108864 ]; then zero=big
            elif [ "$size" -eq 0 ]; then zero=empty
            elif cmp -s -n "$size" "$f" /dev/zero; then zero=allzero
            else zero=data; fi
            echo "$fmt  $size  $zero  $head16  $path"
            ;;
    esac
done < "$review"
