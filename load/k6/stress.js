// Stress: push well past the target to find the knee (where latency/errors
// spike). Thresholds are deliberately loose — the goal is to locate the
// breaking point and confirm the app degrades gracefully (429/503, not 5xx).
import { sleep } from 'k6';
import { login, curatorReads } from './lib/flow.js';
import { VUS, THINK } from './lib/config.js';

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: VUS },
        { duration: '1m', target: VUS * 2 },
        { duration: '1m', target: VUS * 4 },
        { duration: '1m', target: VUS * 8 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    // Record the point where errors climb; don't hard-fail the run.
    http_req_failed: ['rate<0.10'],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  if (data.token) curatorReads(data.token);
  sleep(THINK);
}
