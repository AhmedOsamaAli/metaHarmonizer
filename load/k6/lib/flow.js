import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, EMAIL, PASSWORD } from './config.js';

// One authenticated login. Argon2 password hashing is intentionally expensive,
// so callers should log in ONCE (in setup) and reuse the token across VUs —
// otherwise the test measures password hashing, not the app under load.
export function login() {
  return loginAs(EMAIL, PASSWORD);
}

export function loginAs(email, password) {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } },
  );
  check(res, {
    'login 200': (r) => r.status === 200,
    'login returns token': (r) => !!r.json('access_token'),
  });
  return res.json('access_token');
}

export function authParams(token, extra = {}) {
  return { headers: { Authorization: `Bearer ${token}` }, ...extra };
}

// One pass of the read-heavy "curator dashboard" traffic: list studies, then
// fan out to the per-study review queue, quality metrics, and mappings.
export function curatorReads(token) {
  const studies = http.get(
    `${BASE_URL}/api/v1/studies`,
    authParams(token, { tags: { name: 'studies' } }),
  );
  check(studies, { 'studies 200': (r) => r.status === 200 });

  http.get(
    `${BASE_URL}/api/v1/target-schemas`,
    authParams(token, { tags: { name: 'target-schemas' } }),
  );

  let list = [];
  try {
    list = studies.json() || [];
  } catch (_) {
    list = [];
  }
  if (Array.isArray(list) && list.length > 0) {
    const id = list[0].id;
    const auth = authParams(token).headers;
    const responses = http.batch([
      ['GET', `${BASE_URL}/api/v1/mappings/${id}/review-queue`, null, { headers: auth, tags: { name: 'review-queue' } }],
      ['GET', `${BASE_URL}/api/v1/quality/${id}`, null, { headers: auth, tags: { name: 'quality' } }],
      ['GET', `${BASE_URL}/api/v1/mappings/${id}`, null, { headers: auth, tags: { name: 'mappings' } }],
    ]);
    responses.forEach((r) =>
      check(r, { 'study read ok': (x) => x.status === 200 || x.status === 404 }),
    );
  }
}

// Unauthenticated readiness probe (Postgres + Redis reachable).
export function health() {
  const r = http.get(`${BASE_URL}/readyz`, { tags: { name: 'readyz' } });
  check(r, { 'readyz responds': (x) => x.status === 200 || x.status === 503 });
  return r;
}
