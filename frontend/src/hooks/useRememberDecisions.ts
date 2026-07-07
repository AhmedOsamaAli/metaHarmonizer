import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '../context/AuthContext';

function keyFor(userId: number | undefined): string {
    return `mh:remember-decisions:${userId ?? 'anon'}`;
}

/**
 * Global, per-curator "remember my decisions" preference (ADR-0002).
 *
 * When enabled, accept/edit actions are sent with `remember=true`, so the
 * decision is saved to the curator's personal learned-decision KB and
 * pre-applied to their future studies. Opt-in (default off) and persisted
 * per-user in localStorage so it survives reloads without surprising anyone.
 */
export function useRememberDecisions(): [boolean, (value: boolean) => void] {
    const { user } = useAuth();
    const storageKey = keyFor(user?.id);

    const [on, setOn] = useState<boolean>(() => {
        try {
            return localStorage.getItem(storageKey) === '1';
        } catch {
            return false;
        }
    });

    useEffect(() => {
        try {
            setOn(localStorage.getItem(storageKey) === '1');
        } catch {
            /* localStorage unavailable — keep in-memory value */
        }
    }, [storageKey]);

    const set = useCallback(
        (value: boolean) => {
            setOn(value);
            try {
                localStorage.setItem(storageKey, value ? '1' : '0');
            } catch {
                /* non-fatal */
            }
        },
        [storageKey],
    );

    return [on, set];
}
