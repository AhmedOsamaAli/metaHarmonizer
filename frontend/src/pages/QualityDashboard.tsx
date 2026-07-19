import { useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Cell as PieCell,
} from 'recharts';
import type { TooltipProps } from 'recharts';
import { ArrowRight, BarChart3, Columns3, Gauge, ListChecks, Layers, Wrench, CheckCircle2, AlertTriangle, XCircle, Circle, Orbit } from 'lucide-react';
import { getQualityMetrics, getStudyMappings } from '../api/client';
import { useStudies } from '../hooks/queries';
import PageHeader from '../components/ui/PageHeader';
import CompleteStudyButton from '../components/CompleteStudyButton';
import { Card, CardBody } from '../components/ui/Card';
import { LoadingBlock } from '../components/ui/Feedback';
import AnimatedNumber from '../components/ui/AnimatedNumber';
import Constellation from '../components/ui/Constellation';
import ConfidenceBadge from '../components/ConfidenceBadge';
import StageBadge from '../components/StageBadge';
import StudyPicker from '../components/StudyPicker';
import type { Mapping, QualityMetrics } from '../api/types';

const STAGE_COLORS: Record<string, string> = {
  // Clearly-distinct, colour-blind-safe hues: blue / orange / teal / pink.
  stage1: '#0072b2',
  stage2: '#e69f00',
  stage3: '#009e73',
  stage4: '#cc79a7',
  unmapped: '#94a3b8',
  invalid: '#f43f5e',
};
const STAGE_LABELS: Record<string, string> = {
  stage1: 'Dict / Fuzzy',
  stage2: 'Value / Ontology',
  stage3: 'Semantic',
  stage4: 'LLM',
  unmapped: 'Unmapped',
  invalid: 'Invalid',
};

export default function QualityDashboard() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();
  const { data: studies, isLoading: studiesLoading } = useStudies();

  const { data: metrics, isLoading } = useQuery({
    queryKey: ['quality', studyId],
    queryFn: () => getQualityMetrics(studyId!),
    enabled: !!studyId,
  });
  const { data: mappings } = useQuery({
    queryKey: ['mappings', studyId],
    queryFn: () => getStudyMappings(studyId!),
    enabled: !!studyId,
  });

  // ── Derived, widget-specific aggregates (computed once) ──────────────────
  const methodMix = useMemo(() => aggregateMethods(mappings ?? []), [mappings]);
  const confByStage = useMemo(() => aggregateConfidenceByStage(mappings ?? []), [mappings]);
  const needsReview = useMemo(() => pickNeedsReview(mappings ?? []), [mappings]);

  if (!studyId) {
    return (
      <StudyPicker
        title="Quality dashboard"
        description="Pick a study to view harmonization quality metrics."
        icon={<BarChart3 className="h-6 w-6" />}
        studies={studies}
        loading={studiesLoading}
        basePath="/quality"
      />
    );
  }

  if (isLoading || !metrics) {
    return <LoadingBlock label="Crunching metrics…" />;
  }

  const coverage = metrics.total_columns ? metrics.mapped_columns / metrics.total_columns : 0;
  const stagePie = metrics.stage_breakdown.map((s) => ({
    name: STAGE_LABELS[s.stage] ?? s.stage,
    value: s.count,
    color: STAGE_COLORS[s.stage] ?? '#94a3b8',
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Quality dashboard"
        description="How this study mapped — coverage, confidence, methods, and what still needs review."
        icon={<BarChart3 className="h-6 w-6" />}
        actions={studyId ? <CompleteStudyButton studyId={studyId} studyName={studies?.find((s) => s.id === studyId)?.name} size="sm" redirectTo="/quality" /> : undefined}
      />

      {/* Readiness banner + export-blocking checklist — the "is it ready?" answer */}
      <ReadinessBanner
        metrics={metrics}
        onReview={() => navigate(`/review/${studyId}?status=pending`)}
        onExport={() => navigate(`/export/${studyId}`)}
      />

      {/* KPI strip — each number is distinct and deep-links into a filtered review */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={<Columns3 className="h-4 w-4" />} label="Columns" value={metrics.total_columns} hint={`${metrics.unmapped_columns} unmapped`} onClick={() => navigate(`/review/${studyId}?status=all`)} />
        <Kpi icon={<Layers className="h-4 w-4" />} label="Coverage" value={coverage * 100} decimals={1} suffix="%" hint={`${metrics.mapped_columns} mapped`} tone="text-primary-600" onClick={() => navigate(`/review/${studyId}?status=all`)} />
        <Kpi icon={<Gauge className="h-4 w-4" />} label="Avg confidence" value={metrics.avg_confidence * 100} decimals={1} suffix="%" tone="text-accent-600" onClick={() => navigate(`/review/${studyId}?status=all`)} />
        <Kpi icon={<ListChecks className="h-4 w-4" />} label="Needs review" value={metrics.pending_review} hint={`${metrics.auto_accepted} accepted`} tone={metrics.pending_review ? 'text-amber-600' : 'text-emerald-600'} onClick={() => navigate(`/review/${studyId}?status=pending`)} />
      </div>

      {/* Harmonization constellation — the study's mappings as a living star map */}
      <Card>
        <CardBody>
          <div className="mb-1 flex items-center gap-2">
            <Orbit className="h-4 w-4 text-slate-400" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Harmonization constellation</h3>
          </div>
          <p className="mb-3 text-xs text-slate-500">
            Every column is a star — clustered by the stage that resolved it and brightened by confidence.
          </p>
          <Constellation
            items={(mappings ?? []).map((m) => ({ stage: m.stage ?? 'unmapped', confidence: m.confidence_score }))}
          />
        </CardBody>
      </Card>

      {/* cBioPortal-style widget grid — every chart shows a different thing */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Widget title="Confidence distribution" subtitle="How many columns at each score band">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={metrics.confidence_distribution} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke="#eef2f7" />
              <XAxis dataKey="bucket" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(41,134,226,0.06)' }} content={<ChartTooltip />} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {metrics.confidence_distribution.map((b, i) => (
                  <Cell key={i} fill={confColor(b.min_val)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Widget>

        <Widget title="Which stage solved it" subtitle="Pipeline stage that produced each match">
          <div className="flex items-center gap-4">
            <ResponsiveContainer width="55%" height={200}>
              <PieChart>
                <Pie data={stagePie} cx="50%" cy="50%" innerRadius={48} outerRadius={80} paddingAngle={2} dataKey="value">
                  {stagePie.map((s, i) => (
                    <PieCell key={i} fill={s.color} stroke="#fff" strokeWidth={2} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="flex-1 space-y-1.5">
              {stagePie.map((s) => (
                <li key={s.name} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                    {s.name}
                  </span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{s.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </Widget>

        <Widget title="Matching method" subtitle="Algorithm that won each column" icon={<Wrench className="h-4 w-4" />}>
          {methodMix.length ? (
            <BarList items={methodMix} />
          ) : (
            <Empty>No method data.</Empty>
          )}
        </Widget>

        <Widget title="Confidence by stage" subtitle="Average score each stage achieves">
          {confByStage.length ? (
            <div className="space-y-3 pt-1">
              {confByStage.map((c) => (
                <div key={c.stage} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 truncate text-xs font-medium text-slate-600 dark:text-slate-300">
                    {STAGE_LABELS[c.stage] ?? c.stage}
                  </span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div className="h-full rounded-full" style={{ width: `${c.avg * 100}%`, backgroundColor: STAGE_COLORS[c.stage] ?? '#94a3b8' }} />
                  </div>
                  <span className="w-10 shrink-0 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">
                    {(c.avg * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <Empty>No data.</Empty>
          )}
        </Widget>

        {/* Needs-review queue spans the remaining width */}
        <Card className="md:col-span-2 xl:col-span-1">
          <CardBody>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-200">
                  <ListChecks className="h-4 w-4 text-amber-500" />
                  Needs your review
                </h3>
                <p className="text-xs text-slate-500">Lowest-confidence pending columns</p>
              </div>
              <button
                onClick={() => navigate(`/review/${studyId}`)}
                className="flex items-center gap-1 text-xs font-semibold text-primary-600 hover:text-primary-700"
              >
                Open review
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
            {needsReview.length ? (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {needsReview.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs font-medium text-slate-800 dark:text-slate-200">{m.raw_column}</p>
                      <p className="truncate text-[11px] text-slate-400">
                        → {m.curator_field || m.matched_field || 'unmapped'}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <StageBadge stage={m.stage} />
                      <ConfidenceBadge score={m.confidence_score} size="sm" />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-col items-center gap-1 py-8 text-center">
                <span className="text-2xl">🎉</span>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">All caught up</p>
                <p className="text-xs text-slate-400">No columns are pending review.</p>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

/* ---------- aggregation helpers ---------- */

function aggregateMethods(mappings: Mapping[]): { label: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of mappings) {
    const key = m.method?.trim() || 'unmatched';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
}

function aggregateConfidenceByStage(mappings: Mapping[]): { stage: string; avg: number }[] {
  const sums = new Map<string, { total: number; n: number }>();
  for (const m of mappings) {
    if (m.confidence_score == null) continue;
    const stage = m.stage ?? 'unmapped';
    const cur = sums.get(stage) ?? { total: 0, n: 0 };
    cur.total += m.confidence_score;
    cur.n += 1;
    sums.set(stage, cur);
  }
  return [...sums.entries()]
    .map(([stage, { total, n }]) => ({ stage, avg: n ? total / n : 0 }))
    .sort((a, b) => a.stage.localeCompare(b.stage));
}

function pickNeedsReview(mappings: Mapping[]): Mapping[] {
  return mappings
    .filter((m) => m.status === 'pending')
    .sort((a, b) => (a.confidence_score ?? 0) - (b.confidence_score ?? 0))
    .slice(0, 7);
}

function confColor(minVal: number): string {
  // Confidence ramp: green (high) → amber → red (low).
  if (minVal >= 0.8) return '#16a34a'; // green-600
  if (minVal >= 0.6) return '#84cc16'; // lime-500
  if (minVal >= 0.4) return '#eab308'; // amber-500
  if (minVal >= 0.2) return '#f97316'; // orange-500
  return '#ef4444'; // red-500
}

/** Shared, on-brand tooltip for the recharts widgets. */
function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 px-2.5 py-1.5 text-xs shadow-card backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
      {label !== undefined && label !== '' && (
        <p className="mb-0.5 font-medium text-slate-500">{label}</p>
      )}
      {payload.map((p, i) => {
        const color = (p.payload as { color?: string } | undefined)?.color ?? p.color;
        const name = p.name === 'count' ? 'Columns' : p.name;
        return (
          <p key={i} className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
            {color && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />}
            <span>
              {name}: {p.value}
            </span>
          </p>
        );
      })}
    </div>
  );
}

/* ---------- small presentational pieces ---------- */

function ReadinessBanner({
  metrics,
  onReview,
  onExport,
}: {
  metrics: QualityMetrics;
  onReview: () => void;
  onExport: () => void;
}) {
  const accepted = metrics.auto_accepted;
  const pending = metrics.pending_review;
  const unmapped = metrics.unmapped_columns;

  // Each gate: done = satisfied; todo rows are what's blocking a clean export.
  const checks = [
    {
      label: 'At least one mapping confirmed',
      done: accepted > 0,
      todo: 'No columns are accepted yet — review and accept matches.',
      action: accepted > 0 ? undefined : onReview,
    },
    {
      label: 'No columns pending review',
      done: pending === 0,
      todo: `${pending} column${pending === 1 ? '' : 's'} still need a decision.`,
      action: pending === 0 ? undefined : onReview,
    },
    {
      label: 'Every column mapped to a field',
      done: unmapped === 0,
      todo: `${unmapped} column${unmapped === 1 ? '' : 's'} could not be mapped (they're dropped from export).`,
      action: undefined,
    },
  ];

  const blocking = accepted === 0;
  const needsWork = pending > 0;
  const state = blocking ? 'blocked' : needsWork ? 'review' : 'ready';

  const meta = {
    ready: { tone: 'border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10', icon: <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />, title: 'Ready to export', sub: 'All columns are reviewed and confirmed.' },
    review: { tone: 'border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10', icon: <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />, title: 'Needs review', sub: 'Some columns still need a curator decision.' },
    blocked: { tone: 'border-rose-200 bg-rose-50 dark:border-rose-500/30 dark:bg-rose-500/10', icon: <XCircle className="h-5 w-5 text-rose-600 dark:text-rose-400" />, title: 'Not ready', sub: 'Nothing is confirmed yet — start reviewing.' },
  }[state];

  return (
    <div className={`rounded-2xl border p-4 ${meta.tone}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {meta.icon}
          <div>
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">{meta.title}</h2>
            <p className="text-xs text-slate-600 dark:text-slate-300">{meta.sub}</p>
          </div>
        </div>
        {state === 'ready' ? (
          <button onClick={onExport} className="flex shrink-0 items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700">
            Go to export
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        ) : (
          <button onClick={onReview} className="flex shrink-0 items-center gap-1 rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700 dark:hover:bg-slate-700">
            Review pending
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <ul className="mt-3 space-y-1.5 border-t border-black/5 pt-3 dark:border-white/10">
        {checks.map((c) => (
          <li key={c.label} className="flex items-center gap-2 text-xs">
            {c.done ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
            ) : (
              <Circle className="h-4 w-4 shrink-0 text-slate-300" />
            )}
            <span className={c.done ? 'text-slate-500 line-through' : 'font-medium text-slate-700 dark:text-slate-300'}>
              {c.label}
            </span>
            {!c.done && (
              <span className="text-slate-500">— {c.todo}</span>
            )}
            {!c.done && c.action && (
              <button onClick={c.action} className="ml-auto shrink-0 font-semibold text-primary-600 hover:text-primary-700">
                Fix
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  hint,
  decimals = 0,
  suffix = '',
  tone,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  hint?: string;
  decimals?: number;
  suffix?: string;
  tone?: string;
  onClick?: () => void;
}) {
  return (
    <Card
      onClick={onClick}
      className={`p-4 ${onClick ? 'cursor-pointer transition hover:border-primary-300 hover:shadow-sm dark:hover:border-primary-500/50 dark:hover:bg-slate-800/60' : ''}`}
    >
      <div className="flex items-center gap-2 text-slate-400">
        {icon}
        <span className="text-xs font-medium text-slate-500">{label}</span>
      </div>
      <div className={`mt-1.5 text-2xl font-bold ${tone ?? 'text-slate-900 dark:text-slate-100'}`}>
        <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
      </div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
    </Card>
  );
}

function Widget({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardBody>
        <div className="mb-3 flex items-center gap-2">
          {icon && <span className="text-slate-400">{icon}</span>}
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</h3>
            {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
          </div>
        </div>
        {children}
      </CardBody>
    </Card>
  );
}

function BarList({ items }: { items: { label: string; count: number }[] }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="space-y-2.5 pt-1">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-xs font-medium text-slate-600 dark:text-slate-300" title={it.label}>
            {it.label}
          </span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-primary-500" style={{ width: `${(it.count / max) * 100}%` }} />
          </div>
          <span className="w-8 shrink-0 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">{it.count}</span>
        </div>
      ))}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-8 text-center text-sm text-slate-400">{children}</p>;
}
