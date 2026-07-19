// Load: ramp to the target VU count and hold, simulating steady curator
// traffic. Token is fetched once in setup and reused so we measure the read
// path, not Argon2 login hashing. Fails (non-zero exit) if an SLO is breached.
import { sleep } from 'k6';
import { login, curatorReads } from './lib/flow.js';
import { VUS, HOLD, THINK, thresholds } from './lib/config.js';

export const options = {
  scenarios: {
    curators: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: VUS },
        { duration: HOLD, target: VUS },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
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
