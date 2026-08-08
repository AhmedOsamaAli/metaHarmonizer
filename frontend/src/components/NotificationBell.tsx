import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useNavigate } from 'react-router-dom';
import {
    Bell,
    CheckCheck,
    CircleCheck,
    CircleX,
    Info,
    Trash2,
    UserCheck,
    X,
} from 'lucide-react';
import type { ReactNode } from 'react';
import {
    useNotifications,
    type AppNotification,
    type NotificationKind,
} from '../context/NotificationsContext';
import { safeInternalPath } from '../lib/navigation';

const KIND_ICON: Record<NotificationKind, ReactNode> = {
    job_done: <CircleCheck className="h-4 w-4 text-emerald-500" />,
    job_failed: <CircleX className="h-4 w-4 text-rose-500" />,
    job_cancelled: <Info className="h-4 w-4 text-slate-400" />,
    approval_request: <UserCheck className="h-4 w-4 text-amber-500" />,
    info: <Info className="h-4 w-4 text-primary-500" />,
};

function timeAgo(epochMs: number): string {
    const s = Math.max(0, Math.floor((Date.now() - epochMs) / 1000));
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
}

export default function NotificationBell() {
    const {
        notifications,
        unreadCount,
        markAllRead,
        dismiss,
        clear,
    } = useNotifications();
    const navigate = useNavigate();

    const handleOpenChange = (open: boolean) => {
        // Mark everything read when the panel is opened (the badge is "unseen").
        if (open && unreadCount > 0) markAllRead();
    };

    const openNotification = (n: AppNotification) => {
        if (n.href) navigate(safeInternalPath(n.href));
    };

    return (
        <DropdownMenu.Root onOpenChange={handleOpenChange}>
            <DropdownMenu.Trigger
                aria-label={
                    unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'
                }
                className="relative grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:bg-slate-50 data-[state=open]:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:data-[state=open]:bg-slate-800"
            >
                <Bell className="h-4 w-4" />
                {unreadCount > 0 && (
                    <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white">
                        {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                )}
            </DropdownMenu.Trigger>

            <DropdownMenu.Portal>
                <DropdownMenu.Content
                    align="end"
                    sideOffset={8}
                    className="z-50 w-80 origin-top-right animate-fade-in rounded-2xl border border-slate-200 bg-white p-1.5 shadow-pop dark:border-slate-700 dark:bg-slate-900"
                >
                    <div className="flex items-center justify-between px-2.5 py-2">
                        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Notifications</p>
                        {notifications.length > 0 && (
                            <button
                                onClick={clear}
                                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                                Clear all
                            </button>
                        )}
                    </div>

                    <DropdownMenu.Separator className="my-1 h-px bg-slate-100 dark:bg-slate-800" />

                    <div className="max-h-80 overflow-y-auto">
                        {notifications.length === 0 ? (
                            <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                                <CheckCheck className="h-6 w-6 text-slate-300 dark:text-slate-600" />
                                <p className="text-sm text-slate-500 dark:text-slate-400">You're all caught up</p>
                            </div>
                        ) : (
                            notifications.map((n) => (
                                <div
                                    key={n.id}
                                    className={`group flex items-start gap-2.5 rounded-xl px-2.5 py-2 transition hover:bg-slate-50 dark:hover:bg-slate-800 ${
                                        n.href ? 'cursor-pointer' : ''
                                    }`}
                                    onClick={() => openNotification(n)}
                                >
                                    <span className="mt-0.5 shrink-0">{KIND_ICON[n.kind]}</span>
                                    <div className="min-w-0 flex-1">
                                        <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                                            {n.title}
                                        </p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400">{n.body}</p>
                                        <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
                                            {timeAgo(n.createdAt)}
                                        </p>
                                    </div>
                                    <button
                                        aria-label="Dismiss"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            dismiss(n.id);
                                        }}
                                        className="shrink-0 rounded-md p-1 text-slate-300 opacity-0 transition hover:bg-slate-200 hover:text-slate-600 group-hover:opacity-100 dark:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                            ))
                        )}
                    </div>
                </DropdownMenu.Content>
            </DropdownMenu.Portal>
        </DropdownMenu.Root>
    );
}
