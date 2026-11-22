/* Small load test: N requests at fixed concurrency against pages that are not rate limited.
   BASE_URL=https://yourdomain.com TOTAL=3000 CONCURRENCY=50 node load.mjs
   /api/* is rate limited per IP by nginx (20 r/s, burst 40), so a single-machine test cannot
   measure the API; /health/ exercises Gunicorn + PostgreSQL end to end instead. */
const BASE = (process.env.BASE_URL || 'http://127.0.0.1:5174').replace(/\/$/, '');
const TOTAL = Number(process.env.TOTAL || 3000);
const CONCURRENCY = Number(process.env.CONCURRENCY || 50);
const paths = ['/', '/services', '/consultation', '/health/', '/account/'];

let next = 0, ok = 0, failed = 0;
const latencies = [], codes = {};
async function worker() {
  while (next < TOTAL) {
    const path = paths[next++ % paths.length];
    const t0 = performance.now();
    try {
      const r = await fetch(BASE + path);
      await r.arrayBuffer();
      codes[r.status] = (codes[r.status] || 0) + 1;
      r.ok ? ok++ : failed++;
    } catch (e) {
      failed++; codes.network = (codes.network || 0) + 1;
      console.log(`network error on ${path} after ${(performance.now() - t0).toFixed(0)}ms: ${e.cause?.code || e.cause?.message || e.message}`);
    }
    latencies.push(performance.now() - t0);
  }
}
const start = performance.now();
await Promise.all(Array.from({length: CONCURRENCY}, worker));
const secs = (performance.now() - start) / 1000;
latencies.sort((a, b) => a - b);
const pct = p => latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * p))].toFixed(0);
console.log(`${TOTAL} requests, concurrency ${CONCURRENCY}, ${secs.toFixed(1)}s -> ${(TOTAL / secs).toFixed(0)} req/s`);
console.log(`ok ${ok}, failed ${failed}, status codes ${JSON.stringify(codes)}`);
console.log(`latency ms: p50 ${pct(0.5)}  p95 ${pct(0.95)}  p99 ${pct(0.99)}  max ${latencies.at(-1).toFixed(0)}`);
process.exit(failed ? 1 : 0);
