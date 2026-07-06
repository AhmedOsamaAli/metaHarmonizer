# MetaHarmonizer frontend — build the React/Vite SPA to static assets.
#
# Two stages:
#   1. `build`  — install deps + `npm run build` → /app/dist
#   2. `dist`   — a tiny image that publishes the built assets into the shared
#                 `web_dist` volume on start, then exits. Caddy serves them.
#
# The SPA talks to the API via the same origin (relative `/api/v1`, see
# src/api/http.ts), so no build-time API URL is needed — Caddy fronts both.

FROM node:20-alpine AS build
WORKDIR /app

# Install deps first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm install

# Build the static bundle.
COPY . .
RUN npm run build

# Publisher stage: holds the built assets and copies them into the mounted
# web volume, then exits (a one-shot service in compose).
FROM alpine:3.20 AS dist
WORKDIR /dist
COPY --from=build /app/dist ./
CMD ["sh", "-c", "rm -rf /srv/* && cp -a /dist/. /srv/ && echo 'web assets published to /srv'"]
