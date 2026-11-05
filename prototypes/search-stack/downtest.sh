#!/bin/bash
# Stop the test deployment of the search stack. The state stays.
#
#   downtest.sh           stop the containers
#   downtest.sh --reset   also delete all state: crawler and warehouse databases, index,
#                         Airflow, test data. The next ./uptest.sh starts fresh.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
    "") docker compose down ;;
    --reset) docker compose down --volumes ;;
    *) echo "usage: $0 [--reset]" >&2; exit 2 ;;
esac
