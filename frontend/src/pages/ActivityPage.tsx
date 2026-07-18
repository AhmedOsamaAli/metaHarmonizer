import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import {
  Activity,
  Check,
  X,
  Pencil,
  Layers,
  Sparkles,
  Trash2,
  CircleCheck,
  ShieldCheck,
  UserCog,
  Power,
  LogOut,
  Search,
  ChevronDown,
  Calendar,
  FileSpreadsheet,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { queryAudit } from '../api/client';
import { adminListUsers } from '../api/auth';
import type { AuditEvent, User } from '../api/types';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardBody } from '../components/ui/Card';
import { EmptyState, LoadingBlock } from '../components/ui/Feedback';

/** Human-readable verb + icon + colour per audit action. */
const ACTION_META: Record<string, { verb: string; icon: ReactNode; tone: string; dot: string }> = {
  accept: { verb: 'Accepted a mapping', icon: <Check className="h-4 w-4" />, tone: 'text-emerald-600 bg-emerald-50', dot: 'bg-emerald-500' },
  reject: { verb: 'Rejected a mapping', icon: <X className="h-4 w-4" />, tone: 'text-rose-600 bg-rose-50', dot: 'bg-rose-500' },
  edit: { verb: 'Edited a mapping', icon: <Pencil className="h-4 w-4" />, tone: 'text-amber-600 bg-amber-50', dot: 'bg-amber-500' },
  batch_accepted: { verb: 'Batch-accepted mappings', icon: <Layers className="h-4 w-4" />, tone: 'text-emerald-600 bg-emerald-50', dot: 'bg-emerald-500' },
  batch_rejected: { verb: 'Batch-rejected mappings', icon: <Layers className="h-4 w-4" />, tone: 'text-rose-600 bg-rose-50', dot: 'bg-rose-500' },
  llm_rematch: { verb: 'Ran an LLM rematch', icon: <Sparkles className="h-4 w-4" />, tone: 'text-purple-600 bg-purple-50', dot: 'bg-purple-500' },
  onto_accept: { verb: 'Accepted an ontology term', icon: <Check className="h-4 w-4" />, tone: 'text-emerald-600 bg-emerald-50', dot: 'bg-emerald-500' },
  onto_reject: { verb: 'Rejected an ontology term', icon: <X className="h-4 w-4" />, tone: 'text-rose-600 bg-rose-50', dot: 'bg-rose-500' },
  onto_edit: { verb: 'Edited an ontology term', icon: <Pencil className="h-4 w-4" />, tone: 'text-amber-600 bg-amber-50', dot: 'bg-amber-500' },
  study_delete: { verb: 'Deleted a study', icon: <Trash2 className="h-4 w-4" />, tone: 'text-rose-600 bg-rose-50', dot: 'bg-rose-500' },
  study_complete: { verb: 'Completed a study', icon: <CircleCheck className="h-4 w-4" />, tone: 'text-emerald-600 bg-emerald-50', dot: 'bg-emerald-500' },
  admin_set_role: { verb: 'Changed a user role', icon: <UserCog className="h-4 w-4" />, tone: 'text-indigo-600 bg-indigo-50', dot: 'bg-indigo-500' },
  admin_approve_request: { verb: 'Approved an admin request', icon: <ShieldCheck className="h-4 w-4" />, tone: 'text-indigo-600 bg-indigo-50', dot: 'bg-indigo-500' },
  admin_reject_request: { verb: 'Denied an admin request', icon: <ShieldCheck className="h-4 w-4" />, tone: 'text-slate-600 bg-slate-100', dot: 'bg-slate-400' },
  admin_set_active: { verb: 'Changed account status', icon: <Power className="h-4 w-4" />, tone: 'text-amber-600 bg-amber-50', dot: 'bg-amber-500' },
  admin_force_logout: { verb: 'Forced a sign-out', icon: <LogOut className="h-4 w-4" />, tone: 'text-amber-600 bg-amber-50', dot: 'bg-amber-500' },
};

const ACTION_OPTIONS = Object.keys(ACTION_META);

const TIME_RANGES: { label: string; hours: number | null }[] = [
  { label: 'All time', hours: null },
  { label: 'Last hour', hours: 1 },
  { label: 'Last 24 hours', hours: 24 },
  { label: 'Last 7 days', hours: 24 * 7 },
  { label: 'Last 30 days', hours: 24 * 30 },
  { label: 'Custom range…', hours: null },
];
const CUSTOM_RANGE = TIME_RANGES.length - 1;

function meta(action: string) {
  return (
    ACTION_META[action] ?? {
      verb: action,
      icon: <Activity className="h-4 w-4" />,
      tone: 'text-slate-600 bg-slate-100',
      dot: 'bg-slate-400',
    }
  );
}

function who(e: AuditEvent, usersById: Map<number, User>): string {
  if (e.actor_id != null) {
    const u = usersById.get(e.actor_id);
    if (u) return u.name || u.email;
  }
  return e.details?.curator ?? (e.actor_id != null ? `User #${e.actor_id}` : 'System');
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yest.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export default function ActivityPage() {
  const [action, setAction] = useState('');
  const [studyId, setStudyId] = useState('');
  const [actor, setActor] = useState<User | null>(null);
  const [rangeIdx, setRangeIdx] = useState(0);
  // Custom date range (used when rangeIdx === CUSTOM_RANGE); 'YYYY-MM-DD'.
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: adminListUsers });
  const usersById = useMemo(() => {
    const m = new Map<number, User>();
    for (const u of usersQuery.data ?? []) m.set(u.id, u);
    return m;
  }, [usersQuery.data]);

  // Distinct studies seen in recent activity — fetched independently of the
  // study filter so the picker list stays stable while filtering. (Studies are
  // per-user/private, so there's no global studies list an admin could use.)
  const studyOptionsQuery = useQuery({
    queryKey: ['audit', 'study-options'],
    queryFn: () => queryAudit({ limit: 200 }),
  });
  const studyOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of studyOptionsQuery.data?.items ?? []) {
      if (!e.study_id) continue;
      // study_delete / study_complete carry the study name in new_value.
      if (!map.get(e.study_id) && (e.action === 'study_delete' || e.action === 'study_complete') && e.new_value) {
        map.set(e.study_id, e.new_value);
      } else if (!map.has(e.study_id)) {
        map.set(e.study_id, '');
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [studyOptionsQuery.data]);

  const since = useMemo(() => {
    if (rangeIdx === CUSTOM_RANGE) {
      return fromDate ? new Date(`${fromDate}T00:00:00`).toISOString() : undefined;
    }
    const hrs = TIME_RANGES[rangeIdx].hours;
    if (!hrs) return undefined;
    return new Date(Date.now() - hrs * 3600_000).toISOString();
  }, [rangeIdx, fromDate]);

  const until = useMemo(() => {
    if (rangeIdx === CUSTOM_RANGE && toDate) {
      return new Date(`${toDate}T23:59:59`).toISOString();
    }
    return undefined;
  }, [rangeIdx, toDate]);

  const filters = {
    action: action || undefined,
    study_id: studyId.trim() || undefined,
    actor_id: actor?.id,
    since,
    until,
  };

  const query = useInfiniteQuery({
    queryKey: ['audit', filters],
    queryFn: ({ pageParam }) => queryAudit({ ...filters, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const events = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);

  const groups = useMemo(() => {
    const map = new Map<string, AuditEvent[]>();
    for (const e of events) {
      const key = dayLabel(e.created_at);
      const list = map.get(key) ?? [];
      list.push(e);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [events]);

  const clearFilters = () => {
    setAction('');
    setStudyId('');
    setActor(null);
    setRangeIdx(0);
    setFromDate('');
    setToDate('');
  };
  const hasFilters = !!(action || studyId || actor || rangeIdx);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Activity log"
        description="Every curation and admin decision across the system — who did what, when, and to which study."
      />

      {/* Filters */}
      <Card>
        <CardBody className="flex flex-wrap items-end gap-3">
          {/* Action — with icon + colour per option */}
          <ActionFilter value={action} onChange={setAction} />

          {/* User — searchable picker over existing users/admins */}
          <UserFilter
            users={usersQuery.data ?? []}
            loading={usersQuery.isLoading}
            value={actor}
            onChange={setActor}
          />

          {/* Time range */}
          <WhenFilter
            rangeIdx={rangeIdx}
            onRange={setRangeIdx}
            from={fromDate}
            to={toDate}
            onFrom={setFromDate}
            onTo={setToDate}
          />

          {/* Study — searchable by id or name prefix */}
          <StudyFilter
            studies={studyOptions}
            loading={studyOptionsQuery.isLoading}
            value={studyId}
            onChange={setStudyId}
          />

          {hasFilters && (
            <button onClick={clearFilters} className="btn btn-sm border border-slate-200 text-slate-600 hover:bg-slate-50">
              Clear
            </button>
          )}
        </CardBody>
      </Card>

      {/* Feed */}
      {query.isLoading ? (
        <LoadingBlock label="Loading activity…" />
      ) : events.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-6 w-6" />}
          title="No activity"
          description={hasFilters ? 'No events match these filters.' : 'Decisions will appear here as curators work.'}
        />
      ) : (
        <div className="space-y-6">
          {groups.map(([day, items]) => (
            <div key={day}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{day}</h3>
              <Card>
                <ul className="divide-y divide-slate-100">
                  {items.map((e) => {
                    const m = meta(e.action);
                    return (
                      <li key={e.id} className="flex items-center gap-3 px-4 py-3">
                        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${m.tone}`}>
                          {m.icon}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-slate-800 dark:text-slate-200">
                            <span className="font-semibold">{who(e, usersById)}</span> · {m.verb.toLowerCase()}
                            {e.new_value && <span className="text-slate-500"> · {e.new_value}</span>}
                          </p>
                          <p className="text-xs text-slate-400">
                            {e.study_id ? `Study ${e.study_id} · ` : ''}
                            {timeLabel(e.created_at)}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            </div>
          ))}

          {query.hasNextPage && (
            <div className="flex justify-center">
              <button
                onClick={() => query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
                className="btn btn-sm border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Action filter (icon + colour dropdown) ---------- */

function ActionFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));
  const current = value ? meta(value) : null;
  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Action</span>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="field flex !w-56 items-center justify-between gap-2 !py-2 text-left"
      >
        <span className="flex items-center gap-2 truncate">
          {current ? (
            <>
              <span className={`h-2.5 w-2.5 rounded-full ${current.dot}`} />
              {current.verb}
            </>
          ) : (
            <span className="text-slate-500">All actions</span>
          )}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
          <button
            type="button"
            onClick={() => { onChange(''); setOpen(false); }}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
            All actions
          </button>
          {ACTION_OPTIONS.map((a) => {
            const m = meta(a);
            return (
              <button
                key={a}
                type="button"
                onClick={() => { onChange(a); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <span className={`grid h-6 w-6 place-items-center rounded ${m.tone}`}>{m.icon}</span>
                {m.verb}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------- User filter (searchable picker) ---------- */

function UserFilter({
  users,
  loading,
  value,
  onChange,
}: {
  users: User[];
  loading: boolean;
  value: User | null;
  onChange: (u: User | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return users;
    return users.filter(
      (u) => (u.name ?? '').toLowerCase().includes(needle) || u.email.toLowerCase().includes(needle),
    );
  }, [users, q]);

  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">User</span>
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          window.setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className="field flex !w-56 items-center justify-between gap-2 !py-2 text-left"
      >
        <span className="truncate">
          {value ? (
            <span className="flex items-center gap-2">
              <Avatar user={value} />
              {value.name || value.email}
            </span>
          ) : (
            <span className="text-slate-500">Everyone</span>
          )}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-64 rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name or email…"
              className="w-full text-sm outline-none"
            />
          </div>
          <div className="max-h-64 overflow-auto py-1">
            <button
              type="button"
              onClick={() => { onChange(null); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Everyone
            </button>
            {loading && <p className="px-3 py-2 text-xs text-slate-400">Loading users…</p>}
            {!loading && filtered.length === 0 && (
              <p className="px-3 py-2 text-xs text-slate-400">No users match.</p>
            )}
            {filtered.map((u) => (
              <button
                key={u.id}
                type="button"
                onClick={() => { onChange(u); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                <Avatar user={u} />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{u.name || u.email}</span>
                  <span className="block truncate text-xs text-slate-400">
                    {u.email} · {u.role}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- When filter (presets + custom date range) ---------- */

function WhenFilter({
  rangeIdx,
  onRange,
  from,
  to,
  onFrom,
  onTo,
}: {
  rangeIdx: number;
  onRange: (i: number) => void;
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
}) {
  const custom = rangeIdx === CUSTOM_RANGE;
  return (
    <div className="flex flex-col gap-1 text-xs font-medium text-slate-600 dark:text-slate-300">
      <span className="flex items-center gap-1.5">
        <Calendar className="h-3.5 w-3.5 text-slate-400" />
        When
      </span>
      <div className="flex items-center gap-2">
        <select
          value={rangeIdx}
          onChange={(e) => onRange(Number(e.target.value))}
          className="field !py-2"
        >
          {TIME_RANGES.map((r, i) => (
            <option key={r.label} value={i}>
              {r.label}
            </option>
          ))}
        </select>
        {custom && (
          <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-2 py-1.5">
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => onFrom(e.target.value)}
              className="bg-transparent text-xs text-slate-700 outline-none"
              aria-label="From date"
            />
            <span className="text-slate-400">→</span>
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => onTo(e.target.value)}
              className="bg-transparent text-xs text-slate-700 outline-none"
              aria-label="To date"
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Study filter (search by id or name prefix) ---------- */

function StudyFilter({
  studies,
  loading,
  value,
  onChange,
}: {
  studies: { id: string; name: string }[];
  loading: boolean;
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return studies;
    return studies.filter(
      (s) => s.id.toLowerCase().startsWith(needle) || s.name.toLowerCase().startsWith(needle),
    );
  }, [studies, q]);

  const selected = studies.find((s) => s.id === value);
  const label = selected ? selected.name || selected.id : value || 'Any study';

  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Study</span>
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          window.setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className="field flex !w-56 items-center justify-between gap-2 !py-2 text-left"
      >
        <span className="flex min-w-0 items-center gap-2">
          <FileSpreadsheet className="h-4 w-4 shrink-0 text-slate-400" />
          <span className={`truncate ${value ? '' : 'text-slate-500'}`}>{label}</span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-72 rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search study name or id…"
              className="w-full text-sm outline-none"
            />
          </div>
          <div className="max-h-64 overflow-auto py-1">
            <button
              type="button"
              onClick={() => { onChange(''); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Any study
            </button>
            {loading && <p className="px-3 py-2 text-xs text-slate-400">Loading studies…</p>}
            {!loading && filtered.length === 0 && (
              <p className="px-3 py-2 text-xs text-slate-400">
                {q ? 'No study matches.' : 'No studies in recent activity.'}
              </p>
            )}
            {filtered.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => { onChange(s.id); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                <FileSpreadsheet className="h-4 w-4 shrink-0 text-primary-500" />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{s.name || s.id}</span>
                  {s.name && <span className="block truncate text-xs text-slate-400">{s.id}</span>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Avatar({ user }: { user: User }) {
  const initials = (user.name || user.email).slice(0, 2).toUpperCase();
  const tone = user.role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-primary-100 text-primary-700';
  return (
    <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-semibold ${tone}`}>
      {initials}
    </span>
  );
}

/** Close a popover when the user clicks/taps anywhere outside the returned ref. */
function useClickOutside<T extends HTMLElement>(onOutside: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onOutside();
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [onOutside]);
  return ref;
}
