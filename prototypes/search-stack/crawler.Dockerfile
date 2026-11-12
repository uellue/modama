# The crawler with the EM and common formats and the chain tool. Build context: python/crawler;
# python/modama-formats-em comes in as the context "em", python/modama-formats-common as
# "common", python/search-chain as "chain".
# libnss-sss: owners' names and groups from the service sssd (adds sss to nsswitch.conf)
FROM python:3.14-slim-trixie AS crawler
RUN apt-get update \
    && apt-get install -y --no-install-recommends shared-mime-info libnss-sss \
    && rm -rf /var/lib/apt/lists/*
COPY . /src
# editable, so that the fixture files outside the package data stay available to the e2e test
RUN pip install --no-cache-dir -e "/src[test]"
COPY --from=em . /em
RUN pip install --no-cache-dir -e /em
COPY --from=common . /common
RUN pip install --no-cache-dir -e /common
COPY --from=chain . /chain
# with modama-chain's extra `browse` (the warehouse's xmltodict and jsonschema pins) in the
# crawler too: the extractor identity is a digest of the whole installation, so the browser's
# live extraction matches the crawl's only if both have the same packages (jsonschema also
# comes with nbformat, for the notebooks)
RUN pip install --no-cache-dir -e "/chain[browse]"

# The service browse (target browse; change chain-browse): the same image. Its sources are
# mounted from the checkout at run time, so this image changes only with the dependencies.
FROM crawler AS browse

# The crawler's image: the last stage, the default target
FROM crawler
