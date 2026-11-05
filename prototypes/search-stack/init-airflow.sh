#!/bin/bash
# Run by the airflow-accounts service, once the dag-processor has written the DAGs to
# the database: FAB's per-DAG permissions exist only from then on.
#   the role harvest-trigger: start and read runs of warehouse_harvest_and_index, nothing
#   else (FAB needs edit on a DAG to start its runs, so it could pause that one DAG);
#   the accounts crawler (harvest-trigger) and chain (Viewer), if missing. Existing
#   accounts keep their password: to change one, delete the account and restart.
set -euo pipefail
DAG=warehouse_harvest_and_index

for _ in $(seq 60); do
    airflow roles create harvest-trigger > /dev/null
    if airflow roles add-perms harvest-trigger -r "DAG:$DAG" -a can_read can_edit > /dev/null; then
        break
    fi
    echo "waiting for the DAG $DAG"
    sleep 5
done
airflow roles add-perms harvest-trigger -r "DAG:$DAG" -a can_read can_edit > /dev/null
airflow roles add-perms harvest-trigger -r "DAG Run:$DAG" -a can_create can_read > /dev/null

users=$(airflow users list -o plain)
create() {  # name, role, name of the variable with the password
    local name=$1 role=$2 password=${!3}
    if ! grep -qw "$name" <<< "$users"; then
        # the password is on a command line once, inside this container
        airflow users create -u "$name" -r "$role" -p "$password" -f "$name" -l modama -e "$name@localhost" > /dev/null
        echo "Airflow account $name ($role) created"
    fi
}
create crawler harvest-trigger MODAMA_CRAWLER_AIRFLOW_PASSWORD
create chain Viewer MODAMA_CHAIN_AIRFLOW_PASSWORD
echo "Airflow accounts ready"
