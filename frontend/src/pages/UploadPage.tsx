import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import FileUploader from '../components/FileUploader';
import { uploadAndHarmonize } from '../api/client';
import type { HarmonizeResponse } from '../api/types';

type UploadState = 'idle' | 'uploading' | 'success' | 'error';

export default function UploadPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<UploadState>('idle');
  const [result, setResult] = useState<HarmonizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const handleFileSelected = (f: File) => {
    setFile(f);
    setError(null);
    setState('idle');
  };

  const handleUpload = async () => {
    if (!file) return;
    setState('uploading');
    setError(null);
    try {
      const res = await uploadAndHarmonize(file);
      setResult(res);
      setState('success');
    } catch (err: any) {
      setError(err.message || 'Upload failed');
      setState('error');
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      {/* Heading */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Upload Study Metadata</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload a CSV/TSV file with clinical metadata. The harmonization pipeline will
          automatically map columns to the curated reference schema.
        </p>
      </div>

      {/* Upload Zone */}
      <FileUploader
        onFileSelected={handleFileSelected}
        disabled={state === 'uploading'}
      />

      {/* File Info */}
      {file && state !== 'success' && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-900">{file.name}</p>
            <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
          <button
            onClick={handleUpload}
            disabled={state === 'uploading'}
            className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {state === 'uploading' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Harmonizing…
              </>
            ) : (
              'Run Harmonization'
            )}
          </button>
        </div>
      )}

      {/* Success */}
      {state === 'success' && result && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 space-y-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="w-6 h-6 text-green-600 mt-0.5" />
            <div>
              <h3 className="text-lg font-semibold text-green-900">
                Harmonization Complete
              </h3>
              <p className="text-sm text-green-700 mt-1">{result.message}</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mt-4">
            <Stat label="Study" value={result.study_name} />
            <Stat label="Rows" value={result.row_count.toLocaleString()} />
            <Stat label="Columns" value={result.column_count.toLocaleString()} />
          </div>

          <div className="flex gap-3 mt-4">
            <button
              onClick={() => navigate(`/review/${result.job_id}`)}
              className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
            >
              Review Mappings →
            </button>
            <button
              onClick={() => navigate(`/quality/${result.job_id}`)}
              className="bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              View Quality Dashboard
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {state === 'error' && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-red-900">Upload Failed</h3>
            <p className="text-sm text-red-700 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* How it works */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">
          How the Pipeline Works
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Powered by the real <span className="font-semibold">MetaHarmonizer SchemaMapEngine</span> — a 4-stage cascade from{' '}
          <a href="https://github.com/shbrief/MetaHarmonizer" className="text-primary-600 underline" target="_blank" rel="noreferrer">shbrief/MetaHarmonizer</a>.
        </p>
        <div className="grid grid-cols-4 gap-4">
          {[
            {
              stage: 'Stage 1',
              title: 'Dict / Fuzzy',
              desc: 'Dictionary lookup + RapidFuzz string matching against curated fields',
            },
            {
              stage: 'Stage 2',
              title: 'Value / Ontology',
              desc: 'Column value overlap analysis using ontology-aware matching',
            },
            {
              stage: 'Stage 3',
              title: 'Semantic',
              desc: 'Sentence-transformer embeddings (all-MiniLM-L6-v2) cosine similarity',
            },
            {
              stage: 'Stage 4',
              title: 'LLM',
              desc: 'Large language model fallback for columns unmatched by earlier stages',
            },
          ].map((s) => (
            <div key={s.stage} className="text-center">
              <div className="text-xs font-semibold text-primary-600 mb-1">
                {s.stage}
              </div>
              <div className="text-sm font-medium text-gray-900">{s.title}</div>
              <div className="text-xs text-gray-500 mt-1">{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-green-200 p-3 text-center">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-bold text-gray-900 mt-0.5">{value}</div>
    </div>
  );
}
