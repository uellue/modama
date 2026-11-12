#!/bin/bash
# Bring up the test deployment of the search stack and wait until every service is
# healthy and the init services have finished. Extra arguments go to `docker compose up`,
# for example --build after pulling changes. Idempotent; the first start builds the
# images and downloads the embedding model, which takes a while.
set -euo pipefail
cd "$(dirname "$0")"
# Like deploy/.env: the secrets directory; the test deployment's throwaway values unless set
[ -e .env ] || echo "MODAMA_SECRETS_DIR=./testconf/secrets" > .env
# the base of our Airflow image, which Compose cannot build in order (docker-compose.yml)
docker compose build --quiet airflow-upstream
docker compose up -d --wait --wait-timeout "${UPTEST_TIMEOUT:-900}" "$@"
echo "search stack is up; run ./runtest.sh to check it"
