# The crawler for the e2e test: serves the OAI-PMH endpoint and runs the test. Build context: python/crawler.
FROM python:3.14-slim-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends shared-mime-info git \
    && rm -rf /var/lib/apt/lists/*
COPY . /src
# editable, so that fixture files outside the package data (formats/core/tests/fixtures) stay available
RUN pip install --no-cache-dir -e "/src[test]"
