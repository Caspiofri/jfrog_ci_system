# syntax=docker/dockerfile:1
# The Jessi web UI (Next.js, frontend/) for docker compose. Built from the frontend directory as the context, so
# nothing outside frontend/ is sent but config/ (the `config` build context in docker-compose.yml, for the capability
# sheet the /capabilities page renders); this file lives outside frontend/ on purpose.
#   CI_API_URL: where the Next server forwards /api/v1/* (the compose api service); read at build time
FROM node:22-slim AS build
WORKDIR /ui
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
# /capabilities renders the committed capability sheet at build time, read from ../config (frontend/'s sibling)
COPY --from=config jfrog_capabilities.md /config/jfrog_capabilities.md
ARG CI_API_URL=http://api:8011
ARG CI_MODE=demo
ENV CI_API_URL=${CI_API_URL} CI_MODE=${CI_MODE} NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /ui
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /ui /ui
COPY --from=build /config /config
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
