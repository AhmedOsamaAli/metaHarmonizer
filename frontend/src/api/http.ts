// Core HTTP layer — auth header injection + transparent 401 refresh.

import type { ApiErrorBody } from './types';
import { guestFixture } from './guestFixtures';

export const BASE = '/api/v1';

/** Typed error carrying the backend's envelope code + message. */
export class ApiError extends Error {
    code: string;
    status: number;
    details?: Record<string, unknown>;

    constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
        this.details = details;
    }
}

/* ---------- In-memory access token (never persisted to localStorage) ---------- */
let accessToken: string | null = null;
const listeners = new Set<(token: string | null) => void>();

export function setAccessToken(token: string | null) {
    accessToken = token;
    listeners.forEach((fn) => fn(token));
}
export function getAccessToken() {
    return accessToken;
}
export function onTokenChange(fn: (token: string | null) => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
}

/* ---------- Guest preview (no account) ---------- */
let guestMode = false;
/** Toggle guest preview. While on, non-auth API calls are blocked so no real
 *  data is fetched and no 401 refresh can bounce the visitor to /login. */
export function setGuestMode(v: boolean) {
    guestMode = v;
}
export function isGuestMode() {
    return guestMode;
}

/* ---------- Refresh coordination (single-flight) ---------- */
let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
    if (!refreshing) {
        refreshing = (async () => {
            try {
                const res = await fetch(`${BASE}/auth/refresh`, {
                    method: 'POST',
                    credentials: 'include',
                });
                if (!res.ok) return false;
                const data = (await res.json()) as { access_token?: string };
                if (data.access_token) {
                    setAccessToken(data.access_token);
                    return true;
                }
                return false;
            } catch {
                return false;
            } finally {
                // Reset after the microtask so concurrent callers share this run.
                setTimeout(() => (refreshing = null), 0);
            }
        })();
    }
    return refreshing;
}

async function parseError(res: Response): Promise<ApiError> {
    let code = `HTTP_${res.status}`;
    let message = res.statusText || 'Request failed';
    let details: Record<string, unknown> | undefined;
    try {
        const body = (await res.json()) as Partial<ApiErrorBody> & Record<string, unknown>;
        if (body?.error) {
            code = body.error.code ?? code;
            message = body.error.message ?? message;
            details = body.error.details;
        } else if (typeof body?.detail === 'string') {
            message = body.detail;
        }
    } catch {
        /* non-JSON error body */
    }
    return new ApiError(res.status, code, message, details);
}

interface Options extends RequestInit {
    /** Skip the automatic 401 -> refresh -> retry dance (used by auth calls). */
    skipAuthRetry?: boolean;
    /** Parse and return JSON (default true). */
    json?: boolean;
}

/** Central fetch wrapper: injects bearer token, sends cookies, retries once on 401. */
export async function apiFetch<T = unknown>(path: string, opts: Options = {}): Promise<T> {
    const { skipAuthRetry, json = true, headers, ...init } = opts;

    // Guest preview has no account. Serve sample fixtures for GETs so the
    // walkthrough shows a realistic curated study, and block everything else
    // (writes, unknown reads) so nothing real is exposed and no 401 -> refresh
    // loop can bounce the visitor to /login. Auth endpoints stay reachable.
    if (guestMode && !path.startsWith('/auth/')) {
        const fx = guestFixture(path, (init.method as string) ?? 'GET');
        if (fx) return fx.data as T;
        throw new ApiError(0, 'GUEST_PREVIEW', 'Sign in to do that.');
    }

    const buildHeaders = (): HeadersInit => {
        const h = new Headers(headers);
        if (accessToken) h.set('Authorization', `Bearer ${accessToken}`);
        return h;
    };

    const doFetch = () =>
        fetch(`${BASE}${path}`, {
            credentials: 'include',
            ...init,
            headers: buildHeaders(),
        });

    let res = await doFetch();

    if (res.status === 401 && !skipAuthRetry && accessToken !== null) {
        const ok = await tryRefresh();
        if (ok) {
            res = await doFetch();
        }
    }

    if (!res.ok) throw await parseError(res);
    if (!json || res.status === 204) return undefined as T;
    return (await res.json()) as T;
}
