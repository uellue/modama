# The EOSC search web frontend (matchmaker), built from upstream's source at v0.14.0 with
# our patches on top (patches/matchmaker/, applied in order; a patch that does not apply
# fails the build). The stages follow upstream's Dockerfile, target production; unlike
# it, npm also reads upstream's .npmrc (min-release-age). Build context: patches/matchmaker.
# Drop a patch once upstream has it; with none left, use upstream's image directly again.
FROM busybox:1.37.0 AS source
# a commit, not the tag: the content cannot move
ADD https://github.com/EOSC-Data-Commons/matchmaker.git#e7138c898926ebb79e45dd7d20cbf838dcf5dbe5 /src
COPY *.patch /patches/
RUN cd /src && for p in /patches/*.patch; do echo "applying $p" && patch -p1 -i "$p" || exit 1; done

FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS base
WORKDIR /app
COPY --from=source /src/package.json /src/package-lock.json /src/.npmrc ./
RUN npm ci

FROM base AS build
COPY --from=source /src ./
RUN npm run build

FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS production
WORKDIR /app
COPY --from=source /src/package.json /src/package-lock.json /src/.npmrc ./
RUN npm ci --omit=dev
COPY --from=build /app/build ./build
EXPOSE 3000
ENV NODE_ENV=production
ENV PORT=3000
CMD ["npm", "run", "prod"]
