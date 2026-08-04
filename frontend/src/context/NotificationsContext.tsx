/*  Per-user in-app notifications (bell icon).  */
/*
 * A lightweight, per-user notification centre. Notifications are raised by
 * other parts of the app (e.g. JobsContext when a harmonization finishes) via
 * `notify()`, surfaced as an unread badge on the header bell, and persisted to
 * localStorage so they survive a reload. Storage is namespaced per user id so
 * two accounts sharing a browser never see each other's notifications.
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
import { adminListUsers } from '../api/auth';
import type { User } from '../api/types';
import { useAuth } from './AuthContext';

export type NotificationKind =
    | 'job_done'
    | 'job_failed'
    | 'job_cancelled'
    | 'approval_request'
    | 'info';

export interface AppNotification {
    id: string;
    kind: NotificationKind;
    title: string;
    body: string;
    /** Optional in-app link target (e.g. `/review/<studyId>`). */
    href?: string;
    createdAt: number;
    read: boolean;
}

interface NotificationsContextValue {
    notifications: AppNotification[];
    unreadCount: number;
    /** Raise a new in-app notification (surfaced on the header bell). */
    notify(input: Omit<AppNotification, 'id' | 'createdAt' | 'read'>): void;
    markAllRead(): void;
    dismiss(id: string): void;
    clear(): void;
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

const STORAGE_PREFIX = 'mh.notifs.v1';
const storageKey = (userId: number | null | undefined): string | null =>
    userId == null ? null : `${STORAGE_PREFIX}.${userId}`;

/** Cap stored notifications so the list (and localStorage) stays bounded. */
const MAX_NOTIFICATIONS = 50;

export function adminApprovalNotifications(
    users: User[],
): Array<Omit<AppNotification, 'createdAt' | 'read'>> {
    return users.flatMap((candidate) => {
        if (!candidate.is_active || candidate.role === 'admin') return [];
        const label = candidate.name?.trim() || candidate.email;
        const pending: Array<Omit<AppNotification, 'createdAt' | 'read'>> = [];

        if (!candidate.approved) {
            pending.push({
                id: `account-approval:${candidate.id}`,
                kind: 'approval_request',
                title: 'Account approval needed',
                body: `${label} is waiting for account approval.`,
                href: '/admin',
            });
        }
        if (candidate.admin_requested) {
            pending.push({
                id: `admin-access:${candidate.id}`,
                kind: 'approval_request',
                title: 'Admin access requested',
                body: `${label} requested administrator access.`,
                href: '/admin',
            });
        }
        return pending;
    });
}

function loadPersisted(key: string | null): AppNotification[] {
    if (!key) return [];
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return [];
        const parsed = JSON.parse(raw) as AppNotification[];
        return Array.isArray(parsed) ? parsed.slice(0, MAX_NOTIFICATIONS) : [];
    } catch {
        return [];
    }
}

const makeId = (): string =>
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export function NotificationsProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();
    const userId = user?.id ?? null;

    const [notifications, setNotifications] = useState<AppNotification[]>(() =>
        loadPersisted(storageKey(userId)),
    );

    // Swap to the signed-in user's own notifications on login / logout / account
    // switch within the same browser.
    const lastUserId = useRef<number | null>(userId);
    useEffect(() => {
        if (lastUserId.current === userId) return;
        lastUserId.current = userId;
        setNotifications(loadPersisted(storageKey(userId)));
    }, [userId]);

    // Persist notifications under the current user's key (nothing when logged out).
    useEffect(() => {
        const key = storageKey(userId);
        if (!key) return;
        try {
            localStorage.setItem(key, JSON.stringify(notifications.slice(0, MAX_NOTIFICATIONS)));
        } catch {
            /* storage full / disabled — non-fatal */
        }
    }, [notifications, userId]);

    const notify = useCallback<NotificationsContextValue['notify']>((input) => {
        const entry: AppNotification = {
            ...input,
            id: makeId(),
            createdAt: Date.now(),
            read: false,
        };
        setNotifications((prev) => [entry, ...prev].slice(0, MAX_NOTIFICATIONS));
    }, []);

    useEffect(() => {
        if (user?.role !== 'admin') return;
        let cancelled = false;

        const checkPendingApprovals = async () => {
            try {
                const users = await adminListUsers();
                if (cancelled) return;
                const pending = adminApprovalNotifications(users);
                setNotifications((prev) => {
                    const existing = new Set(prev.map((notification) => notification.id));
                    const additions = pending
                        .filter((notification) => !existing.has(notification.id))
                        .map((notification) => ({
                            ...notification,
                            createdAt: Date.now(),
                            read: false,
                        }));
                    return additions.length > 0
                        ? [...additions, ...prev].slice(0, MAX_NOTIFICATIONS)
                        : prev;
                });
            } catch {}
        };

        void checkPendingApprovals();
        const interval = window.setInterval(checkPendingApprovals, 30_000);
        window.addEventListener('focus', checkPendingApprovals);
        return () => {
            cancelled = true;
            window.clearInterval(interval);
            window.removeEventListener('focus', checkPendingApprovals);
        };
    }, [user?.role]);

    const markAllRead = useCallback(() => {
        setNotifications((prev) =>
            prev.some((n) => !n.read) ? prev.map((n) => ({ ...n, read: true })) : prev,
        );
    }, []);

    const dismiss = useCallback((id: string) => {
        setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, []);

    const clear = useCallback(() => setNotifications([]), []);

    const value = useMemo<NotificationsContextValue>(
        () => ({
            notifications,
            unreadCount: notifications.reduce((n, x) => n + (x.read ? 0 : 1), 0),
            notify,
            markAllRead,
            dismiss,
            clear,
        }),
        [notifications, notify, markAllRead, dismiss, clear],
    );

    return (
        <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
    );
}

export function useNotifications(): NotificationsContextValue {
    const ctx = useContext(NotificationsContext);
    if (!ctx) throw new Error('useNotifications must be used within <NotificationsProvider>');
    return ctx;
}
