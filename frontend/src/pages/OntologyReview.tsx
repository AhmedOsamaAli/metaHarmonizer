import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Check, Loader2, Pencil, Search, X } from 'lucide-react';
import {
  acceptOntologyMapping,
  editOntologyMapping,
  getOntologyMappings,
  listStudies,
  rejectOntologyMapping,
  searchOntology,
} from '../api/client';
import ConfidenceBadge from '../components/ConfidenceBadge';
import StatusBadge from '../components/StatusBadge';
import type { OntologyMapping, OntologySearchResult, Study } from '../api/types';

interface EditState { id: number; term: string; ontId: string }

export default function OntologyReview() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(studyId ?? null);
  const [ontoMappings, setOntoMappings] = useState<OntologyMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<Record<number, boolean>>({});
  const [editState, setEditState] = useState<EditState | null>(null);

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<OntologySearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    listStudies().then(setStudies).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    getOntologyMappings(selectedId)
      .then(setOntoMappings)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedId]);

  const patch = (updated: OntologyMapping) =>
    setOntoMappings((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));

  const handleAccept = async (id: number) => {
    setBusy((b) => ({ ...b, [id]: true }));
    try { patch(await acceptOntologyMapping(id)); } catch { /* ignore */ }
    finally { setBusy((b) => ({ ...b, [id]: false })); }
  };

  const handleReject = async (id: number) => {
    setBusy((b) => ({ ...b, [id]: true }));
    try { patch(await rejectOntologyMapping(id)); } catch { /* ignore */ }
    finally { setBusy((b) => ({ ...b, [id]: false })); }
  };

  const handleEditSave = async () => {
    if (!editState || !editState.term.trim()) return;
    setBusy((b) => ({ ...b, [editState.id]: true }));
    try {
      patch(await editOntologyMapping(editState.id, editState.term.trim(), editState.ontId.trim()));
      setEditState(null);
    } catch { /* ignore */ }
    finally { setBusy((b) => ({ ...b, [editState!.id]: false })); }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try { setSearchResults(await searchOntology(searchQuery)); }
    catch { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const handleStudyChange = (id: string) => {
    setSelectedId(id);
    navigate(`/ontology/${id}`, { replace: true });
  };

  const applySearchResult = (r: OntologySearchResult) => {
    if (!editState) return;
    setEditState({ ...editState, term: r.term, ontId: r.ontology_id });
  };

  const grouped = ontoMappings.reduce<Record<string, OntologyMapping[]>>(
    (acc, m) => { (acc[m.field_name] ??= []).push(m); return acc; },
    {},
  );

  if (!selectedId) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Ontology Review</h2>
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

  return (
    <div className="space-y-6">
      {/* Edit Modal */}
      {editState && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm space-y-4">
            <h3 className="text-sm font-semibold text-gray-800">Override Ontology Term</h3>
            <div className="space-y-2">
              <label className="text-xs text-gray-500">Term name</label>
              <input
                autoFocus
                value={editState.term}
                onChange={(e) => setEditState({ ...editState, term: e.target.value })}
                onKeyDown={(e) => e.key === 'Enter' && handleEditSave()}
                placeholder="e.g. Male"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs text-gray-500">Ontology ID (optional — auto-resolved if blank)</label>
              <input
                value={editState.ontId}
                onChange={(e) => setEditState({ ...editState, ontId: e.target.value })}
                placeholder="e.g. NCIT:C20197"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
              />
            </div>
            <p className="text-xs text-gray-400">
              Or search on the right and click a result to auto-fill.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditState(null)}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                disabled={!editState.term.trim() || busy[editState.id]}
                onClick={handleEditSave}
                className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1"
              >
                {busy[editState.id] ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Ontology Mapping Review</h2>
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

      <div className="grid grid-cols-3 gap-6">
        {/* Main table */}
        <div className="col-span-2 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
            </div>
          ) : Object.keys(grouped).length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-400">
              No ontology mappings found for this study.
            </div>
          ) : (
            Object.entries(grouped).map(([field, items]) => (
              <div key={field} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700">
                    {field}
                    <span className="text-xs text-gray-400 ml-2">
                      {items.length} value{items.length !== 1 ? 's' : ''}
                    </span>
                  </h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-500 uppercase">
                      <th className="px-4 py-2 text-left">Raw Value</th>
                      <th className="px-4 py-2 text-left">Ontology Term</th>
                      <th className="px-4 py-2 text-left">Ontology ID</th>
                      <th className="px-4 py-2 text-left">Score</th>
                      <th className="px-4 py-2 text-left">Status</th>
                      <th className="px-4 py-2 text-left">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((om) => {
                      const isBusy = !!busy[om.id];
                      const displayTerm = om.curator_term ?? om.ontology_term;
                      const displayId = om.curator_id ?? om.ontology_id;
                      return (
                        <tr key={om.id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-mono text-xs">{om.raw_value}</td>
                          <td className="px-4 py-2 text-xs text-primary-700">
                            {displayTerm || '—'}
                            {om.curator_term && (
                              <span className="ml-1 text-[10px] text-amber-600">(edited)</span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-xs font-mono text-gray-600">{displayId || '—'}</td>
                          <td className="px-4 py-2"><ConfidenceBadge score={om.confidence_score} size="sm" /></td>
                          <td className="px-4 py-2"><StatusBadge status={om.status} /></td>
                          <td className="px-4 py-2">
                            {isBusy ? (
                              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                            ) : (
                              <div className="flex gap-1">
                                {om.status !== 'accepted' && (
                                  <button
                                    title="Accept"
                                    onClick={() => handleAccept(om.id)}
                                    className="p-1 rounded hover:bg-green-50 text-green-600"
                                  >
                                    <Check className="w-3.5 h-3.5" />
                                  </button>
                                )}
                                {om.status !== 'rejected' && (
                                  <button
                                    title="Reject"
                                    onClick={() => handleReject(om.id)}
                                    className="p-1 rounded hover:bg-red-50 text-red-500"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                )}
                                <button
                                  title="Edit term"
                                  onClick={() => setEditState({
                                    id: om.id,
                                    term: om.curator_term ?? om.ontology_term ?? '',
                                    ontId: om.curator_id ?? om.ontology_id ?? '',
                                  })}
                                  className="p-1 rounded hover:bg-blue-50 text-blue-500"
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </div>

        {/* Sidebar: Ontology search */}
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-1">Ontology Search</h3>
            {editState && (
              <p className="text-xs text-primary-600 mb-2">
                Click a result to fill the open edit form.
              </p>
            )}
            <div className="flex gap-2">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search NCIT, UBERON…"
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
              <button
                onClick={handleSearch}
                disabled={searching}
                className="p-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              </button>
            </div>

            {searchResults.length > 0 && (
              <ul className="mt-3 space-y-2 max-h-80 overflow-y-auto">
                {searchResults.map((r, i) => (
                  <li
                    key={i}
                    onClick={() => applySearchResult(r)}
                    className={`border border-gray-100 rounded-lg p-2 text-xs ${editState ? 'cursor-pointer hover:border-primary-300 hover:bg-primary-50' : ''}`}
                  >
                    <div className="font-medium text-gray-900">{r.term}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="font-mono text-gray-500">{r.ontology_id}</span>
                      <span className="text-gray-400">{r.ontology}</span>
                      <ConfidenceBadge score={r.score} size="sm" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
