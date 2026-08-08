# MetaHarmonizer frontend — build the React/Vite SPA to static assets.
#
# Two stages:
#   1. `build`  — install deps + `npm run build` → /app/dist
#   2. `dist`   — a tiny image that publishes the built assets into the shared
#                 `web_dist` volume on start, then exits. Caddy serves them.
#
# The SPA talks to the API via the same origin (relative `/api/v1`, see
# src/api/http.ts), so no build-time API URL is needed — Caddy fronts both.

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build
WORKDIR /app

# Install deps first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm ci

# Build the static bundle.
COPY . .
RUN npm run build

# Publisher stage: holds the built assets and copies them into the mounted
# web volume, then exits (a one-shot service in compose).
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS dist
WORKDIR /dist
COPY --from=build /app/dist ./
RUN addgroup -g 1000 app \
	&& adduser -D -u 1000 -G app app \
	&& chown -R app:app /dist
USER app:app
CMD ["sh", "-c", "rm -rf /srv/* && cp -R /dist/. /srv/ && echo 'web assets published to /srv'"]
