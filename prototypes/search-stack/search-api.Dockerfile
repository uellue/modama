# The EOSC search API (data-commons-search), upstream's image with our patches on top
# (patches/search-api/, applied in order; a patch that does not apply fails the build) and
# the CPU budget's start script (cpu-budget/budget.py, README "CPU budget").
# Build context: patches/search-api; named context `budget`: cpu-budget/. Drop a patch once
# upstream has it; with none left and no start script, use upstream's image directly again.
FROM ghcr.io/eosc-data-commons/data-commons-search:0.10.2@sha256:fd3f17eea7261606768101f3fc7e5885f969c61f908b902c07995fadd54d91ee AS upstream

# upstream's image has neither patch nor git
FROM busybox:1.37.0 AS patched
WORKDIR /app
COPY --from=upstream /app/src src
COPY *.patch /patches/
RUN for p in /patches/*.patch; do echo "applying $p" && patch -p1 -i "$p" || exit 1; done

FROM upstream
COPY --from=patched /app/src /app/src
COPY --from=budget budget.py /opt/modama/budget.py
# Upstream's WORKERS=6 cleared: the workers follow the CPUs, and only an operator's WORKERS
# overrides them. budget.py adds --workers and the threads (EMBEDDING_THREADS, patch 0002).
ENV WORKERS=
ENTRYPOINT ["sh", "-c", "exec python /opt/modama/budget.py search-api -- uvicorn src.data_commons_search.main:app --host \"$SERVER_HOST\" --port \"$SERVER_PORT\""]
