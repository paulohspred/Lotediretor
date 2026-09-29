# Builds one Next.js app (client-web, admin-web or site-web).
#   docker build -f deploy/production/docker/node-app.Dockerfile \
#     --build-arg APP_DIR=apps/client-web .
FROM node:22-bookworm-slim AS build
ARG APP_DIR
WORKDIR /app
COPY ${APP_DIR}/package.json ${APP_DIR}/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ${APP_DIR}/ ./
# Public URLs are inlined at build time for the static site pages.
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_COMPANY_NAME
ARG NEXT_PUBLIC_COMPANY_CNPJ
ARG NEXT_PUBLIC_COMPANY_ADDRESS
ARG NEXT_PUBLIC_DPO_EMAIL
ARG NEXT_PUBLIC_LEGAL_REVIEWED
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
USER node
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
