import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Shield, Users, LogOut, Ban, CheckCircle2, ShieldCheck, X, MailWarning, Layers, Upload, CheckCheck, GitCompare, BrainCircuit, Search, Plus, Trash2, Download, RefreshCw, Network } from 'lucide-react';
import { toast } from 'sonner';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardHeader, CardBody } from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { LoadingBlock, EmptyState } from '../components/ui/Feedback';
import { useAuth } from '../context/AuthContext';
import {
  adminApproveAccount,
  adminApproveAdmin,
  adminForceLogout,
  adminListUsers,
  adminListSchemaVersions,
  adminPromoteSchemaVersion,
  adminRejectAccount,
  adminRejectAdmin,
  adminSetActive,
  adminSetRole,
  adminUploadSchemaVersion,
  adminDiffSchemaVersions,
  adminListLearnedCandidates,
  adminPromoteLearned,
  adminGetAliases,
  adminUploadAliases,
  adminSchemaFields,
  adminListAliasEntries,
  adminAddAlias,
  adminDeleteAlias,
  adminExportAliases,
} from '../api/auth';
import { listEngineTargetSchemas } from '../api/client';
import type { SchemaDiff, LearnedCandidate, AliasEntry } from '../api/auth';
import type { Role, User } from '../api/types';
import {
  approveFederationImport,
  exportFederationBundle,
  importFederationBundle,
  listFederationImports,
  rejectFederationImport,
  type FederationBundle,
} from '../api/federation';

const ROLES: Role[] = ['curator', 'admin'];

export default function AdminPage() {
  const { user: me } = useAuth();
  const qc = useQueryClient();

  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: adminListUsers });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'users'] });

  const roleM = useMutation({
    mutationFn: ({ id, role }: { id: number; role: Role }) => adminSetRole(id, role),
    onSuccess: (u) => {
      invalidate();
      toast.success(`${u.email} is now ${u.role}`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not change role'),
  });

  const activeM = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) => adminSetActive(id, isActive),
    onSuccess: (u) => {
      invalidate();
      toast.success(`${u.email} ${u.is_active ? 'enabled' : 'disabled'}`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not update account'),
  });

  const logoutM = useMutation({
    mutationFn: adminForceLogout,
    onSuccess: () => toast.success('All sessions revoked'),
    onError: () => toast.error('Could not force sign-out'),
  });

  const approveM = useMutation({
    mutationFn: adminApproveAdmin,
    onSuccess: (u) => {
      invalidate();
      toast.success(`${u.email} is now an admin`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not approve request'),
  });

  const rejectM = useMutation({
    mutationFn: adminRejectAdmin,
    onSuccess: (u) => {
      invalidate();
      toast(`Admin request for ${u.email} declined`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not decline request'),
  });

  const approveAccountM = useMutation({
    mutationFn: adminApproveAccount,
    onSuccess: (u) => {
      invalidate();
      toast.success(`${u.email} approved — they can now sign in`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not approve account'),
  });

  const rejectAccountM = useMutation({
    mutationFn: adminRejectAccount,
    onSuccess: (u) => {
      invalidate();
      toast(`${u.email} rejected`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not reject account'),
  });

  const stats = computeStats(users.data ?? []);
  const pendingRequests = (users.data ?? []).filter((u) => u.admin_requested && u.role !== 'admin');
  const pendingApprovals = (users.data ?? []).filter((u) => !u.approved && u.is_active);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Admin console"
        description="Manage team members, roles, and access."
        icon={<Shield className="h-6 w-6" />}
        actions={
          <Badge tone="primary">
            <Shield className="h-3.5 w-3.5" />
            Admin only
          </Badge>
        }
      />

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Total users" value={stats.total} />
        <Stat label="Admins" value={stats.admin} tone="text-primary-600" />
        <Stat label="Curators" value={stats.curator} tone="text-accent-600" />
        <Stat label="Disabled" value={stats.disabled} tone="text-rose-600" />
      </div>

      {/* Pending admin-access requests */}
      {pendingRequests.length > 0 && (
        <Card className="overflow-hidden border-amber-200 dark:border-amber-500/30">
          <div className="flex items-center gap-2 border-b border-amber-100 bg-amber-50/70 px-5 py-3 dark:border-amber-500/20 dark:bg-amber-500/10">
            <ShieldCheck className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              Admin access requests
              <span className="ml-1.5 font-normal text-amber-600 dark:text-amber-400">({pendingRequests.length})</span>
            </h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {pendingRequests.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">{u.name || u.email}</p>
                  <p className="truncate text-xs text-slate-500">{u.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                    loading={approveM.isPending && approveM.variables === u.id}
                    onClick={() => approveM.mutate(u.id)}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
                    icon={<X className="h-3.5 w-3.5" />}
                    loading={rejectM.isPending && rejectM.variables === u.id}
                    onClick={() => rejectM.mutate(u.id)}
                  >
                    Decline
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Pending account approvals (untrusted-domain signups) */}
      {pendingApprovals.length > 0 && (
        <Card className="overflow-hidden border-sky-200 dark:border-sky-500/30">
          <div className="flex items-center gap-2 border-b border-sky-100 bg-sky-50/70 px-5 py-3 dark:border-sky-500/20 dark:bg-sky-500/10">
            <ShieldCheck className="h-4 w-4 text-sky-600 dark:text-sky-400" />
            <h3 className="text-sm font-semibold text-sky-800 dark:text-sky-300">
              Pending approvals
              <span className="ml-1.5 font-normal text-sky-600 dark:text-sky-400">({pendingApprovals.length})</span>
            </h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {pendingApprovals.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">{u.name || u.email}</p>
                  <p className="flex items-center gap-1.5 truncate text-xs text-slate-500">
                    {u.email}
                    {u.admin_requested && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                        also requested admin
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                    loading={approveAccountM.isPending && approveAccountM.variables === u.id}
                    onClick={() => approveAccountM.mutate(u.id)}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
                    icon={<X className="h-3.5 w-3.5" />}
                    loading={rejectAccountM.isPending && rejectAccountM.variables === u.id}
                    onClick={() => rejectAccountM.mutate(u.id)}
                  >
                    Reject
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="overflow-hidden">
        {users.isLoading ? (
          <LoadingBlock label="Loading users…" />
        ) : !users.data?.length ? (
          <EmptyState icon={<Users className="h-6 w-6" />} title="No users found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:bg-slate-800/50">
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {users.data.map((u) => {
                  const isSelf = u.id === me?.id;
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-600 dark:bg-slate-700/60 dark:text-slate-300">
                            {(u.name || u.email).slice(0, 2).toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate font-medium text-slate-800 dark:text-slate-200">
                              {u.name || '—'}
                              {isSelf && <span className="ml-1.5 text-xs text-slate-400">(you)</span>}
                            </p>
                            <p className="truncate text-xs text-slate-500">{u.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <select
                          value={u.role}
                          disabled={isSelf || roleM.isPending}
                          onChange={(e) => roleM.mutate({ id: u.id, role: e.target.value as Role })}
                          className="field !w-auto !py-1.5 text-xs disabled:opacity-60"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-5 py-3">
                        {!u.is_active ? (
                          <Badge tone="rose">
                            <Ban className="h-3.5 w-3.5" />
                            Disabled
                          </Badge>
                        ) : !u.email_verified ? (
                          <Badge tone="amber">
                            <MailWarning className="h-3.5 w-3.5" />
                            Unverified
                          </Badge>
                        ) : (
                          <Badge tone="green">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Active
                          </Badge>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={<LogOut className="h-3.5 w-3.5" />}
                            loading={logoutM.isPending && logoutM.variables === u.id}
                            onClick={() => logoutM.mutate(u.id)}
                          >
                            Force sign-out
                          </Button>
                          <Button
                            variant={u.is_active ? 'ghost' : 'secondary'}
                            size="sm"
                            disabled={isSelf}
                            icon={u.is_active ? <Ban className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                            className={u.is_active ? 'text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10' : ''}
                            loading={activeM.isPending && activeM.variables?.id === u.id}
                            onClick={() => activeM.mutate({ id: u.id, isActive: !u.is_active })}
                          >
                            {u.is_active ? 'Disable' : 'Enable'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <SchemaVersionsCard />
      <AliasDictCard />
      <LearnedDecisionsCard />
      <FederationCard />
    </div>
  );
}

function FederationCard() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const imports = useQuery({
    queryKey: ['admin', 'federation-imports'],
    queryFn: listFederationImports,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'federation-imports'] });

  const importM = useMutation({
    mutationFn: importFederationBundle,
    onSuccess: (result) => {
      refresh();
      toast.success(`Staged ${result.mapping_count} shared decisions for review`);
    },
    onError: (error: any) => toast.error(error?.message ?? 'Could not import bundle'),
  });
  const approveM = useMutation({
    mutationFn: approveFederationImport,
    onSuccess: () => {
      refresh();
      toast.success('Imported decisions promoted to the shared knowledge base');
    },
    onError: (error: any) => toast.error(error?.message ?? 'Could not approve import'),
  });
  const rejectM = useMutation({
    mutationFn: rejectFederationImport,
    onSuccess: () => {
      refresh();
      toast('Federation import rejected');
    },
    onError: (error: any) => toast.error(error?.message ?? 'Could not reject import'),
  });

  const download = async () => {
    try {
      const bundle = await exportFederationBundle();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${bundle.source_instance}-shared-kb.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded ${bundle.payload.mappings.length} shared decisions`);
    } catch (error: any) {
      toast.error(error?.message ?? 'Could not export shared knowledge');
    }
  };

  const upload = async (file: File) => {
    try {
      const bundle = JSON.parse(await file.text()) as FederationBundle;
      importM.mutate(bundle);
    } catch {
      toast.error('Bundle must be valid JSON');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const rows = imports.data ?? [];
  return (
    <Card>
      <CardHeader
        icon={<Network className="h-4 w-4" />}
        title="Federation-lite — shared knowledge exchange"
        description="Exchange signed, admin-promoted human decisions between trusted MetaHarmonizer installations. Personal decisions and machine proposals never leave this instance."
        action={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={download}>
              Download bundle
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
            <Button
              size="sm"
              icon={<Upload className="h-3.5 w-3.5" />}
              loading={importM.isPending}
              onClick={() => fileRef.current?.click()}
            >
              Import bundle
            </Button>
          </div>
        }
      />
      <CardBody>
        {imports.isLoading ? (
          <LoadingBlock />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Network className="h-6 w-6" />}
            title="No federation imports"
            description="Imported bundles remain pending until an administrator approves or rejects them."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase text-slate-400 dark:border-slate-800">
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">Decisions</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Received</th>
                  <th className="px-2 py-2 text-right">Review</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-50 dark:border-slate-800/60">
                    <td className="px-2 py-2 font-mono text-xs">{row.source_instance}</td>
                    <td className="px-2 py-2">{row.mapping_count}</td>
                    <td className="px-2 py-2">
                      <Badge tone={row.status === 'approved' ? 'green' : row.status === 'rejected' ? 'rose' : 'amber'}>
                        {row.status}
                      </Badge>
                    </td>
                    <td className="px-2 py-2 text-xs text-slate-500">
                      {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-2 py-2 text-right">
                      {row.status === 'pending' && (
                        <div className="inline-flex gap-2">
                          <Button
                            size="sm"
                            loading={approveM.isPending && approveM.variables === row.id}
                            onClick={() => approveM.mutate(row.id)}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-rose-600"
                            loading={rejectM.isPending && rejectM.variables === row.id}
                            onClick={() => rejectM.mutate(row.id)}
                          >
                            Reject
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tone ?? 'text-slate-900 dark:text-slate-100'}`}>{value}</p>
    </Card>
  );
}

function computeStats(users: User[]) {
  return {
    total: users.length,
    admin: users.filter((u) => u.role === 'admin').length,
    curator: users.filter((u) => u.role === 'curator').length,
    disabled: users.filter((u) => !u.is_active).length,
  };
}

function SchemaVersionsCard() {
  const qc = useQueryClient();
  const engineSchemas = useQuery({ queryKey: ['engine-target-schemas'], queryFn: listEngineTargetSchemas });
  const [target, setTarget] = useState('');
  const activeTarget = target || engineSchemas.data?.[0]?.key || '';
  const versions = useQuery({
    queryKey: ['admin', 'schema-versions', activeTarget],
    queryFn: () => adminListSchemaVersions(activeTarget || undefined),
    enabled: !!activeTarget,
  });
  const fileRef = useRef<HTMLInputElement>(null);
  const [label, setLabel] = useState('');
  const [file, setFile] = useState<File | null>(null);

  // Schema diff (G6 layer A): compare two versions' curated-fields dictionaries.
  const [fromId, setFromId] = useState<number | null>(null);
  const [toId, setToId] = useState<number | null>(null);
  const [diff, setDiff] = useState<SchemaDiff | null>(null);
  const diffM = useMutation({
    mutationFn: () => adminDiffSchemaVersions(fromId!, toId!),
    onSuccess: setDiff,
    onError: (e: any) => toast.error(e?.message ?? 'Could not compute diff'),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'schema-versions'] });

  const uploadM = useMutation({
    mutationFn: () => adminUploadSchemaVersion(activeTarget, label.trim(), file!, true),
    onSuccess: (v) => {
      invalidate();
      toast.success(`Schema ${v.label} uploaded and promoted`);
      setLabel('');
      setFile(null);
      if (fileRef.current) fileRef.current.value = '';
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not upload schema version'),
  });

  const promoteM = useMutation({
    mutationFn: adminPromoteSchemaVersion,
    onSuccess: (v) => {
      invalidate();
      toast.success(`Schema ${v.label} is now current`);
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not promote version'),
  });

  return (
    <Card>
      <CardHeader
        icon={<Layers className="h-4 w-4" />}
        title="Schema versions"
        description="Each target schema keeps its own version lineage. New uploads are new versions of the selected target — existing studies stay pinned."
      />
      <CardBody className="space-y-4">
        {/* Target schema — each target has its own version lineage */}
        <div>
          <label htmlFor="schema-target" className="block text-xs font-medium text-slate-500">
            Target schema
          </label>
          <select
            id="schema-target"
            value={activeTarget}
            onChange={(e) => {
              setTarget(e.target.value);
              setFromId(null);
              setToId(null);
              setDiff(null);
            }}
            className="mt-1 rounded border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {engineSchemas.data?.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>

        {/* Upload form */}
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/40"
          onSubmit={(e) => {
            e.preventDefault();
            if (label.trim() && file && activeTarget) uploadM.mutate();
          }}
        >
          <div>
            <label htmlFor="schema-label" className="block text-xs font-medium text-slate-500">
              Version label
            </label>
            <input
              id="schema-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. v2"
              className="mt-1 w-28 rounded border border-slate-200 px-2 py-1.5 text-sm focus:border-primary-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            />
          </div>
          <div>
            <label htmlFor="schema-file" className="block text-xs font-medium text-slate-500">
              Curated-fields CSV
            </label>
            <input
              id="schema-file"
              ref={fileRef}
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 text-sm file:mr-2 file:rounded file:border-0 file:bg-primary-50 file:px-2 file:py-1 file:text-primary-700 dark:file:bg-primary-500/15 dark:file:text-primary-300"
            />
          </div>
          <Button
            type="submit"
            loading={uploadM.isPending}
            disabled={!label.trim() || !file || !activeTarget}
            icon={<Upload className="h-4 w-4" />}
          >
            Upload &amp; promote
          </Button>
        </form>

        {/* Versions list */}
        {versions.isLoading ? (
          <LoadingBlock label="Loading schema versions…" />
        ) : !versions.data?.length ? (
          <EmptyState title="No schema versions yet" />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {versions.data.map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium text-slate-800 dark:text-slate-200">{v.label}</span>
                  {v.is_current ? (
                    <Badge tone="green">
                      <CheckCheck className="h-3.5 w-3.5" />
                      Current
                    </Badge>
                  ) : null}
                  <span className="text-xs text-slate-400">
                    {new Date(v.created_at).toLocaleDateString()}
                  </span>
                </div>
                {!v.is_current && (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={promoteM.isPending && promoteM.variables === v.id}
                    onClick={() => promoteM.mutate(v.id)}
                  >
                    Make current
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {/* Schema diff (G6 layer A) */}
        {(versions.data?.length ?? 0) >= 2 && (
          <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/40">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <GitCompare className="h-4 w-4" />
              Compare versions
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <select
                aria-label="From version"
                value={fromId ?? ''}
                onChange={(e) => setFromId(Number(e.target.value) || null)}
                className="rounded border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                <option value="">From…</option>
                {versions.data!.map((v) => (
                  <option key={v.id} value={v.id}>{v.label}</option>
                ))}
              </select>
              <span className="text-slate-400">→</span>
              <select
                aria-label="To version"
                value={toId ?? ''}
                onChange={(e) => setToId(Number(e.target.value) || null)}
                className="rounded border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                <option value="">To…</option>
                {versions.data!.map((v) => (
                  <option key={v.id} value={v.id}>{v.label}</option>
                ))}
              </select>
              <Button
                variant="secondary"
                size="sm"
                loading={diffM.isPending}
                disabled={!fromId || !toId || fromId === toId}
                onClick={() => diffM.mutate()}
                icon={<GitCompare className="h-4 w-4" />}
              >
                Compare
              </Button>
            </div>

            {diff && (
              <div className="mt-3 space-y-2 text-sm">
                <p className="text-xs text-slate-500">
                  <span className="font-mono">{diff.from.label}</span> → <span className="font-mono">{diff.to.label}</span>:
                  {' '}{diff.summary.added} added · {diff.summary.removed} removed · {diff.summary.changed} changed · {diff.summary.unchanged} unchanged
                </p>
                {diff.added_fields.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold text-emerald-700">Added fields</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {diff.added_fields.map((f) => (
                        <span key={f.field} className="rounded bg-emerald-50 px-1.5 py-0.5 font-mono text-xs text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                          {f.field}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {diff.removed_fields.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold text-red-700">Removed fields</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {diff.removed_fields.map((f) => (
                        <span key={f.field} className="rounded bg-red-50 px-1.5 py-0.5 font-mono text-xs text-red-700 line-through dark:bg-red-500/15 dark:text-red-300">
                          {f.field}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {diff.changed_fields.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold text-amber-700">Changed allowed values</span>
                    <ul className="mt-1 space-y-1">
                      {diff.changed_fields.map((c) => (
                        <li key={c.field} className="text-xs">
                          <span className="font-mono font-medium text-slate-700 dark:text-slate-300">{c.field}</span>
                          {c.added_values.length > 0 && (
                            <span className="text-emerald-700"> +{c.added_values.join(', ')}</span>
                          )}
                          {c.removed_values.length > 0 && (
                            <span className="text-red-700"> −{c.removed_values.join(', ')}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {diff.summary.added === 0 && diff.summary.removed === 0 && diff.summary.changed === 0 && (
                  <p className="text-xs text-slate-400">No differences — the two schemas are identical.</p>
                )}
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// Two-layer curation KB (ADR-0002): shared promotion queue. All admins see the
// same queue; promoting a personal decision publishes it to the shared layer so
// it applies for every curator. Idempotent, so concurrent admins are safe.
function LearnedDecisionsCard() {
  const qc = useQueryClient();
  const candidates = useQuery({
    queryKey: ['admin', 'learned-candidates'],
    queryFn: () => adminListLearnedCandidates(1),
  });

  const promoteM = useMutation({
    mutationFn: (c: LearnedCandidate) =>
      adminPromoteLearned({
        kind: c.kind,
        source_key: c.source_key,
        decision: c.decision,
        target_field: c.target_field,
        target_term: c.target_term,
        target_id: c.target_id,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'learned-candidates'] });
      toast.success('Promoted to the shared knowledge base');
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not promote decision'),
  });

  const rows = candidates.data?.candidates ?? [];

  return (
    <Card>
      <CardHeader
        icon={<BrainCircuit className="h-4 w-4" />}
        title="Learned decisions — promotion queue"
        description="Curators' remembered decisions. Promote one to the shared layer to apply it for every curator on future studies (two-stage approval)."
        action={
          <button
            type="button"
            onClick={() => candidates.refetch()}
            disabled={candidates.isFetching}
            className="inline-flex items-center gap-1.5 rounded border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            title="Refresh the queue and agreement stats (another admin may have promoted something)"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${candidates.isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />
      <CardBody>
        {candidates.isLoading ? (
          <LoadingBlock />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<BrainCircuit className="h-6 w-6" />}
            title="Nothing to promote yet"
            description="Personal decisions curators choose to remember will appear here with agreement analytics."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
                  <th className="px-2 py-2">Kind</th>
                  <th className="px-2 py-2">Key</th>
                  <th className="px-2 py-2">Decision → target</th>
                  <th className="px-2 py-2 text-center">Curators</th>
                  <th className="px-2 py-2 text-center">Confirmations</th>
                  <th className="px-2 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={`${c.kind}:${c.source_key}`} className="border-b border-slate-50 dark:border-slate-800/60">
                    <td className="px-2 py-2">
                      <Badge tone={c.kind === 'schema' ? 'primary' : 'slate'}>{c.kind}</Badge>
                    </td>
                    <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">{c.source_key}</td>
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-300">
                      {c.decision === 'reject'
                        ? 'reject'
                        : `accept → ${c.target_field ?? c.target_term ?? ''}${
                            c.target_id ? ` (${c.target_id})` : ''
                          }`}
                    </td>
                    <td className="px-2 py-2 text-center font-semibold text-slate-700 dark:text-slate-300">{c.curators}</td>
                    <td className="px-2 py-2 text-center text-slate-600 dark:text-slate-300">{c.support}</td>
                    <td className="px-2 py-2 text-right">
                      <Button
                        size="sm"
                        loading={promoteM.isPending && promoteM.variables?.source_key === c.source_key}
                        onClick={() => promoteM.mutate(c)}
                        icon={<CheckCheck className="h-3.5 w-3.5" />}
                      >
                        Promote
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// Column-name alias dictionary: admins upload a two-column CSV (field, comma-
// separated aliases), or browse/search/add/remove individual aliases. Merged
// with the engine's built-in dictionary and applied on the next harmonize.
function AliasDictCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['admin', 'schema-aliases'], queryFn: adminGetAliases });
  const fields = useQuery({ queryKey: ['admin', 'schema-fields'], queryFn: adminSchemaFields });
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [query, setQuery] = useState('');
  const [addSource, setAddSource] = useState('');
  const [addField, setAddField] = useState('');

  const entries = useQuery({
    queryKey: ['admin', 'alias-entries', query],
    queryFn: () => adminListAliasEntries(query, 500),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'schema-aliases'] });
    qc.invalidateQueries({ queryKey: ['admin', 'alias-entries'] });
  };

  const uploadM = useMutation({
    mutationFn: () => adminUploadAliases(file!),
    onSuccess: (s) => {
      refresh();
      toast.success(`Loaded ${s.alias_count} aliases across ${s.field_count} fields`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = '';
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not upload aliases'),
  });

  const addM = useMutation({
    mutationFn: () => adminAddAlias(addSource.trim(), addField.trim()),
    onSuccess: () => {
      refresh();
      toast.success('Alias added');
      setAddSource('');
      setAddField('');
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not add alias'),
  });

  const delM = useMutation({
    mutationFn: (e: AliasEntry) => adminDeleteAlias(e.source, e.field_name),
    onSuccess: () => {
      refresh();
      toast.success('Alias removed');
    },
    onError: (e: any) => toast.error(e?.message ?? 'Could not remove alias'),
  });

  const fieldList = fields.data?.fields ?? [];
  const unknownField = addField.trim() !== '' && !fieldList.includes(addField.trim());
  const rows = entries.data?.entries ?? [];

  return (
    <Card>
      <CardHeader
        icon={<Layers className="h-4 w-4" />}
        title="Column-name aliases"
        description="Nicknames that teach the schema mapper to recognise messy headers. Uploads and manual edits are merged with the engine's built-in dictionary and applied on the next harmonize."
      />
      <CardBody className="space-y-4">
        <div className="text-sm text-slate-600 dark:text-slate-300">
          {status.data?.present ? (
            <span>
              Custom dictionary: <strong>{status.data.alias_count}</strong> admin aliases across{' '}
              <strong>{status.data.field_count}</strong> fields — merged with the built-ins.
            </span>
          ) : (
            <span className="text-slate-400">
              No custom aliases yet — the schema mapper uses its built-in dictionary.
            </span>
          )}
        </div>

        {/* Bulk upload */}
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/40"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) uploadM.mutate();
          }}
        >
          <div>
            <label htmlFor="alias-file" className="block text-xs font-medium text-slate-500">
              Bulk upload — CSV (field, comma-separated aliases)
            </label>
            <input
              id="alias-file"
              ref={fileRef}
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 text-sm file:mr-2 file:rounded file:border-0 file:bg-primary-50 file:px-2 file:py-1 file:text-primary-700 dark:file:bg-primary-500/15 dark:file:text-primary-300"
            />
          </div>
          <Button type="submit" loading={uploadM.isPending} disabled={!file} icon={<Upload className="h-4 w-4" />}>
            Upload
          </Button>
        </form>

        {/* Add one */}
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/40"
          onSubmit={(e) => {
            e.preventDefault();
            if (addSource.trim() && addField.trim()) addM.mutate();
          }}
        >
          <div>
            <label htmlFor="alias-source" className="block text-xs font-medium text-slate-500">
              Alias (nickname)
            </label>
            <input
              id="alias-source"
              value={addSource}
              onChange={(e) => setAddSource(e.target.value)}
              placeholder="e.g. patient_sex"
              className="mt-1 w-40 rounded border border-slate-200 px-2 py-1.5 text-sm focus:border-primary-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            />
          </div>
          <div>
            <label htmlFor="alias-field" className="block text-xs font-medium text-slate-500">
              Canonical field
            </label>
            <input
              id="alias-field"
              list="schema-fields-list"
              value={addField}
              onChange={(e) => setAddField(e.target.value)}
              placeholder="e.g. sex"
              className={`mt-1 w-40 rounded border px-2 py-1.5 text-sm focus:outline-none dark:bg-slate-900 dark:text-slate-200 ${
                unknownField ? 'border-amber-400' : 'border-slate-200 focus:border-primary-400 dark:border-slate-700'
              }`}
            />
            <datalist id="schema-fields-list">
              {fieldList.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </div>
          <Button
            type="submit"
            loading={addM.isPending}
            disabled={!addSource.trim() || !addField.trim()}
            icon={<Plus className="h-4 w-4" />}
          >
            Add
          </Button>
          {unknownField && (
            <span className="text-xs text-amber-600">
              &ldquo;{addField.trim()}&rdquo; isn&rsquo;t a known schema field — the mapper will ignore it.
            </span>
          )}
        </form>

        {/* Browse + search */}
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="relative max-w-xs flex-1">
              <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search aliases or fields…"
                className="w-full rounded border border-slate-200 py-1.5 pl-8 pr-2 text-sm focus:border-primary-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              />
            </div>
            <button
              type="button"
              onClick={() =>
                adminExportAliases('merged').catch(() => toast.error('Export failed'))
              }
              className="inline-flex items-center gap-1.5 rounded border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              title="Download the full (built-in + custom) alias dictionary as CSV"
            >
              <Download className="h-4 w-4" />
              Export all
            </button>
            <button
              type="button"
              onClick={() =>
                adminExportAliases('custom').catch(() => toast.error('Export failed'))
              }
              className="inline-flex items-center gap-1.5 rounded border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              title="Download only the admin-added (custom) aliases as CSV"
            >
              <Download className="h-4 w-4" />
              Export custom
            </button>
          </div>
          {entries.isLoading ? (
            <LoadingBlock />
          ) : rows.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">No aliases match.</p>
          ) : (
            <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-100 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-3 py-2">Alias</th>
                    <th className="px-3 py-2">Field</th>
                    <th className="px-3 py-2">Source</th>
                    <th className="px-3 py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.source}::${r.field_name}`} className="border-t border-slate-50 dark:border-slate-800/60">
                      <td className="px-3 py-1.5 font-mono text-xs text-slate-700 dark:text-slate-300">{r.source}</td>
                      <td className="px-3 py-1.5 text-slate-700 dark:text-slate-300">{r.field_name}</td>
                      <td className="px-3 py-1.5">
                        <Badge tone={r.builtin ? 'slate' : 'primary'}>{r.builtin ? 'built-in' : 'custom'}</Badge>
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {r.builtin ? (
                          <span className="text-xs text-slate-300">—</span>
                        ) : (
                          <button
                            title="Remove alias"
                            onClick={() => delM.mutate(r)}
                            className="rounded p-1 text-rose-500 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-1 text-xs text-slate-400">
            Showing {entries.data?.returned ?? 0} of {entries.data?.total ?? 0}. Built-ins are read-only; custom rows can be removed.
          </p>
        </div>

        <p className="text-xs text-slate-400">
          Bulk row example: <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">SEX,&quot;gender,patient_sex,gender_at_birth&quot;</code>
        </p>
      </CardBody>
    </Card>
  );
}
