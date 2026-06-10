FROM node:22-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-yaml && rm -rf /var/lib/apt/lists/*

# Repo-Struktur spiegeln: ROOT in generate_taxonomy.py = /repo
# Skript erwartet /repo/frontend/, /repo/scripts/, /repo/config/
WORKDIR /repo/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
# docs/user/ muss beim Vite-Build erreichbar sein (Alias $docs → /docs/user)
COPY docs/user/ /docs/user/
COPY scripts/ /repo/scripts/
COPY config/taxonomy.yaml /repo/config/taxonomy.yaml

ARG PUBLIC_SCHOOL_NAME=ki@schule
ARG PUBLIC_SCHOOL_LOGO_URL=
ENV PUBLIC_SCHOOL_NAME=$PUBLIC_SCHOOL_NAME
ENV PUBLIC_SCHOOL_LOGO_URL=$PUBLIC_SCHOOL_LOGO_URL

RUN npm run build


FROM node:22-slim

WORKDIR /app

COPY --from=builder /repo/frontend/build ./build
COPY --from=builder /repo/frontend/node_modules ./node_modules
COPY --from=builder /repo/frontend/package.json ./

EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "build"]
