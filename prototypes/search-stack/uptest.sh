#!/bin/bash
# Bring up the test deployment of the search stack and wait until every service is
# healthy and the init services have finished. Extra arguments go to `docker compose up`,
# for example --build after pulling changes. Idempotent; the first start builds the
# images and downloads the embedding model, which takes a while.
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d --wait --wait-timeout "${UPTEST_TIMEOUT:-900}" "$@"
echo "search stack is up; run ./runtest.sh to check it"
