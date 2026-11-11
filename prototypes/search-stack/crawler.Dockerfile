# The crawler with the EM formats and the chain tool. Build context: python/crawler;
# python/modama-formats-em comes in as the context "em", python/search-chain as "chain".
FROM python:3.14-slim-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
COPY . /src
# editable, so that the fixture files outside the package data stay available to the e2e test
RUN pip install --no-cache-dir -e "/src[test]"
COPY --from=em . /em
RUN pip install --no-cache-dir -e /em
COPY --from=chain . /chain
RUN pip install --no-cache-dir -e /chain
