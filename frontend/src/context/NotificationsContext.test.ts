import { describe, expect, it } from 'vitest';
import type { User } from '../api/types';
import { adminApprovalNotifications } from './NotificationsContext';

const user = (overrides: Partial<User>): User => ({
    id: 1,
    email: 'curator@example.org',
    name: 'Curator',
    role: 'curator',
    is_active: true,
    email_verified: true,
    approved: true,
    admin_requested: false,
    ...overrides,
});

describe('adminApprovalNotifications', () => {
    it('creates distinct account and admin-access notifications', () => {
        expect(
            adminApprovalNotifications([
                user({ id: 4, approved: false }),
                user({ id: 7, admin_requested: true }),
            ]),
        ).toMatchObject([
            { id: 'account-approval:4', title: 'Account approval needed', href: '/admin' },
            { id: 'admin-access:7', title: 'Admin access requested', href: '/admin' },
        ]);
    });

    it('ignores inactive, approved, and existing admin accounts', () => {
        expect(
            adminApprovalNotifications([
                user({ id: 1 }),
                user({ id: 2, is_active: false, approved: false }),
                user({ id: 3, role: 'admin', admin_requested: true }),
            ]),
        ).toEqual([]);
    });
});