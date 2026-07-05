// Worker-Pool für CircuiTikZ-Rendering.
//
// Warum ein Pool: node-tikzjax lädt ~5 MB WASM je Prozess — ein persistenter Worker
// hält die Engine warm (schnelle Folge-Renders). Warum überhaupt Worker: TeX ist
// turing-vollständig → ein Runaway-Snippet muss hart gestoppt werden können. Läuft der
// Render in einem worker_thread, terminiert der Pool bei Timeout genau diesen Worker
// und startet einen frischen — das Backend/der Server bleibt unbeeinflusst.
//
// Pool-Größe = Concurrency-Cap (mehr gleichzeitige Renders werden eingereiht).
import { Worker } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';

const WORKER_PATH = fileURLToPath(new URL('./worker.mjs', import.meta.url));

export class CircuitRenderPool {
  constructor({ size = 2, timeoutMs = 10000 } = {}) {
    this.size = size;
    this.timeoutMs = timeoutMs;
    this.queue = [];          // wartende Tasks { source, resolve, reject }
    this.workers = [];        // pro Slot: { worker, current, timer, slot }
    this._seq = 0;
    for (let i = 0; i < size; i++) this._spawn(i);
  }

  _spawn(slot) {
    const worker = new Worker(WORKER_PATH);
    const rec = { worker, current: null, timer: null, slot };
    worker.on('message', (msg) => this._onMessage(rec, msg));
    worker.on('error', (err) => this._onError(rec, err));
    worker.on('exit', () => { if (rec.current) this._onError(rec, new Error('worker exited')); });
    this.workers[slot] = rec;
    return rec;
  }

  _settle(rec) {
    const task = rec.current;
    if (rec.timer) clearTimeout(rec.timer);
    rec.timer = null;
    rec.current = null;
    return task;
  }

  _onMessage(rec, msg) {
    const task = this._settle(rec);
    if (!task) return;
    if (msg.error) task.reject(new Error(msg.error));
    else task.resolve(msg.svg);
    this._drain();
  }

  // Fehler / Timeout / unerwarteter Exit: Worker wegwerfen, frischen starten, Task ablehnen.
  _onError(rec, err) {
    const task = this._settle(rec);
    try { rec.worker.terminate(); } catch { /* egal */ }
    this._spawn(rec.slot);        // ersetzt this.workers[slot] durch frischen Worker
    if (task) task.reject(err);
    this._drain();
  }

  _dispatch(rec, task) {
    rec.current = task;
    rec.timer = setTimeout(
      () => this._onError(rec, new Error(`render timeout after ${this.timeoutMs}ms`)),
      this.timeoutMs,
    );
    rec.worker.postMessage({ id: ++this._seq, source: task.source });
  }

  _drain() {
    for (const rec of this.workers) {
      if (rec.current || this.queue.length === 0) continue;
      this._dispatch(rec, this.queue.shift());
    }
  }

  render(source) {
    return new Promise((resolve, reject) => {
      this.queue.push({ source, resolve, reject });
      this._drain();
    });
  }

  async destroy() {
    for (const rec of this.workers) {
      if (rec.timer) clearTimeout(rec.timer);
    }
    await Promise.all(this.workers.map((r) => r.worker.terminate().catch(() => {})));
  }
}
