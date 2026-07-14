import {
    createContext,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from 'react';
import {
    bootstrapSession,
    login as apiLogin,
    logout as apiLogout,
    register as apiRegister,
    requestAdminAccess as apiRequestAdmin,
} from '../api/auth';
import { setGuestMode } from '../api/http';
import type { Role, User } from '../api/types';

interface AuthContextValue {
    user: User | null;
    /** True until the initial refresh-on-boot resolves. */
    initializing: boolean;
    isAuthenticated: boolean;
    /** True when browsing the no-account preview (read-only, no real data). */
    isGuest: boolean;
    login: (email: string, password: string) => Promise<User>;
    /**
     * Create an account. Does NOT sign in — non-bootstrap users must verify
     * their email first. Resolves to the server's next-step message.
     */
    register: (
        email: string,
        password: string,
        name?: string,
        requestAdmin?: boolean,
    ) => Promise<string>;
    logout: () => Promise<void>;
    setUser: (u: User | null) => void;
    /** Enter the no-account guided preview (synthetic read-only curator). */
    startGuestPreview: () => void;
    /** Leave preview mode (e.g. to sign in / register). */
    exitGuest: () => void;
    /** Ask to be promoted from curator to admin (an admin approves). */
    requestAdmin: () => Promise<void>;
    /** Role hierarchy check: curator < admin. */
    hasRole: (minimum: Role) => boolean;
}

const ROLE_RANK: Record<Role, number> = { curator: 1, admin: 2 };

// Synthetic user for the no-account preview: a read-only curator with no token
// (every write is blocked by the guest gate in api/http).
const GUEST_USER: User = {
    id: 0,
    email: 'guest@preview.local',
    name: 'Guest',
    role: 'curator',
    is_active: true,
    email_verified: true,
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [initializing, setInitializing] = useState(true);
    const [isGuest, setIsGuest] = useState(false);

    // On boot, try to restore a session from the httpOnly refresh cookie.
    useEffect(() => {
        let active = true;
        bootstrapSession()
            .then((u) => {
                if (active) setUser(u);
            })
            .finally(() => {
                if (active) setInitializing(false);
            });
        return () => {
            active = false;
        };
    }, []);

    const value = useMemo<AuthContextValue>(
        () => ({
            user,
            initializing,
            isAuthenticated: !!user,
            isGuest,
            setUser,
            startGuestPreview: () => {
                setGuestMode(true);
                setIsGuest(true);
                setUser(GUEST_USER);
            },
            exitGuest: () => {
                setGuestMode(false);
                setIsGuest(false);
                setUser(null);
            },
            hasRole: (minimum) => !!user && ROLE_RANK[user.role] >= ROLE_RANK[minimum],
            login: async (email, password) => {
                const res = await apiLogin({ email, password });
                setUser(res.user);
                return res.user;
            },
            register: async (email, password, name, requestAdmin) => {
                const res = await apiRegister({
                    email,
                    password,
                    name,
                    request_admin: requestAdmin,
                });
                return res.message;
            },
            requestAdmin: async () => {
                const updated = await apiRequestAdmin();
                setUser(updated);
            },
            logout: async () => {
                if (isGuest) {
                    setGuestMode(false);
                    setIsGuest(false);
                    setUser(null);
                    return;
                }
                await apiLogout();
                setUser(null);
            },
        }),
        [user, initializing, isGuest],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
    return ctx;
}
