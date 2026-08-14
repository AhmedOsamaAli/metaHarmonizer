// Smoke: 1 VU, a handful of iterations. Proves the flow works end-to-end and
// the thresholds are wired. Run this first (and in CI) before any real load.
import { sleep } from 'k6';
import { login, curatorReads, health } from './lib/flow.js';

export const options = {
  vus: 1,
  iterations: 5,
  thresholds: {
    http_req_failed: ['rate==0'],
    checks: ['rate==1'],
  },
};

export default function () {
  health();
  const token = login();
  if (token) curatorReads(token);
  sleep(1);
}
