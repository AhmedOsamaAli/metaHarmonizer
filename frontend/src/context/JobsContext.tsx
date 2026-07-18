/*  Persistent harmonization-job tracker.  */
/*
 * Why this exists
 * ---------------
 * Harmonization runs asynchronously on the backend and can take a while. The
 * old UI kept progress in UploadPage's local state and listened on a single
 * WebSocket, so:
 *   - refreshing the page or switching tabs lost the view (back to "upload"),
 *   - if the WebSocket dropped mid-job the completion event was missed and the
 *     spinner span forever even though the study had finished.
 *
 * This provider is the single source of truth for in-flight + recently-finished
 * jobs. It is mounted once at the app root (above the router) so it survives
 * navigation between tabs, and it persists tracked jobs to localStorage so they
 * survive a full page reload. State is reconciled by POLLING the backend
 * (GET /jobs/{id}) every couple of seconds — a reliable convergence mechanism
 * that always reflects real backend state, even if a WebSocket never connects.
 */

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';
import { useNotifications } from './NotificationsContext';
import { cancelJob as apiCancelJob, getJobStatus } from '../api/jobs';

export type JobPhase = 'queued' | 'processing' | 'done' | 'failed' | 'cancelled';

export interface TrackedJob {
    studyId: string;
    studyName: string;
    rowCount?: number;
    columnCount?: number;
    phase: JobPhase;
    pct: number;
    stage: string;
    message: string;
    /** epoch ms when tracking started (for "started X ago"). */
    startedAt: number;
    /** epoch ms when the job reached a terminal phase, else null. */
    finishedAt: number | null;
}

interface JobsContextValue {
    jobs: TrackedJob[];
    /** True while at least one job is queued/processing. */
    activeCount: number;
    /** Begin tracking a freshly-accepted harmonize job. */
    track(input: {
        studyId: string;
        studyName: string;
        rowCount?: number;
        columnCount?: number;
    }): void;
    /** Request cancellation of a running job. */
    cancel(studyId: string): Promise<void>;
    /** Remove a (typically finished) job from the tray. */
    dismiss(studyId: string): void;
    /** Look up a single tracked job (used by UploadPage). */
    getJob(studyId: string): TrackedJob | undefined;
}

const JobsContext = createContext<JobsContextValue | null>(null);

// Jobs are persisted per-user so two accounts sharing a browser never see each
// other's processing list. The key is namespaced by user id; logged-out has no
// key at all (the tray is empty until someone signs in).
const STORAGE_PREFIX = 'mh.jobs.v1';
const storageKey = (userId: number | null | undefined): string | null =>
    userId == null ? null : `${STORAGE_PREFIX}.${userId}`;
const POLL_INTERVAL_MS = 2000;
/** Drop finished jobs from storage after this long so the tray self-cleans. */
const FINISHED_TTL_MS = 24 * 60 * 60 * 1000;

const isTerminal = (p: JobPhase) => p === 'done' || p === 'failed' || p === 'cancelled';

/**
 * Fire an OS-level notification for a finished job, but only when the tab is
 * backgrounded — the spec's "navigate away and be alerted when it's done" case.
 * When the tab is focused the in-app toast + bell already cover it. Fully
 * feature-detected and permission-gated; a no-op if unsupported or not granted.
 */
function maybeBrowserNotify(title: string, body: string, href?: string): void {
    try {
        if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
        if (typeof document !== 'undefined' && !document.hidden) return;
        const n = new Notification(title, { body });
        if (href) {
            n.onclick = () => {
                try {
                    window.focus();
                    window.location.assign(href);
                } catch {
                    /* non-fatal */
                }
            };
        }
    } catch {
        /* Notifications unavailable — the in-app bell still fired. */
    }
}

/** Best-effort, one-shot permission prompt when a long job begins. */
function requestNotifyPermission(): void {
    try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
            void Notification.requestPermission();
        }
    } catch {
        /* non-fatal */
    }
}

function loadPersisted(key: string | null): TrackedJob[] {
    if (!key) return [];
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return [];
        const parsed = JSON.parse(raw) as TrackedJob[];
        if (!Array.isArray(parsed)) return [];
        const now = Date.now();
        // Drop stale finished jobs on boot.
        return parsed.filter(
            (j) => !j.finishedAt || now - j.finishedAt < FINISHED_TTL_MS,
        );
    } catch {
        return [];
    }
}

/** Map the backend job state + progress snapshot to our tracker phase/fields. */
function reconcile(prev: TrackedJob, status: Awaited<ReturnType<typeof getJobStatus>>): TrackedJob {
    const snap = status.progress;
    const state = status.state;

    // Determine terminal phase from the authoritative job state first, then the
    // progress snapshot type as a fallback.
    let phase: JobPhase = prev.phase;
    if (state === 'succeeded' || snap?.type === 'complete') phase = 'done';
    else if (state === 'failed' || state === 'dead_letter' || snap?.type === 'failed') phase = 'failed';
    else if (state === 'cancelled' || snap?.type === 'cancelled') phase = 'cancelled';
    else if (state === 'running') phase = 'processing';
    else if (state === 'queued') phase = 'queued';

    const pct = phase === 'done' ? 100 : snap?.pct ?? prev.pct;
    const stage = snap?.stage ?? prev.stage;
    const message = snap?.message ?? prev.message;

    const finishedAt =
        isTerminal(phase) && !prev.finishedAt ? Date.now() : prev.finishedAt;

    return { ...prev, phase, pct, stage, message, finishedAt };
}

export function JobsProvider({ children }: { children: ReactNode }) {
    const { isAuthenticated, user } = useAuth();
    const { notify } = useNotifications();
    const userId = user?.id ?? null;
    const qc = useQueryClient();
    const [jobs, setJobs] = useState<TrackedJob[]>(() => loadPersisted(storageKey(userId)));
    // Keep a ref so the polling interval always sees the latest jobs without
    // being torn down/recreated on every state change.
    const jobsRef = useRef(jobs);
    jobsRef.current = jobs;

    // When the signed-in user changes (login / logout / account switch on the
    // same browser), swap to that user's own persisted jobs so the tray is
    // strictly per-user and never leaks another account's processing list.
    const lastUserId = useRef<number | null>(userId);
    useEffect(() => {
        if (lastUserId.current === userId) return;
        lastUserId.current = userId;
        setJobs(loadPersisted(storageKey(userId)));
    }, [userId]);

    // Persist on every change, under the current user's key (no key when
    // logged out → nothing is written).
    useEffect(() => {
        const key = storageKey(userId);
        if (!key) return;
        try {
            localStorage.setItem(key, JSON.stringify(jobs));
        } catch {
            /* storage full / disabled — non-fatal */
        }
    }, [jobs, userId]);

    const track = useCallback<JobsContextValue['track']>((input) => {
        // A harmonize can run for minutes; ask once so we can alert at the OS
        // level if the curator switches tabs while it runs.
        requestNotifyPermission();
        setJobs((prev) => {
            const existing = prev.find((j) => j.studyId === input.studyId);
            const base: TrackedJob = {
                studyId: input.studyId,
                studyName: input.studyName,
                rowCount: input.rowCount,
                columnCount: input.columnCount,
                phase: 'queued',
                pct: 5,
                stage: 'parse',
                message: 'Starting…',
                startedAt: Date.now(),
                finishedAt: null,
            };
            if (existing) {
                return prev.map((j) => (j.studyId === input.studyId ? { ...base, ...j, finishedAt: null, phase: 'queued' } : j));
            }
            return [base, ...prev];
        });
    }, []);

    const dismiss = useCallback<JobsContextValue['dismiss']>((studyId) => {
        setJobs((prev) => prev.filter((j) => j.studyId !== studyId));
    }, []);

    const cancel = useCallback<JobsContextValue['cancel']>(async (studyId) => {
        try {
            await apiCancelJob(studyId);
            toast('Cancelling…');
        } catch {
            toast.error('Could not request cancellation.');
        }
    }, []);

    const getJob = useCallback(
        (studyId: string) => jobsRef.current.find((j) => j.studyId === studyId),
        [],
    );

    // Polling loop: reconcile every non-terminal job with the backend.
    useEffect(() => {
        if (!isAuthenticated) return;

        let stopped = false;

        const tick = async () => {
            const active = jobsRef.current.filter((j) => !isTerminal(j.phase));
            if (active.length === 0) return;

            const results = await Promise.allSettled(
                active.map(async (j) => ({ id: j.studyId, status: await getJobStatus(j.studyId) })),
            );

            if (stopped) return;

            // Compute the next state and detect terminal transitions *outside*
            // the setState updater. React doesn't run an updater synchronously,
            // so collecting side-effects (notifications) inside it would leave
            // this list empty when we read it below. jobsRef.current is the
            // latest committed state, so it's a safe source of truth here.
            const prev = jobsRef.current;
            const justFinished: TrackedJob[] = [];
            const next = prev.map((j) => {
                const r = results.find(
                    (x) => x.status === 'fulfilled' && x.value.id === j.studyId,
                );
                if (!r || r.status !== 'fulfilled') return j;
                const updated = reconcile(j, r.value.status);
                if (!isTerminal(j.phase) && isTerminal(updated.phase)) {
                    justFinished.push(updated);
                }
                return updated;
            });
            setJobs(next);

            // Side effects for newly-finished jobs (toast + bell + cache refresh).
            for (const job of justFinished) {
                if (job.phase === 'done') {
                    toast.success(`Harmonization complete — ${job.studyName}`);
                    notify({
                        kind: 'job_done',
                        title: 'Harmonization complete',
                        body: `${job.studyName} is ready for review.`,
                        href: `/review/${job.studyId}`,
                    });
                    maybeBrowserNotify(
                        'Harmonization complete',
                        `${job.studyName} is ready for review.`,
                        `/review/${job.studyId}`,
                    );
                    qc.invalidateQueries({ queryKey: ['studies'] });
                } else if (job.phase === 'failed') {
                    toast.error(`Harmonization failed — ${job.studyName}`);
                    notify({
                        kind: 'job_failed',
                        title: 'Harmonization failed',
                        body: `${job.studyName} could not be harmonized. Please try again.`,
                    });
                    maybeBrowserNotify(
                        'Harmonization failed',
                        `${job.studyName} could not be harmonized.`,
                    );
                } else if (job.phase === 'cancelled') {
                    toast(`Harmonization cancelled — ${job.studyName}`);
                    notify({
                        kind: 'job_cancelled',
                        title: 'Harmonization cancelled',
                        body: `${job.studyName} was cancelled.`,
                    });
                }
            }
        };

        // Run immediately on mount (so a reload reconciles at once), then poll.
        void tick();
        const id = setInterval(() => void tick(), POLL_INTERVAL_MS);
        return () => {
            stopped = true;
            clearInterval(id);
        };
    }, [isAuthenticated, qc, notify]);

    const value = useMemo<JobsContextValue>(
        () => ({
            jobs,
            activeCount: jobs.filter((j) => !isTerminal(j.phase)).length,
            track,
            cancel,
            dismiss,
            getJob,
        }),
        [jobs, track, cancel, dismiss, getJob],
    );

    return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}

export function useJobs(): JobsContextValue {
    const ctx = useContext(JobsContext);
    if (!ctx) throw new Error('useJobs must be used within <JobsProvider>');
    return ctx;
}
