# render-sidecar (Phase 17): CircuiTikZ (node-tikzjax) + MathJax → SVG.
# Interner Dienst — NUR vom Backend erreichbar, nie öffentlich exponieren.
FROM node:22-slim

WORKDIR /app

# Nur Manifeste zuerst → npm-ci-Layer wird gecacht, solange die Deps gleich bleiben.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY *.mjs ./
COPY README.md ./

ENV RENDER_SIDECAR_HOST=0.0.0.0 \
    RENDER_SIDECAR_PORT=3200

EXPOSE 3200

# Unprivilegiert laufen (Härtung; die TeX/WASM-Sandbox verhindert ohnehin FS-/Netzzugriff).
USER node

CMD ["node", "server.mjs"]
