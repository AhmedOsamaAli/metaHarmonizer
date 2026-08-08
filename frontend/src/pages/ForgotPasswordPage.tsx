import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, Send, MailCheck } from 'lucide-react';
import AuthLayout from '../components/AuthLayout';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import { forgotPassword } from '../api/auth';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      // Always returns the same message (no account enumeration).
      const res = await forgotPassword(email);
      setDone(res.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email you a secure link."
      footer={
        <>
          Remembered it?{' '}
          <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">
            Back to sign in
          </Link>
        </>
      }
    >
      {done ? (
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 dark:bg-emerald-500/15">
            <MailCheck className="h-7 w-7 text-emerald-600" />
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">{done}</p>
          <p className="text-xs text-slate-400">
            The link expires in 30 minutes. Check your spam folder if it doesn't arrive.
          </p>
        </div>
      ) : (
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
            hint="Enter the address you registered with."
          />
          <Button
            type="submit"
            className="w-full"
            loading={submitting}
            disabled={!email}
            icon={<Send className="h-4 w-4" />}
          >
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
