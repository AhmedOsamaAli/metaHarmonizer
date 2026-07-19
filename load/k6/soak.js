// Soak: hold a moderate load for a long time to surface slow leaks (memory,
// connection-pool exhaustion, Redis growth). Override the hold with
// `-e SOAK=2h`. Watch container memory + DB/Redis connections during the run.
import { sleep } from 'k6';
import { login, curatorReads } from './lib/flow.js';
import { VUS, THINK, thresholds } from './lib/config.js';

export const options = {
  scenarios: {
    soak: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: VUS },
        { duration: __ENV.SOAK || '30m', target: VUS },
        { duration: '2m', target: 0 },
      ],
    },
  },
  thresholds,
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  if (data.token) curatorReads(data.token);
  sleep(THINK);
}
