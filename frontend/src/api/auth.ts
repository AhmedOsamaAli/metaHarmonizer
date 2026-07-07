/*  Auth, sessions, API tokens, and admin endpoints.  */

import { apiFetch, setAccessToken, BASE, getAccessToken } from './http';
import type {
    ApiTokenCreated,
    ApiTokenInfo,
    MessageResponse,
    Role,
    SessionInfo,
    TokenResponse,
    User,
} from './types';

/* ---------- Auth ---------- */

export async function register(input: {
    email: string;
    password: string;
    name?: string;
    request_admin?: boolean;
}): Promise<MessageResponse> {
    // Register no longer logs the user in: non-bootstrap accounts must confirm
    // their email first. The response is a human-readable next-step message.
    return apiFetch<MessageResponse>('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
        skipAuthRetry: true,
    });
}

export async function login(input: { email: string; password: string }): Promise<TokenResponse> {
    const res = await apiFetch<TokenResponse>('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
        skipAuthRetry: true,
    });
    setAccessToken(res.access_token);
    return res;
}

/* ---------- Email verification + password reset ---------- */

export async function verifyEmail(token: string): Promise<MessageResponse> {
    return apiFetch<MessageResponse>('/auth/verify-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
        skipAuthRetry: true,
    });
}

export async function resendVerification(email: string): Promise<MessageResponse> {
    return apiFetch<MessageResponse>('/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
        skipAuthRetry: true,
    });
}

export async function forgotPassword(email: string): Promise<MessageResponse> {
    return apiFetch<MessageResponse>('/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
        skipAuthRetry: true,
    });
}

export async function resetPassword(token: string, password: string): Promise<MessageResponse> {
    return apiFetch<MessageResponse>('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
        skipAuthRetry: true,
    });
}

/**
 * Attempt to restore a session from the refresh cookie (called on app boot).
 *
 * Single-flighted: refresh tokens are rotated server-side (each call revokes
 * the presented token and issues a new one), so two concurrent calls would
 * race — the second would send the now-revoked cookie and fail, signing the
 * user out. React 18 StrictMode double-invokes mount effects in dev, which
 * triggers exactly that. Sharing one in-flight promise guarantees a single
 * /auth/refresh per boot regardless of how many callers ask.
 */
let bootstrapInFlight: Promise<User | null> | null = null;

export async function bootstrapSession(): Promise<User | null> {
    if (bootstrapInFlight) return bootstrapInFlight;
    bootstrapInFlight = (async () => {
        try {
            const res = await apiFetch<TokenResponse>('/auth/refresh', {
                method: 'POST',
                skipAuthRetry: true,
            });
            setAccessToken(res.access_token);
            return res.user;
        } catch {
            setAccessToken(null);
            return null;
        } finally {
            // Allow a later, deliberate re-bootstrap (e.g. after logout) to run.
            bootstrapInFlight = null;
        }
    })();
    return bootstrapInFlight;
}

export async function getMe(): Promise<User> {
    return apiFetch<User>('/auth/me');
}

export async function changePassword(
    currentPassword: string,
    newPassword: string,
): Promise<MessageResponse> {
    return apiFetch<MessageResponse>('/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
}

export async function logout(): Promise<void> {
    try {
        await apiFetch('/auth/logout', { method: 'POST', json: false });
    } finally {
        setAccessToken(null);
    }
}

/* ---------- Sessions ---------- */

export async function listSessions(): Promise<SessionInfo[]> {
    return apiFetch<SessionInfo[]>('/auth/sessions');
}

export async function revokeSession(id: number): Promise<void> {
    await apiFetch(`/auth/sessions/${id}`, { method: 'DELETE', json: false });
}

/* ---------- API tokens ---------- */

export async function listApiTokens(): Promise<ApiTokenInfo[]> {
    return apiFetch<ApiTokenInfo[]>('/tokens');
}

export async function createApiToken(scope: 'read' | 'write'): Promise<ApiTokenCreated> {
    return apiFetch<ApiTokenCreated>('/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope }),
    });
}

export async function revokeApiToken(id: number): Promise<void> {
    await apiFetch(`/tokens/${id}`, { method: 'DELETE', json: false });
}

/* ---------- Admin ---------- */

export async function adminListUsers(): Promise<User[]> {
    return apiFetch<User[]>('/admin/users');
}

export async function adminSetRole(userId: number, role: Role): Promise<User> {
    return apiFetch<User>(`/admin/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
    });
}

export async function adminApproveAdmin(userId: number): Promise<User> {
    return apiFetch<User>(`/admin/users/${userId}/approve-admin`, { method: 'POST' });
}

export async function adminRejectAdmin(userId: number): Promise<User> {
    return apiFetch<User>(`/admin/users/${userId}/reject-admin`, { method: 'POST' });
}

export async function adminSetActive(userId: number, isActive: boolean): Promise<User> {
    return apiFetch<User>(`/admin/users/${userId}/active`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive }),
    });
}

export async function adminForceLogout(userId: number): Promise<void> {
    await apiFetch(`/admin/users/${userId}/logout`, { method: 'POST', json: false });
}

/* ---------- Schema versions (admin, U9) ---------- */

export interface SchemaVersion {
    id: number;
    label: string;
    is_current: boolean;
    source_path: string | null;
    created_at: string;
}

export async function adminListSchemaVersions(): Promise<SchemaVersion[]> {
    return apiFetch<SchemaVersion[]>('/admin/schema-versions');
}

export async function adminUploadSchemaVersion(
    label: string,
    file: File,
    promote = false,
): Promise<{ id: number; label: string; is_current: boolean }> {
    const form = new FormData();
    form.append('file', file);
    const params = new URLSearchParams({ label, promote: String(promote) });
    return apiFetch(`/admin/schema-versions?${params}`, { method: 'POST', body: form });
}

export async function adminPromoteSchemaVersion(
    versionId: number,
): Promise<{ id: number; label: string; is_current: boolean }> {
    return apiFetch(`/admin/schema-versions/${versionId}/promote`, { method: 'POST' });
}

export interface SchemaDiff {
    from: { id: number; label: string };
    to: { id: number; label: string };
    added_fields: { field: string; value_count: number }[];
    removed_fields: { field: string; value_count: number }[];
    changed_fields: { field: string; added_values: string[]; removed_values: string[] }[];
    summary: { added: number; removed: number; changed: number; unchanged: number };
}

export async function adminDiffSchemaVersions(
    fromId: number,
    toId: number,
): Promise<SchemaDiff> {
    const params = new URLSearchParams({ from_id: String(fromId), to_id: String(toId) });
    return apiFetch<SchemaDiff>(`/admin/schema-versions/diff?${params}`);
}

// ── Learned-decision KB (ADR-0002) promotion queue ───────────────────────────
export interface LearnedCandidate {
    kind: 'schema' | 'ontology';
    source_key: string;
    decision: 'accept' | 'reject';
    target_field: string | null;
    target_term: string | null;
    target_id: string | null;
    curators: number;
    support: number;
}

export async function adminListLearnedCandidates(
    minSupport = 1,
): Promise<{ count: number; candidates: LearnedCandidate[] }> {
    return apiFetch(`/admin/learned-decisions/candidates?min_support=${minSupport}`);
}

export async function adminPromoteLearned(c: {
    kind: string;
    source_key: string;
    decision: string;
    target_field?: string | null;
    target_term?: string | null;
    target_id?: string | null;
}): Promise<{ promoted: unknown }> {
    return apiFetch('/admin/learned-decisions/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(c),
    });
}

// ── Column-name alias dictionary (schema-mapper aliases) ─────────────────────
export interface AliasStatus {
    present: boolean;
    alias_count: number;
    field_count: number;
}

export async function adminGetAliases(): Promise<AliasStatus> {
    return apiFetch<AliasStatus>('/admin/schema-aliases');
}

export async function adminUploadAliases(file: File): Promise<AliasStatus> {
    const form = new FormData();
    form.append('file', file);
    return apiFetch<AliasStatus>('/admin/schema-aliases', { method: 'POST', body: form });
}

export interface AliasEntry {
    source: string;
    field_name: string;
    builtin: boolean;
}

export async function adminSchemaFields(): Promise<{ fields: string[] }> {
    return apiFetch<{ fields: string[] }>('/admin/schema-fields');
}

export async function adminListAliasEntries(
    q = '',
    limit = 500,
): Promise<{ total: number; returned: number; entries: AliasEntry[] }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q) params.set('q', q);
    return apiFetch(`/admin/schema-aliases/entries?${params}`);
}

export async function adminAddAlias(source: string, fieldName: string): Promise<{ ok: boolean }> {
    return apiFetch('/admin/schema-aliases/entry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, field_name: fieldName }),
    });
}

export async function adminDeleteAlias(source: string, fieldName: string): Promise<{ ok: boolean }> {
    const params = new URLSearchParams({ source, field_name: fieldName });
    return apiFetch(`/admin/schema-aliases/entry?${params}`, { method: 'DELETE' });
}

/** Download the alias dictionary as a CSV file (authenticated fetch → blob). */
export async function adminExportAliases(scope: 'merged' | 'custom' = 'merged'): Promise<void> {
    const token = getAccessToken();
    const res = await fetch(`${BASE}/admin/schema-aliases/export?scope=${scope}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aliases_${scope}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}
