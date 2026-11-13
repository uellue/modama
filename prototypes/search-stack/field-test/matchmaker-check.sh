#!/bin/bash
# Why the search page says "Something went wrong while searching": the state of matchmaker
# and the search API, their last log lines, and one search sent three ways (through
# matchmaker's proxy, as the page does; straight to the search API from matchmaker; and
# from inside the search API). Read-only: prints no environment beyond SEARCH_API_URL.
#
#   bash matchmaker-check.sh [compose project, default search-staging] > matchmaker-check.txt 2>&1
set -uo pipefail
p="${1:-search-staging}"
q='q=ferritin&resource=datasets'
fetch='const u=process.argv[1]; fetch(u).then(async r=>{console.log(u, "->", r.status); console.log((await r.text()).slice(0,600))}).catch(e=>console.log(u, "-> ERROR", e.message, e.cause?.code ?? ""))'

echo "== containers"
docker ps -a --filter "name=$p-matchmaker" --filter "name=$p-search-api" \
  --format '{{.Names}}  {{.Image}}  {{.Status}}'
echo "== matchmaker's SEARCH_API_URL"
docker exec "$p-matchmaker-1" printenv SEARCH_API_URL
echo "== search through matchmaker's proxy (what the page calls)"
docker exec "$p-matchmaker-1" node -e "$fetch" "http://127.0.0.1:3000/api/search/search?$q"
echo "== search straight to the search API, from matchmaker"
docker exec "$p-matchmaker-1" node -e "$fetch" "http://search-api:8000/search?$q"
echo "== search API's health, from matchmaker"
docker exec "$p-matchmaker-1" node -e "$fetch" "http://search-api:8000/health"
echo "== matchmaker log, last 20 minutes"
docker logs --since 20m "$p-matchmaker-1" 2>&1 | tail -n 80
echo "== search API log, last 20 minutes"
docker logs --since 20m "$p-search-api-1" 2>&1 | tail -n 80
