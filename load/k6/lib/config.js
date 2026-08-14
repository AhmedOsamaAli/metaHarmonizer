// Shared config for the k6 suite. Every value is overridable per run with
// `-e NAME=value` (e.g. `k6 run load.js -e BASE_URL=https://harmonize.example.org`).

export const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const EMAIL = __ENV.EMAIL || 'admin@example.com';
export const PASSWORD = __ENV.PASSWORD || 'ChangeMe!2026';

// Target concurrency / arrival rate — tune per environment.
export const VUS = Number(__ENV.VUS || 25);
export const HOLD = __ENV.HOLD || '2m';
export const THINK = Number(__ENV.THINK || 1); // seconds between iterations per VU

// Service-level objectives. Breaching a threshold makes k6 exit non-zero, so
// these double as a CI capacity gate.
export const thresholds = {
  http_req_failed: ['rate==0'],
  http_req_duration: ['p(95)<=750', 'p(99)<=1500'],
  checks: ['rate==1'],
};
