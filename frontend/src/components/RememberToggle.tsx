import { BrainCircuit } from 'lucide-react';

import { useRememberDecisions } from '../hooks/useRememberDecisions';

/**
 * Global toggle shown in the review toolbars (ADR-0002). When on, the curator's
 * accept/edit decisions are remembered and pre-applied to their future studies.
 * Available to curators and admins alike.
 */
export default function RememberToggle() {
    const [on, setOn] = useRememberDecisions();
    return (
        <label
            className={`inline-flex cursor-pointer select-none items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                on
                    ? 'border-primary-300 bg-primary-50 text-primary-700 dark:border-primary-500/40 dark:bg-primary-500/15 dark:text-primary-300'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
            title="When on, your accept/edit decisions are remembered and pre-applied to your future studies."
        >
            <input
                type="checkbox"
                className="sr-only"
                checked={on}
                onChange={(e) => setOn(e.target.checked)}
            />
            <BrainCircuit className="h-4 w-4" />
            Remember my decisions
        </label>
    );
}
