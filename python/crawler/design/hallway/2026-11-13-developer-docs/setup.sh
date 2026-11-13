#!/bin/bash
# Make the tester's clone for the hallway test of the developer docs (2026-11-13):
# a clone of the branch crawler with the seed applied, this folder and its record
# removed (the answer key must not be visible), and no history (one orphan commit).
# Also an empty scratch directory with the tester's brief filled in.
#
# Usage: setup.sh REPO [TARGET] [SCRATCH]
#   REPO     the repository to clone (a path or URL), for example /workspaces/data-management-system
#   TARGET   the clone; default /var/tmp/hallway/clone; must not exist
#   SCRATCH  the tester's scratch directory; default /var/tmp/hallway/scratch; must not exist
#   REF      (environment) a commit to check out instead of crawler's head, for a seed
#            that no longer applies there; the seed was made at 0fced7aa
set -euo pipefail

repo=${1:?usage: setup.sh REPO [TARGET] [SCRATCH]}
target=${2:-/var/tmp/hallway/clone}
scratch=${3:-/var/tmp/hallway/scratch}
here=$(cd "$(dirname "$0")" && pwd)
folder=python/crawler/design/hallway/2026-11-13-developer-docs

for d in "${target:?}" "${scratch:?}"; do
    if [ -e "$d" ]; then
        echo "setup.sh: $d exists; remove it or name another" >&2
        exit 1
    fi
done

git clone -q --branch crawler --no-local "$repo" "${target:?}"
echo "cloned $repo, branch crawler, into $target"
if [ -n "${REF:-}" ]; then
    git -C "$target" checkout -q --detach "$REF"
    echo "checked out $REF"
fi
echo "at $(git -C "$target" log -1 --format='%h %s')"

git -C "$target" apply "$here/seed.patch"
echo "applied the seed: $here/seed.patch"

# This folder and the test's records (2026-11-13-developer-docs.md, -2.md, ...)
rm -rf -- "${target:?}/${folder:?}"
rm -f -- "${target:?}/${folder:?}"*.md
echo "removed $folder and its records from the clone"

git -C "$target" checkout -q --orphan hallway
git -C "$target" add -A
git -C "$target" -c user.name="hallway setup" -c user.email=hallway@invalid \
    -c commit.gpgsign=false commit -q -m snapshot
git -C "$target" for-each-ref --format='%(refname:short)' refs/heads/ |
    while read -r branch; do
        if [ "$branch" != hallway ]; then
            git -C "$target" branch -q -D "$branch"
        fi
    done
git -C "$target" for-each-ref --format='%(refname:short)' refs/tags/ |
    while read -r tag; do git -C "$target" tag -d "$tag" > /dev/null; done
git -C "$target" remote remove origin
git -C "$target" reflog expire --expire=now --all
git -C "$target" gc -q --prune=now
echo "history removed: $(git -C "$target" rev-list --all | wc -l) commit, branch $(git -C "$target" branch --show-current), remotes: $(git -C "$target" remote | wc -l)"

# Anything left that names this test points the tester at the answers
mentions=$(git -C "$target" grep -l -e 2026-11-13-developer-docs -e "hallway test of the developer docs" || true)
if [ -n "$mentions" ]; then
    echo "WARNING: files in the clone mention this test; read them before the run:" >&2
    echo "$mentions" | sed "s|^|  $target/|" >&2
fi

mkdir -p "${scratch:?}"
# The prompt is what follows the first line "---"
sed -e '1,/^---$/d' -e "s|{{CLONE}}|$target|g" -e "s|{{SCRATCH}}|$scratch|g" \
    "$here/brief.md" > "$scratch/brief.md"
echo "made $scratch, with the brief filled in: $scratch/brief.md"
echo "clone: $target"
echo "scratch: $scratch"
