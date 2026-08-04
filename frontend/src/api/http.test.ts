import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  apiFetch,
  getAccessToken,
  isGuestMode,
  onTokenChange,
  setAccessToken,
  setGuestMode,
} from './http';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

afterEach(() => {
  setAccessToken(null);
  setGuestMode(false);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('access-token store', () => {
  it('stores and clears the in-memory token', () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken('abc');
    expect(getAccessToken()).toBe('abc');
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });

  it('notifies subscribers and stops after unsubscribe', () => {
    const seen: (string | null)[] = [];
    const off = onTokenChange((t) => seen.push(t));
    setAccessToken('t1');
    off();
    setAccessToken('t2');
    expect(seen).toEqual(['t1']);
  });
});

describe('ApiError', () => {
  it('carries status, code, message and details', () => {
    const e = new ApiError(409, 'CONFLICT', 'stale', { current_version: 2 });
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe('ApiError');
    expect(e.status).toBe(409);
    expect(e.code).toBe('CONFLICT');
    expect(e.message).toBe('stale');
    expect(e.details).toEqual({ current_version: 2 });
  });
});

describe('apiFetch', () => {
  it('injects the bearer token, sends cookies, and returns parsed JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('tok-123');

    const data = await apiFetch<{ ok: boolean }>('/studies');
    expect(data).toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/studies');
    expect(init.credentials).toBe('include');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok-123');
  });

  it('maps the unified error envelope to an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: 'FORBIDDEN', message: 'no', details: { a: 1 } } }, 403),
      ),
    );
    await expect(apiFetch('/admin/users')).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
      code: 'FORBIDDEN',
      message: 'no',
      details: { a: 1 },
    });
  });

  it('falls back to a plain detail message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'bad input' }, 422)));
    await expect(apiFetch('/harmonize')).rejects.toMatchObject({ status: 422, message: 'bad input' });
  });

  it('returns undefined for 204 No Content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiFetch('/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
  });
});

describe('guest preview gate', () => {
  it('toggles the guest flag', () => {
    expect(isGuestMode()).toBe(false);
    setGuestMode(true);
    expect(isGuestMode()).toBe(true);
  });

  it('blocks writes without touching the network', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    setGuestMode(true);
    await expect(apiFetch('/mappings/1/accept', { method: 'POST' })).rejects.toMatchObject({
      code: 'GUEST_PREVIEW',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('blocks unknown reads without touching the network', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    setGuestMode(true);
    await expect(apiFetch('/definitely/not/a/fixture')).rejects.toMatchObject({
      code: 'GUEST_PREVIEW',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
