# The Airflow image of the warehouse with our patches on top (patches/warehouse/, applied in
# order; a patch that does not apply fails the build) and the CPU budget's start script
# (cpu-budget/budget.py, README "CPU budget"). Build context: patches/warehouse; named context
# `budget`: cpu-budget/. The base is upstream's Dockerfile built unchanged, as the image of the
# build-only service airflow-upstream (docker-compose.yml), which ./uptest.sh and ./upstaging.sh
# build first. Drop a patch once upstream has it.
FROM search-stack-airflow-upstream:3.3.2 AS upstream

# upstream's image has no patch
FROM busybox:1.37.0 AS patched
WORKDIR /w
COPY --from=upstream /opt/airflow/dags airflow/dags
COPY --from=upstream /opt/airflow/project/src src
COPY *.patch /patches/
RUN for p in /patches/*.patch; do echo "applying $p" && patch -p1 -i "$p" || exit 1; done

FROM upstream
COPY --from=patched --chown=airflow:root /w/airflow/dags /opt/airflow/dags
COPY --from=patched --chown=airflow:root /w/src /opt/airflow/project/src
COPY --from=budget budget.py /opt/modama/budget.py
