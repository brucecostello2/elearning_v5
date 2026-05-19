# IVGS v5 — Next.js 14 Frontend (ivgs-frontend)
# Node 20 alpine, multi-stage build
FROM node:20-alpine AS builder

WORKDIR /app

COPY ivgs-frontend/package.json ivgs-frontend/package-lock.json ./
RUN npm ci --frozen-lockfile

COPY ivgs-frontend/ ./
RUN npm run build

# --- Runtime stage ---
FROM node:20-alpine

RUN addgroup -S ivgs && adduser -S ivgs -G ivgs

WORKDIR /app

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN chown -R ivgs:ivgs /app

USER ivgs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
