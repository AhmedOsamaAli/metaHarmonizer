import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, XCircle } from 'lucide-react';
import AuthLayout from '../components/AuthLayout';
import Button from '../components/ui/Button';
import { Spinner } from '../components/ui/Feedback';
import { verifyEmail } from '../api/auth';
import { ApiError } from '../api/http';

type State = 'verifying' | 'ok' | 'error';

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token');
  const [state, setState] = useState<State>('verifying');
  const [message, setMessage] = useState('');
  // Guard against React 18 StrictMode double-invoking the effect.
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setState('error');
      setMessage('This verification link is missing its token.');
      return;
    }
    verifyEmail(token)
      .then((res) => {
        setState('ok');
        setMessage(res.message);
      })
      .catch((err) => {
        setState('error');
        setMessage(
          err instanceof ApiError
            ? err.message
            : 'This verification link is invalid or has expired.',
        );
      });
  }, [token]);

  return (
    <AuthLayout
      title="Email verification"
      subtitle="Confirming your address."
      footer={
        // Only an escape hatch while verifying; the result state has its own button.
        state === 'verifying' ? (
          <>
            Back to{' '}
            <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">
              sign in
            </Link>
          </>
        ) : undefined
      }
    >
      <div className="space-y-4 text-center">
        {state === 'verifying' && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-50 dark:bg-slate-800">
              <Spinner className="h-7 w-7 text-primary-600" />
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">Verifying your email…</p>
          </>
        )}
        {state === 'ok' && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 dark:bg-emerald-500/15">
              <CheckCircle2 className="h-7 w-7 text-emerald-600" />
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">{message}</p>
            <Button className="w-full" onClick={() => navigate('/login')}>
              Continue to sign in
            </Button>
          </>
        )}
        {state === 'error' && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-50 dark:bg-rose-500/15">
              <XCircle className="h-7 w-7 text-rose-600" />
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">{message}</p>
            <Button variant="secondary" className="w-full" onClick={() => navigate('/login')}>
              Back to sign in
            </Button>
          </>
        )}
      </div>
    </AuthLayout>
  );
}
