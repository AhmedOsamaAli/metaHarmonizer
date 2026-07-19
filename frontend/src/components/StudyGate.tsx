/*  Study readiness gate.  */
/*
 * Review/Ontology/Quality pages must not be opened until a study has finished
 * harmonizing — otherwise the curator sees an empty or half-populated table.
 * This component renders a state-appropriate placeholder for any study that is
 * not yet in a reviewable state, and auto-refreshes the studies list so the
 * page flips to the real content the moment the backend reports completion.
 */

import { useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, AlertCircle, Ban, Upload } from 'lucide-react';
import type { Study } from '../api/types';
import { Card, CardBody } from './ui/Card';
import Button from './ui/Button';
import PageHeader from './ui/PageHeader';

/** A study is reviewable once harmonization has produced mappings. Anything
 * still in the pipeline (or terminally failed/cancelled) is gated. Unknown or
 * legacy statuses are treated as ready so older studies still open. */
const NOT_READY = new Set(['queued', 'processing', 'pending', 'failed', 'cancelled']);

export function isStudyReady(status: string | undefined | null): boolean {
    if (!status) return true;
    return !NOT_READY.has(status.toLowerCase());
}

export default function StudyGate({ study, title, icon }: { study: Study; title: string; icon?: ReactNode }) {
    const qc = useQueryClient();
    const navigate = useNavigate();
    const status = (study.status ?? '').toLowerCase();
    const inFlight = status === 'queued' || status === 'processing' || status === 'pending';

    // While the study is still processing, poll the studies list so this gate
    // resolves to the real page automatically when harmonization completes.
    useEffect(() => {
        if (!inFlight) return;
        const id = setInterval(() => {
            qc.invalidateQueries({ queryKey: ['studies'] });
        }, 2500);
        return () => clearInterval(id);
    }, [inFlight, qc]);

    return (
        <div className="space-y-6">
            <PageHeader title={title} icon={icon} />
            <Card>
                <CardBody className="flex flex-col items-center gap-4 py-12 text-center">
                    {inFlight ? (
                        <>
                            <Loader2 className="h-10 w-10 animate-spin text-primary-600" />
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                    “{study.name}” is still being harmonized
                                </h3>
                                <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                                    Column and value mappings aren’t ready to review yet. This page
                                    will open automatically as soon as processing finishes — you can
                                    also track progress in the tray at the bottom-right.
                                </p>
                            </div>
                        </>
                    ) : status === 'failed' ? (
                        <>
                            <AlertCircle className="h-10 w-10 text-rose-500" />
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                    Harmonization failed for “{study.name}”
                                </h3>
                                <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                                    There’s nothing to review. Try uploading the file again.
                                </p>
                            </div>
                            <Button icon={<Upload className="h-4 w-4" />} onClick={() => navigate('/upload')}>
                                Back to upload
                            </Button>
                        </>
                    ) : (
                        <>
                            <Ban className="h-10 w-10 text-slate-400" />
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                    Harmonization was cancelled for “{study.name}”
                                </h3>
                                <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                                    Re-upload the file to harmonize it again.
                                </p>
                            </div>
                            <Button icon={<Upload className="h-4 w-4" />} onClick={() => navigate('/upload')}>
                                Back to upload
                            </Button>
                        </>
                    )}
                </CardBody>
            </Card>
        </div>
    );
}
