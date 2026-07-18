import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Upload,
  Table2,
  Layers,
  Database,
  Columns3,
  Clock,
  CircleCheckBig,
  TriangleAlert,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useOverview } from '../hooks/queries';
import { useAuth } from '../context/AuthContext';
import { Card, CardBody } from '../components/ui/Card';
import { EmptyState, LoadingBlock } from '../components/ui/Feedback';
import AnimatedNumber from '../components/ui/AnimatedNumber';
import RadialProgress from '../components/ui/RadialProgress';
import PipelineStack3D from '../components/PipelineStack3D';
import { Stagger, StaggerItem } from '../components/ui/motion';
import type { StageBreakdown } from '../api/types';

const STAGE_META: Record<string, { label: string; color: string }> = {
  stage1: { label: 'Dict / Fuzzy', color: '#2986e2' },
  stage2: { label: 'Value / Ontology', color: '#6366f1' },
  stage3: { label: 'Semantic', color: '#a855f7' },
  stage4: { label: 'LLM', color: '#17ad84' },
  invalid: { label: 'Invalid', color: '#f43f5e' },
  unmapped: { label: 'Unmapped', color: '#94a3b8' },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading } = useOverview();

  const greeting = getGreeting();
  const firstName = (user?.name || user?.email || '').split(/[\s@]/)[0];
  const completedStudies = data?.studies?.filter((s) => s.review_progress >= 1).length ?? 0;

  return (
    <div className="space-y-7">
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="relative overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-primary-600 via-primary-600 to-primary-800 p-7 text-white shadow-card sm:p-9"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 right-24 h-56 w-56 rounded-full bg-accent-400/20 blur-3xl" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-primary-100">
              {greeting}{firstName ? `, ${firstName}` : ''} 👋
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
              Harmonization overview
            </h1>
            <p className="mt-2 max-w-md text-sm text-primary-100">
              A portfolio-wide snapshot of mapping coverage, confidence, and curation
              progress across all studies.
            </p>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <Link to="/upload" className="btn bg-white text-primary-700 hover:bg-primary-50">
                <Upload className="h-4 w-4" />
                Upload study
              </Link>
              <Link
                to="/review"
                className="btn border border-white/30 bg-white/10 text-white backdrop-blur hover:bg-white/20"
              >
                <Table2 className="h-4 w-4" />
                Review mappings
              </Link>
            </div>
          </div>

          {data && data.total_columns > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.15, duration: 0.4 }}
              className="shrink-0 rounded-2xl bg-white/10 p-4 backdrop-blur"
            >
              <RadialProgress
                value={data.review_progress}
                tone="#ffffff"
                track="rgba(255,255,255,0.25)"
                label="reviewed"
                dark
              />
            </motion.div>
          )}
        </div>
      </motion.div>

      {isLoading ? (
        <LoadingBlock label="Loading your workspace…" />
      ) : !data || data.total_studies === 0 ? (
        <EmptyState
          icon={<Upload className="h-6 w-6" />}
          title="No studies yet"
          description="Upload a clinical metadata file to start harmonizing and this dashboard will come alive."
          action={
            <Link to="/upload" className="btn-primary">
              <Upload className="h-4 w-4" />
              Upload your first study
            </Link>
          }
        />
      ) : (
        <>
          {/* KPI tiles */}
          <Stagger className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile
              icon={<Database className="h-5 w-5" />}
              tone="from-primary-500 to-primary-700"
              label="Studies"
              value={data.total_studies}
              hint={`${data.total_rows.toLocaleString()} rows total`}
            />
            <StatTile
              icon={<Columns3 className="h-5 w-5" />}
              tone="from-indigo-500 to-indigo-700"
              label="Columns mapped"
              value={data.mapped_columns}
              hint={`of ${data.total_columns.toLocaleString()} columns`}
            />
            <StatTile
              icon={<Clock className="h-5 w-5" />}
              tone="from-amber-500 to-orange-600"
              label="Pending review"
              value={data.pending_review}
              hint="awaiting a curator"
            />
            <StatTile
              icon={<CircleCheckBig className="h-5 w-5" />}
              tone="from-accent-500 to-accent-700"
              label="Completed studies"
              value={completedStudies}
              hint={`of ${data.total_studies} fully reviewed`}
            />
          </Stagger>

          {/* Analytics row: coverage + review split + stage mix */}
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardBody className="flex flex-col items-center justify-center gap-4 py-8">
                <RadialProgress
                  value={data.total_columns ? data.mapped_columns / data.total_columns : 0}
                  label="mapped"
                  size={150}
                  tone="#2986e2"
                />
                <div className="text-center">
                  <p className="text-sm font-semibold text-slate-800">Schema coverage</p>
                  <p className="mt-1 text-xs text-slate-500">
                    <AnimatedNumber value={data.mapped_columns} /> of{' '}
                    {data.total_columns.toLocaleString()} columns mapped
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardBody>
                <h3 className="mb-4 text-sm font-semibold text-slate-800">Review status</h3>
                <ReviewSplit
                  accepted={data.accepted}
                  rejected={data.rejected}
                  pending={data.pending_review}
                />
              </CardBody>
            </Card>

            <Card>
              <CardBody>
                <div className="mb-3 flex items-center gap-2">
                  <Layers className="h-4 w-4 text-slate-400" />
                  <h3 className="text-sm font-semibold text-slate-800">Stage mix</h3>
                </div>
                <StageBars stages={data.stage_breakdown} total={data.total_columns} />
              </CardBody>
            </Card>
          </div>

          {/* 3D pipeline explainer */}
          <Card>
            <CardBody>
              <div className="mb-1 flex items-center gap-2">
                <Layers className="h-4 w-4 text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-800">Harmonization pipeline</h3>
              </div>
              <p className="mb-2 text-xs text-slate-500">
                Every column cascades through four stages until it finds a match — the
                deeper it falls, the harder it was to resolve.
              </p>
              <PipelineStack3D stages={data.stage_breakdown} total={data.total_columns} />
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}

/* ---------- pieces ---------- */

function StatTile({
  icon,
  tone,
  label,
  value,
  hint,
  decimals = 0,
  suffix = '',
}: {
  icon: ReactNode;
  tone: string;
  label: string;
  value: number;
  hint?: string;
  decimals?: number;
  suffix?: string;
}) {
  return (
    <StaggerItem>
      <div className="stat-tile">
        <div className={`mb-3 grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br ${tone} text-white shadow-sm`}>
          {icon}
        </div>
        <div className="text-2xl font-bold tracking-tight text-slate-900">
          <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
        </div>
        <div className="mt-0.5 text-sm font-medium text-slate-600">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
      </div>
    </StaggerItem>
  );
}

function ReviewSplit({
  accepted,
  rejected,
  pending,
}: {
  accepted: number;
  rejected: number;
  pending: number;
}) {
  const total = accepted + rejected + pending || 1;
  const segments = [
    { label: 'Accepted', value: accepted, color: 'bg-emerald-500', icon: <CircleCheckBig className="h-3.5 w-3.5 text-emerald-600" /> },
    { label: 'Pending', value: pending, color: 'bg-amber-500', icon: <Clock className="h-3.5 w-3.5 text-amber-600" /> },
    { label: 'Rejected', value: rejected, color: 'bg-rose-500', icon: <TriangleAlert className="h-3.5 w-3.5 text-rose-600" /> },
  ];
  return (
    <div className="space-y-4">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100">
        {segments.map((s) => (
          <motion.div
            key={s.label}
            className={s.color}
            initial={{ width: 0 }}
            animate={{ width: `${(s.value / total) * 100}%` }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          />
        ))}
      </div>
      <div className="space-y-2">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-slate-600">
              {s.icon}
              {s.label}
            </span>
            <span className="font-semibold text-slate-900">
              <AnimatedNumber value={s.value} />
              <span className="ml-1 text-xs font-normal text-slate-400">
                ({Math.round((s.value / total) * 100)}%)
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StageBars({ stages, total }: { stages: StageBreakdown[]; total: number }) {
  if (!stages.length) {
    return <p className="py-6 text-center text-sm text-slate-400">No stage data yet.</p>;
  }
  const max = Math.max(...stages.map((s) => s.count), 1);
  return (
    <div className="space-y-3">
      {stages.map((s, i) => {
        const meta = STAGE_META[s.stage] ?? { label: s.stage, color: '#94a3b8' };
        const pct = (s.count / max) * 100;
        return (
          <div key={s.stage} className="flex items-center gap-3">
            <div className="w-24 shrink-0 truncate text-xs font-medium text-slate-600">{meta.label}</div>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: meta.color }}
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.7, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <div className="w-16 shrink-0 text-right text-xs text-slate-500">
              {total ? Math.round((s.count / total) * 100) : 0}%
            </div>
          </div>
        );
      })}
    </div>
  );
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}
