// Harmonize submit: stress the write/accept path at a fixed arrival rate. Each
// iteration uploads a UNIQUE tiny CSV so the content-hash dedup guard doesn't
// collapse them into one job. Healthy responses are 202 (accepted), 409
// (deduped) or 503 (queue backpressure) — never 5xx.
//
// IMPORTANT: run this against a stack using ENGINE_IMPL=mock. Against the real
// engine each submit triggers heavy ML work + model loads; that measures the
// engine, not the API accept path.
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL } from './lib/config.js';
import { login } from './lib/flow.js';

export const options = {
  scenarios: {
    submit: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 2), // submissions per second
      timeUnit: '1s',
      duration: __ENV.DURATION || '1m',
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  thresholds: {
    checks: ['rate>0.99'],
    http_req_failed: ['rate<0.05'],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const uniq = `${__VU}-${__ITER}-${Date.now()}`;
  const csv = `SEX,AGE,sample_uid\nMale,42,${uniq}a\nFemale,51,${uniq}b\n`;
  const res = http.post(
    `${BASE_URL}/api/v1/harmonize`,
    { file: http.file(csv, `load_${uniq}.csv`, 'text/csv'), mode: 'schema' },
    { headers: { Authorization: `Bearer ${data.token}` }, tags: { name: 'harmonize' } },
  );
  check(res, {
    'accepted / deduped / backpressure': (r) => [202, 409, 503].includes(r.status),
  });
}
