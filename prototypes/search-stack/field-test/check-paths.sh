#!/bin/bash
# Whether each path in PATHS (one per line, for example the paths a chat answer linked)
# is a dataset the crawler knows: "known" when a record has that path as its title.
# Read-only.
#
#   bash check-paths.sh PATHS [compose project, default search-staging] > check-paths.txt 2>&1
set -uo pipefail
paths="${1:?usage: check-paths.sh PATHS [compose project]}"
p="${2:-search-staging}"
while IFS= read -r path; do
    # the query on psql's stdin, so that :'path' is quoted by psql (it doesn't substitute in -c)
    n=$(echo "select count(*) from records where metadata->'title'->>0 = :'path';" |
        docker exec -i "$p-crawler-db-1" psql -U postgres -d modama_crawler -At -v path="$path" 2>&1)
    [ "$n" = "1" ] && echo "known    $path" || echo "unknown  $path  ($n)"
done < "$paths"
