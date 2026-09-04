# syntax=docker/dockerfile:1
#
# Sprint 034 (Phase 2) — the public GeoCore site (geocore.one).
# Mirrors apps/web/Dockerfile; built with the repository root as its context.

FROM node:20-alpine AS base

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH"

RUN corepack enable

WORKDIR /app

FROM base AS builder

COPY . ./
RUN pnpm install --frozen-lockfile

ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_APP_URL
ENV APP_ENV=production \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL

RUN pnpm --filter marketing build

FROM node:20-alpine AS runner

ENV NODE_ENV=production \
    PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 --ingroup nodejs nextjs

WORKDIR /app

COPY --from=builder --chown=nextjs:nodejs /app/apps/marketing/public ./apps/marketing/public
COPY --from=builder --chown=nextjs:nodejs /app/apps/marketing/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/marketing/.next/static ./apps/marketing/.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "apps/marketing/server.js"]
