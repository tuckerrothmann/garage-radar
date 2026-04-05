ARG NODE_IMAGE=node:20-alpine

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install

# ── Builder ───────────────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN mkdir -p /app/public

ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED 1
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

# ── Runner ────────────────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS runner
WORKDIR /app

ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]
