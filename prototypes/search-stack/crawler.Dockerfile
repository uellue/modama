# The crawler with the chain tool. Build context: python/crawler; python/search-chain
# comes in as the context "chain".
FROM python:3.14-slim-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
COPY . /src
# editable, so that the fixture files outside the package data stay available to the e2e test
RUN pip install --no-cache-dir -e "/src[test]"
COPY --from=chain . /chain
RUN pip install --no-cache-dir -e /chain
