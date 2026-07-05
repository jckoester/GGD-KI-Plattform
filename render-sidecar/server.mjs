// Render-Sidecar HTTP-Server (Phase 17).
//
// Interner Dienst — NUR vom Backend aufgerufen, nie öffentlich exponieren (kein Netz-
// facing Deployment; localhost/compose-Netz). Reines Rendering: kein LLM, kein Provider,
// keine Moderation, keine Kosten.
//
//   GET  /health          → { status, pool }
//   POST /render/circuit  { source }        → { svg }   | { error }
//   POST /render/math     { tex, display }  → { html }  | { error }
import http from 'node:http';
import { CircuitRenderPool } from './pool.mjs';
import { wrapCircuit, renderMath, sha256, BoundedCache } from './render.mjs';

const HOST = process.env.RENDER_SIDECAR_HOST ?? '127.0.0.1';
const PORT = Number(process.env.RENDER_SIDECAR_PORT ?? 3200);
const POOL_SIZE = Number(process.env.RENDER_POOL_SIZE ?? 2);
const TIMEOUT_MS = Number(process.env.RENDER_TIMEOUT_MS ?? 10000);
const CACHE_MAX = Number(process.env.RENDER_CACHE_MAX ?? 500);
const MAX_BODY = Number(process.env.RENDER_MAX_BODY ?? 128 * 1024); // 128 KB

const pool = new CircuitRenderPool({ size: POOL_SIZE, timeoutMs: TIMEOUT_MS });
const cache = new BoundedCache(CACHE_MAX);

function send(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) { reject(new Error('payload too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); }
      catch { reject(new Error('invalid JSON')); }
    });
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/health') {
      return send(res, 200, { status: 'ok', pool: POOL_SIZE });
    }

    if (req.method === 'POST' && req.url === '/render/circuit') {
      const { source } = await readJson(req);
      if (typeof source !== 'string' || !source.trim()) {
        return send(res, 400, { error: 'source (string) erforderlich' });
      }
      const key = 'circuit:' + sha256(source);
      const hit = cache.get(key);
      if (hit !== undefined) return send(res, 200, { svg: hit, cached: true });
      try {
        const svg = await pool.render(wrapCircuit(source));
        cache.set(key, svg);
        return send(res, 200, { svg });
      } catch (e) {
        return send(res, 422, { error: String(e?.message ?? e).slice(0, 500) });
      }
    }

    if (req.method === 'POST' && req.url === '/render/math') {
      const { tex, display } = await readJson(req);
      if (typeof tex !== 'string' || !tex.trim()) {
        return send(res, 400, { error: 'tex (string) erforderlich' });
      }
      const key = 'math:' + (display ? 'd:' : 'i:') + sha256(tex);
      const hit = cache.get(key);
      if (hit !== undefined) return send(res, 200, { html: hit, cached: true });
      try {
        const html = renderMath(tex, display);
        cache.set(key, html);
        return send(res, 200, { html });
      } catch (e) {
        return send(res, 422, { error: String(e?.message ?? e).slice(0, 500) });
      }
    }

    return send(res, 404, { error: 'not found' });
  } catch (e) {
    return send(res, 400, { error: String(e?.message ?? e).slice(0, 200) });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`render-sidecar auf http://${HOST}:${PORT} (pool=${POOL_SIZE}, timeout=${TIMEOUT_MS}ms)`);
});

async function shutdown() {
  server.close();
  await pool.destroy();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
