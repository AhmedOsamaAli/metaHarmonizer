import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Check,
  X,
  Pencil,
  ChevronDown,
  ChevronUp,
  Filter,
  ArrowUpDown,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import ConfidenceBadge from '../components/ConfidenceBadge';
import StageBadge from '../components/StageBadge';
import StatusBadge from '../components/StatusBadge';
import {
  listStudies,
  getStudyMappings,
  acceptMapping,
  rejectMapping,
  editMapping,
  batchUpdateMappings,
} from '../api/client';
import type { Mapping, Study } from '../api/types';

type SortKey = 'raw_column' | 'confidence_score' | 'stage' | 'status';
type FilterStage = 'all' | 'stage1' | 'stage2' | 'stage3' | 'stage4' | 'invalid' | 'unmapped';
type FilterStatus = 'all' | 'pending' | 'accepted' | 'rejected';

export default function MappingReview() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(studyId ?? null);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Filters — default to "pending" so curators see only actionable items
  const [filterStage, setFilterStage] = useState<FilterStage>('all');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('pending');
  const [sortKey, setSortKey] = useState<SortKey>('confidence_score');
  const [sortAsc, setSortAsc] = useState(false);

  // Edit modal
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editField, setEditField] = useState('');
  const [editNote, setEditNote] = useState('');

  // Toast notification
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 2500);
  };

  // Load studies list
  useEffect(() => {
    listStudies().then(setStudies).catch(console.error);
  }, []);

  // Load mappings when study selected
  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    getStudyMappings(selectedId)
      .then(setMappings)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedId]);

  // Study selector change
  const handleStudyChange = (id: string) => {
    setSelectedId(id);
    navigate(`/review/${id}`, { replace: true });
    setSelected(new Set());
    setExpandedRow(null);
  };

  // Filter + sort
  const filteredMappings = useMemo(() => {
    let result = [...mappings];
    if (filterStage !== 'all') result = result.filter((m) => m.stage === filterStage);
    if (filterStatus !== 'all') result = result.filter((m) => m.status === filterStatus);
    result.sort((a, b) => {
      let av: any = a[sortKey];
      let bv: any = b[sortKey];
      if (av === null) av = sortKey === 'confidence_score' ? -1 : '';
      if (bv === null) bv = sortKey === 'confidence_score' ? -1 : '';
      if (typeof av === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortAsc ? av - bv : bv - av;
    });
    return result;
  }, [mappings, filterStage, filterStatus, sortKey, sortAsc]);

  // Actions
  const updateMapping = useCallback(
    (updated: Mapping) => {
      setMappings((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
    },
    [],
  );

  const handleAccept = async (id: number) => {
    try {
      const m = await acceptMapping(id);
      updateMapping(m);
      showToast(`Accepted: ${m.raw_column} → ${m.curator_field || m.matched_field}`);
    } catch {
      showToast('Failed to accept mapping', 'error');
    }
  };
  const handleReject = async (id: number) => {
    try {
      const m = await rejectMapping(id);
      updateMapping(m);
      showToast(`Rejected: ${m.raw_column}`);
    } catch {
      showToast('Failed to reject mapping', 'error');
    }
  };
  const handleEditSubmit = async () => {
    if (editingId === null) return;
    try {
      const m = await editMapping(editingId, editField, editNote);
      updateMapping(m);
      showToast(`Edited: ${m.raw_column} → ${editField}`);
    } catch {
      showToast('Failed to edit mapping', 'error');
    }
    setEditingId(null);
    setEditField('');
    setEditNote('');
  };

  const handleBatch = async (action: 'accepted' | 'rejected') => {
    if (selected.size === 0) return;
    try {
      await batchUpdateMappings([...selected], action);
      // Reload
      if (selectedId) {
        const fresh = await getStudyMappings(selectedId);
        setMappings(fresh);
      }
      showToast(`${action === 'accepted' ? 'Accepted' : 'Rejected'} ${selected.size} mappings`);
    } catch {
      showToast('Batch update failed', 'error');
    }
    setSelected(new Set());
  };

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const toggleSelectAll = () => {
    if (selected.size === filteredMappings.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filteredMappings.map((m) => m.id)));
    }
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  // No study selected
  if (!selectedId) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Mapping Review</h2>
        {studies.length === 0 ? (
          <p className="text-gray-500">
            No studies uploaded yet.{' '}
            <button onClick={() => navigate('/')} className="text-primary-600 underline">
              Upload a file
            </button>{' '}
            to get started.
          </p>
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
                  {s.row_count} rows · {s.column_count} columns · {s.status}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toast notification */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-[100] flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all ${
            toast.type === 'success'
              ? 'bg-green-600 text-white'
              : 'bg-red-600 text-white'
          }`}
        >
          {toast.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <XCircle className="w-4 h-4" />
          )}
          {toast.message}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Schema Mapping Review</h2>
          <div className="flex items-center gap-2 mt-1">
            <select
              value={selectedId}
              onChange={(e) => handleStudyChange(e.target.value)}
              className="text-sm border border-gray-300 rounded-lg px-2 py-1"
            >
              {studies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Batch actions */}
        {selected.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">{selected.size} selected</span>
            <button
              onClick={() => handleBatch('accepted')}
              className="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-green-700"
            >
              Accept All
            </button>
            <button
              onClick={() => handleBatch('rejected')}
              className="bg-red-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-red-700"
            >
              Reject All
            </button>
          </div>
        )}
      </div>

      {/* Status Summary Tabs */}
      <div className="flex gap-2">
        {(['pending', 'accepted', 'rejected', 'all'] as FilterStatus[]).map((status) => {
          const count =
            status === 'all'
              ? mappings.length
              : mappings.filter((m) => m.status === status).length;
          const icons: Record<string, React.ReactNode> = {
            pending: <Clock className="w-3.5 h-3.5" />,
            accepted: <CheckCircle2 className="w-3.5 h-3.5" />,
            rejected: <XCircle className="w-3.5 h-3.5" />,
            all: null,
          };
          const colors: Record<string, string> = {
            pending: filterStatus === status ? 'bg-amber-100 text-amber-800 border-amber-300' : 'text-amber-700 hover:bg-amber-50',
            accepted: filterStatus === status ? 'bg-green-100 text-green-800 border-green-300' : 'text-green-700 hover:bg-green-50',
            rejected: filterStatus === status ? 'bg-red-100 text-red-800 border-red-300' : 'text-red-700 hover:bg-red-50',
            all: filterStatus === status ? 'bg-gray-200 text-gray-800 border-gray-400' : 'text-gray-600 hover:bg-gray-100',
          };
          return (
            <button
              key={status}
              onClick={() => {
                setFilterStatus(status);
                setSelected(new Set());
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${colors[status]}`}
            >
              {icons[status]}
              {status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)}
              <span className="bg-white/60 text-xs px-1.5 py-0.5 rounded-full font-semibold ml-1">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 bg-white border border-gray-200 rounded-xl p-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">Stage:</label>
          <select
            value={filterStage}
            onChange={(e) => setFilterStage(e.target.value as FilterStage)}
            className="text-sm border border-gray-200 rounded px-2 py-1"
          >
            <option value="all">All</option>
            <option value="stage1">S1 Dict/Fuzzy</option>
            <option value="stage2">S2 Value/Ontology</option>
            <option value="stage3">S3 Semantic</option>
            <option value="stage4">S4 LLM</option>
            <option value="invalid">Invalid</option>
            <option value="unmapped">Unmapped</option>
          </select>
        </div>
        <span className="text-xs text-gray-400 ml-auto">
          {filteredMappings.length} of {mappings.length} shown
        </span>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={selected.size === filteredMappings.length && filteredMappings.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded"
                  />
                </th>
                <SortableHeader label="Raw Column" sortKey="raw_column" current={sortKey} asc={sortAsc} onSort={toggleSort} />
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Matched Field
                </th>
                <SortableHeader label="Confidence" sortKey="confidence_score" current={sortKey} asc={sortAsc} onSort={toggleSort} />
                <SortableHeader label="Stage" sortKey="stage" current={sortKey} asc={sortAsc} onSort={toggleSort} />
                <SortableHeader label="Status" sortKey="status" current={sortKey} asc={sortAsc} onSort={toggleSort} />
                <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredMappings.map((m) => (
                <React.Fragment key={m.id}>
                  <tr
                    className={`hover:bg-gray-50 transition-colors ${
                      selected.has(m.id) ? 'bg-primary-50' : ''
                    }`}
                  >
                    <td className="px-3 py-2.5">
                      <input
                        type="checkbox"
                        checked={selected.has(m.id)}
                        onChange={() => toggleSelect(m.id)}
                        className="rounded"
                      />
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs font-medium text-gray-900">
                      {m.raw_column}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-primary-700">
                      {m.curator_field || m.matched_field || (
                        <span className="text-gray-400 italic">unmapped</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <ConfidenceBadge score={m.confidence_score} size="sm" />
                    </td>
                    <td className="px-3 py-2.5">
                      <StageBadge stage={m.stage} />
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={m.status} />
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1">
                        {m.status !== 'accepted' && (
                          <button
                            onClick={() => handleAccept(m.id)}
                            className="p-1 rounded hover:bg-green-100 text-green-600"
                            title="Accept"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                        {m.status !== 'rejected' && (
                          <button
                            onClick={() => handleReject(m.id)}
                            className="p-1 rounded hover:bg-red-100 text-red-600"
                            title="Reject"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setEditingId(m.id);
                            setEditField(m.curator_field || m.matched_field || '');
                          }}
                          className="p-1 rounded hover:bg-blue-100 text-blue-600"
                          title="Edit"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setExpandedRow(expandedRow === m.id ? null : m.id)}
                          className="p-1 rounded hover:bg-gray-200 text-gray-500"
                          title="Details"
                        >
                          {expandedRow === m.id ? (
                            <ChevronUp className="w-4 h-4" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>

                  {/* Expanded detail */}
                  {expandedRow === m.id && (
                    <tr>
                      <td colSpan={7} className="bg-gray-50 px-6 py-4">
                        <div className="grid grid-cols-2 gap-6 text-xs">
                          <div>
                            <h4 className="font-semibold text-gray-700 mb-2">
                              Top-5 Alternative Matches
                            </h4>
                            {m.alternatives.length > 0 ? (
                              <ul className="space-y-1">
                                {m.alternatives.map((alt, i) => (
                                  <li key={i} className="flex items-center gap-2">
                                    <span className="font-mono text-primary-700">
                                      {alt.field}
                                    </span>
                                    <ConfidenceBadge
                                      score={alt.score}
                                      size="sm"
                                    />
                                    <span className="text-gray-400">
                                      {alt.method}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-gray-400 italic">
                                No alternative matches
                              </p>
                            )}
                          </div>
                          <div>
                            <h4 className="font-semibold text-gray-700 mb-2">
                              Mapping Details
                            </h4>
                            <dl className="space-y-1">
                              <dt className="text-gray-500">Method</dt>
                              <dd className="text-gray-900">
                                {m.method || 'N/A'}
                              </dd>
                              <dt className="text-gray-500 mt-2">
                                Curator Note
                              </dt>
                              <dd className="text-gray-900">
                                {m.curator_note || '—'}
                              </dd>
                              {m.reviewed_at && (
                                <>
                                  <dt className="text-gray-500 mt-2">
                                    Reviewed
                                  </dt>
                                  <dd className="text-gray-900">
                                    {new Date(m.reviewed_at).toLocaleString()}
                                  </dd>
                                </>
                              )}
                            </dl>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>

          {filteredMappings.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              No mappings match the current filters.
            </div>
          )}
        </div>
      )}

      {/* Edit Modal */}
      {editingId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Edit Mapping</h3>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                New field name
              </label>
              <input
                value={editField}
                onChange={(e) => setEditField(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="e.g. sex, age_years, body_site"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Note (optional)
              </label>
              <textarea
                value={editNote}
                onChange={(e) => setEditNote(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                rows={2}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setEditingId(null);
                  setEditField('');
                  setEditNote('');
                }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleEditSubmit}
                disabled={!editField.trim()}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* Sortable header cell */
function SortableHeader({
  label,
  sortKey,
  current,
  asc,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  asc: boolean;
  onSort: (k: SortKey) => void;
}) {
  return (
    <th
      className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700"
      onClick={() => onSort(sortKey)}
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className="w-3 h-3" />
        {current === sortKey && (
          <span className="text-primary-600">{asc ? '↑' : '↓'}</span>
        )}
      </span>
    </th>
  );
}
