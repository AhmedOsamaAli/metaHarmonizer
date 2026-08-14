import { sleep } from 'k6';
import { loginAs, curatorReads } from './lib/flow.js';
import { VUS, HOLD, THINK, PASSWORD, thresholds } from './lib/config.js';

const USER_COUNT = Number(__ENV.USER_COUNT || VUS);
const EMAIL_PREFIX = __ENV.EMAIL_PREFIX || 'load-user';
const EMAIL_DOMAIN = __ENV.EMAIL_DOMAIN || 'capacity.metaharmonizer.online';

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
  const tokens = [];
  for (let index = 1; index <= USER_COUNT; index += 1) {
    const suffix = String(index).padStart(3, '0');
    tokens.push(loginAs(`${EMAIL_PREFIX}-${suffix}@${EMAIL_DOMAIN}`, PASSWORD));
  }
  return { tokens };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  if (token) curatorReads(token);
  sleep(THINK);
}