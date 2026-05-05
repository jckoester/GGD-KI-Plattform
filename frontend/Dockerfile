FROM node:22-slim AS builder

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
# docs/user/ muss beim Vite-Build erreichbar sein (Alias $docs → /docs/user)
COPY docs/user/ /docs/user/

ARG PUBLIC_SCHOOL_NAME=ki@schule
ARG PUBLIC_SCHOOL_LOGO_URL=
ENV PUBLIC_SCHOOL_NAME=$PUBLIC_SCHOOL_NAME
ENV PUBLIC_SCHOOL_LOGO_URL=$PUBLIC_SCHOOL_LOGO_URL

RUN npm run build


FROM node:22-slim

WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "build"]
