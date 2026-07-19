import { Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Upload, Table2, BarChart3, Download, Shield, Activity } from 'lucide-react';
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import Brand from './components/Brand';
import UserMenu from './components/UserMenu';
import NotificationBell from './components/NotificationBell';
import ThemeToggle from './components/ThemeToggle';
import ProtectedRoute from './components/ProtectedRoute';
import OntologyIcon from './components/icons/OntologyIcon';
import { LoadingBlock } from './components/ui/Feedback';
import { useAuth } from './context/AuthContext';
import type { Role } from './api/types';

// Eager: tiny entry pages. Lazy: heavier feature pages (code-split per route).
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
const UploadPage = lazy(() => import('./pages/UploadPage'));
const MappingReview = lazy(() => import('./pages/MappingReview'));
const OntologyReview = lazy(() => import('./pages/OntologyReview'));
const QualityDashboard = lazy(() => import('./pages/QualityDashboard'));
const ExportPage = lazy(() => import('./pages/ExportPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const ActivityPage = lazy(() => import('./pages/ActivityPage'));

const NAV_ITEMS: {
  to: string;
  icon: ComponentType<{ className?: string }>;
  label: string;
  end: boolean;
  minRole?: Role;
}[] = [
  { to: '/upload', icon: Upload, label: 'Upload', end: false, minRole: 'curator' },
  { to: '/review', icon: Table2, label: 'Mappings', end: false },
  { to: '/ontology', icon: OntologyIcon, label: 'Ontology', end: false },
  { to: '/quality', icon: BarChart3, label: 'Quality', end: false },
  { to: '/export', icon: Download, label: 'Export', end: false },
];

function TopNav() {
  const { hasRole, isGuest, exitGuest } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/80">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Brand />

        <nav className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.filter((i) => hasRole(i.minRole ?? 'curator')).map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `relative flex items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? 'text-primary-700 dark:text-primary-300'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.span
                      layoutId="nav-active-pill"
                      className="absolute inset-0 rounded-xl bg-primary-50 dark:bg-primary-500/15"
                      transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                    />
                  )}
                  <Icon className="relative h-4 w-4 shrink-0" />
                  <span className="relative">{label}</span>
                </>
              )}
            </NavLink>
          ))}
          {hasRole('admin') && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                `flex items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`
              }
            >
              <Shield className="h-4 w-4 shrink-0" />
              Admin
            </NavLink>
          )}
          {hasRole('admin') && (
            <NavLink
              to="/activity"
              className={({ isActive }) =>
                `flex items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`
              }
            >
              <Activity className="h-4 w-4 shrink-0" />
              Activity
            </NavLink>
          )}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {isGuest ? (
            <>
              <button
                type="button"
                onClick={() => {
                  exitGuest();
                  navigate('/login');
                }}
                className="rounded-xl px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => {
                  exitGuest();
                  navigate('/register');
                }}
                className="rounded-xl bg-primary-600 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-primary-700"
              >
                Create account
              </button>
            </>
          ) : (
            <>
              <NotificationBell />
              <UserMenu />
            </>
          )}
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="flex items-center gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2 md:hidden dark:border-slate-800">
        {NAV_ITEMS.filter((i) => hasRole(i.minRole ?? 'curator')).map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                isActive ? 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300' : 'text-slate-600 dark:text-slate-300'
              }`
            }
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}

function AppLayout({ children }: { children: ReactNode }) {
  const { isGuest, exitGuest } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="relative flex min-h-screen flex-col">
      {/* Layered ambient background */}
      <div className="pointer-events-none fixed inset-0 -z-10 bg-slate-50 dark:bg-slate-950" />
      <div className="pointer-events-none fixed inset-0 -z-10 bg-mesh-primary" />
      <div className="pointer-events-none fixed inset-0 -z-10 bg-grid-slate bg-grid [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />

      <TopNav />
      {isGuest && (
        <div className="sticky top-16 z-30 flex flex-wrap items-center justify-center gap-x-1.5 border-b border-amber-200 bg-amber-50/95 px-4 py-2 text-center text-xs font-medium text-amber-900 backdrop-blur dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <span>Preview mode — no account, read-only.</span>
          <button
            type="button"
            onClick={() => {
              exitGuest();
              navigate('/register');
            }}
            className="font-semibold underline underline-offset-2 hover:text-amber-950"
          >
            Create an account
          </button>
          <span>or</span>
          <button
            type="button"
            onClick={() => {
              exitGuest();
              navigate('/login');
            }}
            className="font-semibold underline underline-offset-2 hover:text-amber-950"
          >
            sign in
          </button>
          <span>to harmonize studies.</span>
        </div>
      )}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <Suspense fallback={<LoadingBlock />}>
          <div className="animate-fade-in">{children}</div>
        </Suspense>
      </main>
      <footer className="border-t border-slate-200 bg-white/60 py-4 text-center text-xs text-slate-400 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-500">
        MetaHarmonizer Dashboard · Biomedical Metadata Harmonization · cBioPortal Compatible
      </footer>
    </div>
  );
}

/** Wrap an authenticated, shell-rendered page. */
function Shell({ children, role }: { children: ReactNode; role?: 'admin' | 'curator' }) {
  return (
    <ProtectedRoute role={role}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

/** Redirect authenticated users away from login/register. */
function PublicOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, initializing } = useAuth();
  const location = useLocation();
  if (initializing) return null;
  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? '/';
    return <Navigate to={from} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
      <Route path="/verify" element={<VerifyEmailPage />} />
      <Route path="/forgot" element={<PublicOnly><ForgotPasswordPage /></PublicOnly>} />
      <Route path="/reset" element={<ResetPasswordPage />} />

      <Route path="/" element={<Navigate to="/upload" replace />} />
      <Route path="/upload" element={<Shell role="curator"><UploadPage /></Shell>} />
      <Route path="/review" element={<Shell><MappingReview /></Shell>} />
      <Route path="/review/:studyId" element={<Shell><MappingReview /></Shell>} />
      <Route path="/ontology" element={<Shell><OntologyReview /></Shell>} />
      <Route path="/ontology/:studyId" element={<Shell><OntologyReview /></Shell>} />
      <Route path="/quality" element={<Shell><QualityDashboard /></Shell>} />
      <Route path="/quality/:studyId" element={<Shell><QualityDashboard /></Shell>} />
      <Route path="/export" element={<Shell><ExportPage /></Shell>} />
      <Route path="/export/:studyId" element={<Shell><ExportPage /></Shell>} />
      <Route path="/profile" element={<Shell><ProfilePage /></Shell>} />
      <Route path="/admin" element={<Shell role="admin"><AdminPage /></Shell>} />
      <Route path="/activity" element={<Shell role="admin"><ActivityPage /></Shell>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
