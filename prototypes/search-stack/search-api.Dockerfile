# The EOSC search API (data-commons-search), upstream's image with our patches on top
# (patches/search-api/, applied in order; a patch that does not apply fails the build).
# Build context: patches/search-api. Drop a patch once upstream has it; with none left,
# use upstream's image directly again.
FROM ghcr.io/eosc-data-commons/data-commons-search:0.10.2@sha256:fd3f17eea7261606768101f3fc7e5885f969c61f908b902c07995fadd54d91ee AS upstream

# upstream's image has neither patch nor git
FROM busybox:1.37.0 AS patched
WORKDIR /app
COPY --from=upstream /app/src src
COPY *.patch /patches/
RUN for p in /patches/*.patch; do echo "applying $p" && patch -p1 -i "$p" || exit 1; done

FROM upstream
COPY --from=patched /app/src /app/src
