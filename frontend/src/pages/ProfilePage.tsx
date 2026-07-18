import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  KeyRound,
  Laptop,
  Plus,
  ShieldCheck,
  Trash2,
  Copy,
  Check,
  LogOut,
  Eye,
  Pencil,
  User as UserIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardHeader, CardBody } from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { LoadingBlock, EmptyState } from '../components/ui/Feedback';
import { useAuth } from '../context/AuthContext';
import {
  changePassword,
  createApiToken,
  listApiTokens,
  listSessions,
  revokeApiToken,
  revokeSession,
} from '../api/auth';
import { ApiError } from '../api/http';
import Input from '../components/ui/Input';
import type { ApiTokenCreated } from '../api/types';

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ProfilePage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const sessions = useQuery({ queryKey: ['sessions'], queryFn: listSessions });
  const tokens = useQuery({ queryKey: ['tokens'], queryFn: listApiTokens });

  const [newToken, setNewToken] = useState<ApiTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [scope, setScope] = useState<'read' | 'write'>('read');

  const [curPw, setCurPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const changePwM = useMutation({
    mutationFn: () => changePassword(curPw, newPw),
    onSuccess: (r) => {
      toast.success(r.message);
      setCurPw('');
      setNewPw('');
      setConfirmPw('');
    },
    onError: (e: unknown) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not change password'),
  });

  const revokeSessionM = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions'] });
      toast.success('Session revoked');
    },
    onError: () => toast.error('Could not revoke session'),
  });

  const createTokenM = useMutation({
    mutationFn: () => createApiToken(scope),
    onSuccess: (t) => {
      setNewToken(t);
      setCopied(false);
      qc.invalidateQueries({ queryKey: ['tokens'] });
      toast.success('API token created');
    },
    onError: () => toast.error('Could not create token'),
  });

  const revokeTokenM = useMutation({
    mutationFn: revokeApiToken,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tokens'] });
      toast.success('Token revoked');
    },
    onError: () => toast.error('Could not revoke token'),
  });

  const copyToken = async () => {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken.token);
    setCopied(true);
    toast.success('Copied to clipboard');
  };

  if (!user) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Profile & security"
        description="Manage your account, active sessions, and API tokens."
      />

      {/* Account summary */}
      <Card>
        <CardBody className="flex flex-wrap items-center gap-4">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary-600 text-white">
            <UserIcon className="h-7 w-7" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{user.name || 'Account'}</p>
            <p className="truncate text-sm text-slate-500">{user.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={user.role === 'admin' ? 'primary' : user.role === 'curator' ? 'teal' : 'slate'}>
              <ShieldCheck className="h-3.5 w-3.5" />
              {user.role}
            </Badge>
            {user.email_verified ? (
              <Badge tone="green">Verified</Badge>
            ) : (
              <Badge tone="amber">Unverified</Badge>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Change password */}
      <Card>
        <CardHeader
          icon={<KeyRound className="h-4 w-4" />}
          title="Change password"
          description="Updating your password signs out your other devices."
        />
        <CardBody>
          <form
            className="grid max-w-md gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              changePwM.mutate();
            }}
          >
            <Input
              type="password"
              label="Current password"
              autoComplete="current-password"
              value={curPw}
              onChange={(e) => setCurPw(e.target.value)}
              required
            />
            <Input
              type="password"
              label="New password"
              autoComplete="new-password"
              minLength={8}
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              required
            />
            <Input
              type="password"
              label="Confirm new password"
              autoComplete="new-password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              error={confirmPw && newPw !== confirmPw ? 'Passwords do not match.' : undefined}
              required
            />
            <Button
              type="submit"
              className="w-fit"
              loading={changePwM.isPending}
              disabled={!curPw || newPw.length < 8 || newPw !== confirmPw}
              icon={<KeyRound className="h-4 w-4" />}
            >
              Update password
            </Button>
          </form>
        </CardBody>
      </Card>

      {/* Sessions */}
      <Card>
        <CardHeader
          icon={<Laptop className="h-4 w-4" />}
          title="Active sessions"
          description="Devices currently signed in to your account."
        />
        <CardBody className="space-y-2">
          {sessions.isLoading ? (
            <LoadingBlock label="Loading sessions…" />
          ) : !sessions.data?.length ? (
            <EmptyState title="No active sessions" />
          ) : (
            sessions.data.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                      {s.user_agent ? shortenUA(s.user_agent) : 'Unknown device'}
                    </p>
                    {s.current && <Badge tone="green">This device</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {s.ip || 'unknown IP'} · last active {timeAgo(s.last_seen ?? s.created_at)}
                  </p>
                </div>
                {!s.current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-600 hover:bg-rose-50"
                    icon={<LogOut className="h-3.5 w-3.5" />}
                    loading={revokeSessionM.isPending && revokeSessionM.variables === s.id}
                    onClick={() => revokeSessionM.mutate(s.id)}
                  >
                    Revoke
                  </Button>
                )}
              </div>
            ))
          )}
        </CardBody>
      </Card>

      {/* API tokens */}
      <Card id="tokens">
        <CardHeader
          icon={<KeyRound className="h-4 w-4" />}
          title="API tokens"
          description="Personal tokens for CLI and programmatic access."
          action={
            <div className="flex items-center gap-2">
              {/* Segmented read/write scope toggle */}
              <div
                role="radiogroup"
                aria-label="Token scope"
                className="inline-flex items-center rounded-lg bg-slate-100 p-0.5"
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={scope === 'read'}
                  onClick={() => setScope('read')}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                    scope === 'read'
                      ? 'bg-white text-slate-800 shadow-sm ring-1 ring-slate-200'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <Eye className="h-3.5 w-3.5" />
                  Read
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={scope === 'write'}
                  onClick={() => setScope('write')}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                    scope === 'write'
                      ? 'bg-white text-accent-700 shadow-sm ring-1 ring-accent-200'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Write
                </button>
              </div>
              <Button
                size="sm"
                icon={<Plus className="h-3.5 w-3.5" />}
                loading={createTokenM.isPending}
                onClick={() => createTokenM.mutate()}
              >
                New token
              </Button>
            </div>
          }
        />
        <CardBody className="space-y-3">
          {/* Freshly created token (shown once) */}
          {newToken && (
            <div className="rounded-xl border border-accent-200 bg-accent-50 p-4">
              <p className="text-xs font-semibold text-accent-800">
                Copy your token now — it won't be shown again.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 truncate rounded-lg bg-white px-3 py-2 font-mono text-xs text-slate-700 ring-1 ring-slate-200">
                  {newToken.token}
                </code>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                  onClick={copyToken}
                >
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              </div>
            </div>
          )}

          {tokens.isLoading ? (
            <LoadingBlock label="Loading tokens…" />
          ) : !tokens.data?.length ? (
            <EmptyState
              icon={<KeyRound className="h-6 w-6" />}
              title="No API tokens yet"
              description="Create a token to use the API from scripts or the CLI."
            />
          ) : (
            tokens.data.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-white text-slate-400 shadow-soft">
                    <KeyRound className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Token #{t.id}</p>
                    <p className="text-xs text-slate-500">
                      Created {new Date(t.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge tone={t.scope === 'write' ? 'indigo' : 'slate'}>
                    {t.scope === 'write' ? <Pencil className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                    {t.scope}
                  </Badge>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-rose-600 hover:bg-rose-50"
                  icon={<Trash2 className="h-3.5 w-3.5" />}
                  loading={revokeTokenM.isPending && revokeTokenM.variables === t.id}
                  onClick={() => revokeTokenM.mutate(t.id)}
                >
                  Revoke
                </Button>
              </div>
            ))
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function shortenUA(ua: string): string {
  const browser =
    /Edg/.test(ua) ? 'Edge' :
    /Chrome/.test(ua) ? 'Chrome' :
    /Firefox/.test(ua) ? 'Firefox' :
    /Safari/.test(ua) ? 'Safari' : 'Browser';
  const os =
    /Windows/.test(ua) ? 'Windows' :
    /Mac/.test(ua) ? 'macOS' :
    /Linux/.test(ua) ? 'Linux' :
    /Android/.test(ua) ? 'Android' :
    /iPhone|iPad/.test(ua) ? 'iOS' : '';
  return os ? `${browser} on ${os}` : browser;
}
