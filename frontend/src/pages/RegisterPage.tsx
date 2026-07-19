import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, User as UserIcon, UserPlus, MailCheck } from 'lucide-react';
import AuthLayout from '../components/AuthLayout';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { useAuth } from '../context/AuthContext';
import { ApiError } from '../api/http';

/** Lightweight password strength meter (length + character variety). */
function strength(pw: string): { score: number; label: string; tone: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const levels = [
    { label: 'Too short', tone: 'bg-rose-500' },
    { label: 'Weak', tone: 'bg-rose-500' },
    { label: 'Fair', tone: 'bg-amber-500' },
    { label: 'Good', tone: 'bg-accent-500' },
    { label: 'Strong', tone: 'bg-emerald-500' },
    { label: 'Excellent', tone: 'bg-emerald-600' },
  ];
  return { score, ...levels[Math.min(score, levels.length - 1)] };
}

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [requestAdmin, setRequestAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const pwStrength = useMemo(() => strength(password), [password]);
  const canSubmit = email && password.length >= 8;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const message = await register(email, password, name || undefined, requestAdmin);
      // Register no longer signs the user in — surface the next step instead.
      setDone(message);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.code === 'EMAIL_TAKEN'
            ? 'An account with this email already exists. Try signing in instead.'
            : err.message
          : 'Could not create the account. Please try again.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    // The first account (bootstrap admin) is auto-verified and can sign in right
    // away — its server message says so and never mentions email. Only show the
    // "check your inbox" screen when verification is actually required, so we
    // don't tell the admin to wait for an email that never comes.
    const needsVerification = /verify/i.test(done);
    return (
      <AuthLayout
        title={needsVerification ? 'Check your inbox' : "You're all set"}
        subtitle={
          needsVerification
            ? 'One more step to activate your account.'
            : 'Your admin account is ready — sign in to get started.'
        }
        footer={
          <>
            Ready to continue?{' '}
            <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">
              Go to sign in
            </Link>
          </>
        }
      >
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50">
            {needsVerification ? (
              <MailCheck className="h-7 w-7 text-emerald-600" />
            ) : (
              <UserPlus className="h-7 w-7 text-emerald-600" />
            )}
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">{done}</p>
          {needsVerification && (
            <p className="text-xs text-slate-400">
              Didn’t get it? Check spam, or you can request a new link from the sign-in page.
            </p>
          )}
          <Button className="w-full" onClick={() => navigate('/login')}>
            Go to sign in
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Join the curation workspace."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          name="name"
          label="Full name"
          placeholder="Jane Curator"
          autoComplete="name"
          leftIcon={<UserIcon className="h-4 w-4" />}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
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
          hint="Any email works — trusted domains are approved instantly; others need an admin to approve the account before first sign-in."
        />
        <div>
          <Input
            name="password"
            type="password"
            label="Password"
            placeholder="At least 8 characters"
            autoComplete="new-password"
            required
            minLength={8}
            leftIcon={<Lock className="h-4 w-4" />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {password && (
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                <div
                  className={`h-full rounded-full transition-all ${pwStrength.tone}`}
                  style={{ width: `${(pwStrength.score / 5) * 100}%` }}
                />
              </div>
              <span className="w-16 text-right text-xs font-medium text-slate-500">
                {pwStrength.label}
              </span>
            </div>
          )}
        </div>

        {/* Admin access request — never grants it directly. */}
        <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-3 dark:border-slate-700 dark:bg-slate-800/40">
          <input
            type="checkbox"
            checked={requestAdmin}
            onChange={(e) => setRequestAdmin(e.target.checked)}
            className="checkbox mt-0.5"
          />
          <span className="text-sm">
            <span className="font-medium text-slate-800 dark:text-slate-200">Request admin access</span>
            <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
              You’ll join as a curator. Admin access is never granted automatically — an existing administrator must approve it. You can also request it later.
            </span>
          </span>
        </label>

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700">
            {error}
          </div>
        )}

        <Button
          type="submit"
          className="w-full"
          loading={submitting}
          disabled={!canSubmit}
          icon={<UserPlus className="h-4 w-4" />}
        >
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
