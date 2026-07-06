/*  Job progress over WebSocket (Sprint 4).  */

import { apiFetch } from './http';
import type { JobProgress } from './types';

export async function getWsTicket(): Promise<string> {
    const res = await apiFetch<{ ticket: string }>('/ws/ticket', { method: 'POST' });
    return res.ticket;
}

/** Latest job state for a study — the reliable poll fallback used by the
 * persistent jobs tracker (works even when no WebSocket is connected). */
export interface JobStatus {
    study_id: string;
    /** job_runs lifecycle: queued | running | succeeded | failed | cancelled | dead_letter | null */
    state: string | null;
    attempt: number;
    error_code: string | null;
    /** Latest cached progress snapshot, or null if none yet. */
    progress: JobProgress | null;
}

export async function getJobStatus(studyId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${encodeURIComponent(studyId)}`);
}

/** Request cancellation over HTTP (no WebSocket required). */
export async function cancelJob(studyId: string): Promise<void> {
    await apiFetch(`/jobs/${encodeURIComponent(studyId)}/cancel`, { method: 'POST' });
}

function wsBase(): string {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${window.location.host}/api/v1`;
}

export interface JobSubscription {
    /** Ask the server to cancel the running job. */
    cancel(): void;
    /** Close the socket. */
    close(): void;
}

/**
 * Open a live progress stream for a study's harmonize job. Fetches a one-time
 * ticket, connects, and invokes callbacks for each progress event. Resolves the
 * returned controller once the socket is open.
 */
export async function subscribeJob(
    studyId: string,
    handlers: {
        onProgress: (p: JobProgress) => void;
        onError?: () => void;
        onClose?: () => void;
    },
): Promise<JobSubscription> {
    const ticket = await getWsTicket();
    const ws = new WebSocket(`${wsBase()}/ws/jobs/${encodeURIComponent(studyId)}?ticket=${ticket}`);

    ws.onmessage = (ev) => {
        try {
            handlers.onProgress(JSON.parse(ev.data) as JobProgress);
        } catch {
            /* ignore malformed frames */
        }
    };
    ws.onerror = () => handlers.onError?.();
    ws.onclose = () => handlers.onClose?.();

    return {
        cancel() {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ action: 'cancel' }));
            }
        },
        close() {
            ws.close();
        },
    };
}
