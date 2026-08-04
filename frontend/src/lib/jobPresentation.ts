import type { JobPhase } from '../context/JobsContext';

export function activeJobMessage(phase: JobPhase): string {
    return phase === 'queued'
        ? 'Waiting for an available worker…'
        : 'Processing with the real engine…';
}