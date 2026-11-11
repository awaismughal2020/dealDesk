# syntax=docker/dockerfile:1.7
# Deal Desk web (Next.js). Stages: deps -> dev (tooling) / builder -> runtime (standalone, non-root) / e2e.
ARG NODE_IMAGE=node:26.13.0-trixie-slim
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.65.0-noble

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund \
 && chmod -R a+rX /app/node_modules

# Tooling image for lint/typecheck/unit tests; the source is bind-mounted over /app.
FROM deps AS dev
RUN mkdir -p /app/node_modules/.vitest-cache && chmod 1777 /app/node_modules/.vitest-cache
CMD ["npm", "run", "test"]

FROM deps AS builder
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
RUN groupadd --system --gid 10001 web \
 && useradd --system --uid 10001 --gid web --no-create-home --shell /usr/sbin/nologin web
COPY --from=builder --chown=10001:10001 /app/.next/standalone ./
COPY --from=builder --chown=10001:10001 /app/.next/static ./.next/static
COPY --from=builder --chown=10001:10001 /app/public ./public
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]

# Playwright runner, built FROM the official image so browsers and system deps match the pinned version.
FROM ${PLAYWRIGHT_IMAGE} AS e2e
WORKDIR /work
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts
CMD ["npx", "playwright", "test"]
