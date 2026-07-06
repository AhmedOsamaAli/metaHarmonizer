/*  Persistent processing tray — docked job-status widget.  */
/*
 * Shows every in-flight and recently-finished harmonization job. Mounted on
 * every authenticated page (via AppLayout) and fed by the app-root JobsProvider,
 * so it survives tab navigation; the provider persists to localStorage so it
 * survives a full page reload too. This is what lets a curator upload a study,
 * navigate away (or refresh), and still see "processing / ready to review".
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    CheckCircle2,
    AlertCircle,
    Loader2,
    X,
    ChevronDown,
    ChevronUp,
    ArrowRight,
    Ban,
} from 'lucide-react';
import { useJobs, type TrackedJob } from '../context/JobsContext';

function relTime(ms: number): string {
    const s = Math.max(1, Math.round((Date.now() - ms) / 1000));
    if (s < 60) return `${s}s ago`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    return `${h}h ago`;
}

const STAGE_LABEL: Record<string, string> = {
    parse: 'Reading file',
    schema: 'Mapping columns',
    ontology: 'Resolving ontology',
    done: 'Finalizing',
};

export default function ProcessingTray() {
    const { jobs, cancel, dismiss, activeCount } = useJobs();
    const [collapsed, setCollapsed] = useState(true);
    const [hidden, setHidden] = useState(false);
    const navigate = useNavigate();

    if (jobs.length === 0) return null;

    // Hidden → show only a tiny launcher chip so the tray never covers content.
    if (hidden) {
        return (
            <button
                type="button"
                onClick={() => setHidden(false)}
                title="Show harmonization jobs"
                className="fixed bottom-4 right-4 z-50 flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-lg shadow-slate-900/10 hover:bg-slate-50"
            >
                {activeCount > 0 ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary-600" />
                ) : (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                )}
                {activeCount > 0 ? `${activeCount} processing` : 'Jobs'}
            </button>
        );
    }

    return (
        <div className="fixed bottom-4 right-4 z-50 w-[min(90vw,20rem)]">
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
                {/* Header */}
                <div className="flex items-center gap-1 border-b border-slate-100 bg-slate-50/80 pr-1.5">
                    <button
                        type="button"
                        onClick={() => setCollapsed((c) => !c)}
                        className="flex flex-1 items-center justify-between gap-2 px-3 py-2 text-left"
                    >
                        <span className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                            {activeCount > 0 ? (
                                <Loader2 className="h-4 w-4 animate-spin text-primary-600" />
                            ) : (
                                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            )}
                            {activeCount > 0
                                ? `Processing ${activeCount} ${activeCount === 1 ? 'study' : 'studies'}`
                                : 'Harmonization jobs'}
                        </span>
                        {collapsed ? (
                            <ChevronUp className="h-4 w-4 text-slate-400" />
                        ) : (
                            <ChevronDown className="h-4 w-4 text-slate-400" />
                        )}
                    </button>
                    <button
                        type="button"
                        onClick={() => setHidden(true)}
                        title="Hide"
                        className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                {/* Body */}
                {!collapsed && (
                    <ul className="max-h-[55vh] divide-y divide-slate-100 overflow-y-auto">
                        {jobs.map((job) => (
                            <JobRow
                                key={job.studyId}
                                job={job}
                                onCancel={() => cancel(job.studyId)}
                                onDismiss={() => dismiss(job.studyId)}
                                onReview={() => navigate(`/review/${job.studyId}`)}
                            />
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}

function JobRow({
    job,
    onCancel,
    onDismiss,
    onReview,
}: {
    job: TrackedJob;
    onCancel: () => void;
    onDismiss: () => void;
    onReview: () => void;
}) {
    const active = job.phase === 'queued' || job.phase === 'processing';

    return (
        <li className="px-4 py-3">
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900" title={job.studyName}>
                        {job.studyName}
                    </p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-xs">
                        <PhaseBadge job={job} />
                        <span className="text-slate-400">·</span>
                        <span className="text-slate-500">
                            {job.finishedAt ? relTime(job.finishedAt) : relTime(job.startedAt)}
                        </span>
                    </p>
                </div>
                {active ? (
                    <button
                        type="button"
                        onClick={onCancel}
                        title="Cancel"
                        className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                    >
                        <Ban className="h-4 w-4" />
                    </button>
                ) : (
                    <button
                        type="button"
                        onClick={onDismiss}
                        title="Dismiss"
                        className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                        <X className="h-4 w-4" />
                    </button>
                )}
            </div>

            {/* Progress bar while active */}
            {active && (
                <div className="mt-2">
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                            className="h-full rounded-full bg-primary-500 transition-all duration-500"
                            style={{ width: `${Math.max(5, job.pct)}%` }}
                        />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                        {STAGE_LABEL[job.stage] ?? job.message} · {job.pct}%
                    </p>
                </div>
            )}

            {/* Action when done */}
            {job.phase === 'done' && (
                <button
                    type="button"
                    onClick={onReview}
                    className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary-700 hover:text-primary-800"
                >
                    Review mappings <ArrowRight className="h-3 w-3" />
                </button>
            )}
            {job.phase === 'failed' && (
                <p className="mt-1.5 text-xs text-rose-600">{job.message || 'Harmonization failed.'}</p>
            )}
        </li>
    );
}

function PhaseBadge({ job }: { job: TrackedJob }) {
    switch (job.phase) {
        case 'done':
            return (
                <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" /> Ready to review
                </span>
            );
        case 'failed':
            return (
                <span className="inline-flex items-center gap-1 font-medium text-rose-700">
                    <AlertCircle className="h-3 w-3" /> Failed
                </span>
            );
        case 'cancelled':
            return <span className="font-medium text-slate-500">Cancelled</span>;
        case 'queued':
            return <span className="font-medium text-amber-600">Queued</span>;
        default:
            return <span className="font-medium text-primary-700">Processing</span>;
    }
}
