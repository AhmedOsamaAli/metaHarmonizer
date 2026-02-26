import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Download, FileText, Database, FileJson } from 'lucide-react';
import { listStudies, getExportUrl } from '../api/client';
import type { Study } from '../api/types';

export default function ExportPage() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(studyId ?? null);

  useEffect(() => {
    listStudies().then(setStudies).catch(console.error);
  }, []);

  const handleStudyChange = (id: string) => {
    setSelectedId(id);
    navigate(`/export/${id}`, { replace: true });
  };

  if (!selectedId) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Export</h2>
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

  const study = studies.find((s) => s.id === selectedId);

  const exports = [
    {
      icon: FileText,
      title: 'Harmonized CSV',
      desc: 'Download the data with columns renamed to curated schema fields and ontology IDs added.',
      format: 'harmonized' as const,
      color: 'text-green-600 bg-green-50',
    },
    {
      icon: Database,
      title: 'cBioPortal Format',
      desc: 'Tab-separated file with cBioPortal clinical data header lines, ready for the importer.',
      format: 'cbioportal' as const,
      color: 'text-blue-600 bg-blue-50',
    },
    {
      icon: FileJson,
      title: 'Mapping Report (JSON)',
      desc: 'Full audit trail including all mapping decisions, curator edits, and metadata.',
      format: 'report' as const,
      color: 'text-purple-600 bg-purple-50',
    },
  ];

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Export Harmonized Data</h2>
        <div className="flex items-center gap-2 mt-1">
          <select
            value={selectedId}
            onChange={(e) => handleStudyChange(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1"
          >
            {studies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {study && (
            <span className="text-xs text-gray-500">
              {study.row_count} rows · {study.column_count} columns
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-4">
        {exports.map(({ icon: Icon, title, desc, format, color }) => (
          <div
            key={format}
            className="bg-white border border-gray-200 rounded-xl p-6 flex items-center justify-between hover:shadow-sm transition-shadow"
          >
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-xl ${color}`}>
                <Icon className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
                <p className="text-xs text-gray-500 mt-1 max-w-md">{desc}</p>
              </div>
            </div>
            <a
              href={getExportUrl(selectedId, format)}
              download
              className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
            >
              <Download className="w-4 h-4" />
              Download
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
