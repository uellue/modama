#!/bin/bash
# Prepares the tester's folder for a re-run of this hallway test: DESIGN.md, the two logos,
# and the screenshots of the last `./runtest.sh brand baseline` and `./runtest.sh brand`
# (prototypes/search-stack/brandcheck/out/). Then give a fresh agent brief.md, with its
# folder path replaced by DIR, and nothing else.
#   prepare.sh DIR
set -euo pipefail
dir=${1:?usage: prepare.sh DIR}
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
out=$repo/prototypes/search-stack/brandcheck/out
mkdir -p "$dir/before" "$dir/after" "$dir/work"
cp "$out"/baseline/*.png "$dir/before/"
cp "$out"/current/*.png "$dir/after/"
cp "$repo/mgmtinterface-new/DESIGN.md" "$repo/branding/modama.svg" "$dir/"
cp "$repo/deploy/landingpage/fzj_logo.jpg" "$dir/fzj-logo.png"
sed "s#/tmp/[^ ]*/scratchpad/hallway/#$dir/#" "$(dirname "$0")/brief.md" > "$dir/brief.md"
echo "brief: $dir/brief.md"
