import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, Search } from 'lucide-react';
import {
  listStudies,
  getOntologyMappings,
  searchOntology,
} from '../api/client';
import ConfidenceBadge from '../components/ConfidenceBadge';
import StatusBadge from '../components/StatusBadge';
import type { OntologyMapping, OntologySearchResult, Study } from '../api/types';

export default function OntologyReview() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(studyId ?? null);
  const [ontoMappings, setOntoMappings] = useState<OntologyMapping[]>([]);
  const [loading, setLoading] = useState(false);

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

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const results = await searchOntology(searchQuery);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleStudyChange = (id: string) => {
    setSelectedId(id);
    navigate(`/ontology/${id}`, { replace: true });
  };

  // Group mappings by field
  const grouped = ontoMappings.reduce<Record<string, OntologyMapping[]>>(
    (acc, m) => {
      (acc[m.field_name] ??= []).push(m);
      return acc;
    },
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
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((om) => (
                      <tr key={om.id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono text-xs">{om.raw_value}</td>
                        <td className="px-4 py-2 text-xs text-primary-700">{om.ontology_term || '—'}</td>
                        <td className="px-4 py-2 text-xs font-mono text-gray-600">{om.ontology_id || '—'}</td>
                        <td className="px-4 py-2"><ConfidenceBadge score={om.confidence_score} size="sm" /></td>
                        <td className="px-4 py-2"><StatusBadge status={om.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </div>

        {/* Sidebar: Ontology search */}
        <div className="space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              Ontology Search
            </h3>
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
                  <li key={i} className="border border-gray-100 rounded-lg p-2 text-xs">
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
