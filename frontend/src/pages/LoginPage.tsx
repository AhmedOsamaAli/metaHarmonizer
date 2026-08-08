import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Mail, Lock, LogIn, Compass } from 'lucide-react';
import { toast } from 'sonner';
import AuthLayout from '../components/AuthLayout';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { useAuth } from '../context/AuthContext';
import { ApiError } from '../api/http';
import { resendVerification } from '../api/auth';
import { safeInternalPath } from '../lib/navigation';

export default function LoginPage() {
  const { login, startGuestPreview } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = safeInternalPath((location.state as { from?: string } | null)?.from);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsVerify, setNeedsVerify] = useState(false);
  const [resending, setResending] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNeedsVerify(false);
    setSubmitting(true);
    try {
      const user = await login(email, password, remember);
      toast.success(`Welcome back, ${user.name || user.email}`);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_NOT_VERIFIED') {
        setNeedsVerify(true);
        setError('Please verify your email address before signing in.');
      } else {
        const msg =
          err instanceof ApiError
            ? err.code === 'ACCOUNT_LOCKED'
              ? 'Too many attempts. Please wait a few minutes and try again.'
              : err.message
            : 'Sign in failed. Please try again.';
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      await resendVerification(email);
      toast.success('Verification email sent. Check your inbox.');
      setNeedsVerify(false);
    } catch {
      toast.error('Could not send the email. Please try again.');
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Access your harmonization workspace."
      footer={
        <>
          New to MetaHarmonizer?{' '}
          <Link to="/register" className="font-semibold text-primary-600 hover:text-primary-700">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          name="email"
          type="email"
          label="Email"
          placeholder="you@institution.org"
          autoComplete="email"
          required
          leftIcon={<Mail className="h-4 w-4" />}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          name="password"
          type="password"
          label="Password"
          placeholder="••••••••"
          autoComplete="current-password"
          required
          leftIcon={<Lock className="h-4 w-4" />}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <div className="flex items-center justify-between -mt-1">
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              className="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            Remember me
          </label>
          <Link
            to="/forgot"
            className="text-xs font-medium text-primary-600 hover:text-primary-700"
          >
            Forgot password?
          </Link>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700">
            {error}
            {needsVerify && (
              <button
                type="button"
                onClick={handleResend}
                disabled={resending}
                className="mt-1.5 block font-semibold text-rose-800 underline underline-offset-2 disabled:opacity-60"
              >
                {resending ? 'Sending…' : 'Resend verification email'}
              </button>
            )}
          </div>
        )}

        <Button
          type="submit"
          className="w-full"
          loading={submitting}
          icon={<LogIn className="h-4 w-4" />}
        >
          Sign in
        </Button>
      </form>

      <div className="mt-5">
        <div className="relative flex items-center">
          <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
          <span className="px-3 text-xs font-medium text-slate-400 dark:text-slate-500">or</span>
          <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        </div>
        <button
          type="button"
          onClick={() => {
            startGuestPreview();
            navigate('/', { replace: true });
          }}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Compass className="h-4 w-4" />
          Explore a live demo — no account needed
        </button>
        <p className="mt-2 text-center text-xs text-slate-400 dark:text-slate-500">
          A guided, read-only walkthrough of what curators and admins do.
        </p>
      </div>
    </AuthLayout>
  );
}
