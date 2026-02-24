import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { listStudies, getQualityMetrics } from '../api/client';
import type { QualityMetrics, Study } from '../api/types';

const STAGE_COLORS: Record<string, string> = {
  stage1: '#3b82f6',
  stage2: '#6366f1',
  stage3: '#a855f7',
  stage4: '#f97316',
  unmapped: '#9ca3af',
};

const STATUS_COLORS = ['#22c55e', '#eab308', '#ef4444', '#9ca3af'];

export default function QualityDashboard() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(studyId ?? null);
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listStudies().then(setStudies).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    getQualityMetrics(selectedId)
      .then(setMetrics)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedId]);

  const handleStudyChange = (id: string) => {
    setSelectedId(id);
    navigate(`/quality/${id}`, { replace: true });
  };

  if (!selectedId) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Quality Dashboard</h2>
        {studies.length === 0 ? (
          <p className="text-gray-500">No studies uploaded yet.</p>
        ) : (
          <div className="grid gap-3">
            {studies.map((s) => (
              <button
                key={s.id}
                onClick={() => handleStudyChange(s.id)}
                className="bg-white border border-gray-200 rounded-xl p-4 text-left hover:border-primary-300 hover:shadow-sm transition-all"
              >
                <div className="font-medium text-gray-900">{s.name}</div>
                <div className="text-xs text-gray-500 mt-1">
                  {s.row_count} rows · {s.column_count} columns
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (loading || !metrics) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
      </div>
    );
  }

  const statusData = [
    { name: 'Accepted', value: metrics.auto_accepted },
    { name: 'Pending', value: metrics.pending_review },
    { name: 'Rejected', value: metrics.rejected },
    { name: 'New Field', value: metrics.new_field_suggestions },
  ];

  const pipelineCoverage =
    metrics.total_columns > 0
      ? ((metrics.mapped_columns / metrics.total_columns) * 100).toFixed(1)
      : '0';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Quality Dashboard</h2>
          <select
            value={selectedId}
            onChange={(e) => handleStudyChange(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1 mt-1"
          >
            {studies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard label="Total Columns" value={metrics.total_columns} />
        <KpiCard label="Mapped" value={metrics.mapped_columns} sub={`${pipelineCoverage}%`} color="text-green-700" />
        <KpiCard label="Unmapped" value={metrics.unmapped_columns} color="text-red-600" />
        <KpiCard label="Avg Confidence" value={`${(metrics.avg_confidence * 100).toFixed(1)}%`} />
        <KpiCard label="Pending Review" value={metrics.pending_review} color="text-yellow-700" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Confidence Distribution */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Confidence Score Distribution
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={metrics.confidence_distribution}>
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Stage Funnel */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Stage Breakdown
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart
              data={metrics.stage_breakdown}
              layout="vertical"
            >
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
              <YAxis dataKey="stage" type="category" tick={{ fontSize: 12 }} width={80} />
              <Tooltip
                formatter={(v: number, _: string, props: any) => [
                  `${v} (${props.payload.percentage}%)`,
                  'Columns',
                ]}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {metrics.stage_breakdown.map((entry) => (
                  <Cell
                    key={entry.stage}
                    fill={STAGE_COLORS[entry.stage] ?? '#9ca3af'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Status Pie */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Review Status
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={statusData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={90}
                paddingAngle={3}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
              >
                {statusData.map((_, i) => (
                  <Cell key={i} fill={STATUS_COLORS[i]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Progress */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Harmonization Progress
          </h3>
          <div className="space-y-4 mt-6">
            <ProgressBar
              label="Mapped"
              value={metrics.mapped_columns}
              max={metrics.total_columns}
              color="bg-green-500"
            />
            <ProgressBar
              label="Reviewed"
              value={metrics.auto_accepted + metrics.rejected}
              max={metrics.total_columns}
              color="bg-blue-500"
            />
            <ProgressBar
              label="Pending"
              value={metrics.pending_review}
              max={metrics.total_columns}
              color="bg-yellow-500"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${color ?? 'text-gray-900'}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function ProgressBar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
        <span>{label}</span>
        <span>
          {value}/{max} ({pct.toFixed(0)}%)
        </span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
