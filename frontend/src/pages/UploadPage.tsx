import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, AlertCircle, FileSpreadsheet, ArrowRight, Sparkles, Loader2, X, Table2 } from 'lucide-react';
import { toast } from 'sonner';
import FileUploader from '../components/FileUploader';
import ColumnTokenInput from '../components/ColumnTokenInput';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardBody } from '../components/ui/Card';
import Button from '../components/ui/Button';
import { uploadAndHarmonize, listEngineTargetSchemas, type HarmonizeMode } from '../api/client';
import { parseDelimitedPreview, type ParsedPreview } from '../lib/parseDelimited';
import { useJobs } from '../context/JobsContext';
import { useAuth } from '../context/AuthContext';
import { ApiError } from '../api/http';

type UploadState = 'idle' | 'uploading' | 'error';

const MODES: { value: HarmonizeMode; label: string; desc: string }[] = [
  { value: 'both', label: 'Both', desc: 'Schema mapping, then value → ontology resolution' },
  { value: 'schema', label: 'Schema only', desc: 'Map columns to curated fields; skip ontology' },
  { value: 'ontology', label: 'Ontology only', desc: 'Resolve cell values to ontology terms; skip schema mapping' },
];

const STAGES = [
  { stage: 'Stage 1', title: 'Dict / Fuzzy', desc: 'Dictionary lookup + RapidFuzz string matching against curated fields', tone: 'bg-blue-50 text-blue-700' },
  { stage: 'Stage 2', title: 'Value / Ontology', desc: 'Column value overlap analysis using ontology-aware matching', tone: 'bg-orange-50 text-orange-700' },
  { stage: 'Stage 3', title: 'Semantic', desc: 'Sentence-transformer embeddings (all-MiniLM-L6-v2) cosine similarity', tone: 'bg-teal-50 text-teal-700' },
  { stage: 'Stage 4', title: 'LLM', desc: 'Large-language-model fallback for columns unmatched by earlier stages', tone: 'bg-pink-50 text-pink-700' },
];

export default function UploadPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { track, cancel, jobs } = useJobs();
  const { isGuest } = useAuth();
  const [state, setState] = useState<UploadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  // Harmonization options (Sehyun follow-ups): mapper mode, target schema, and
  // an optional column allow-list that scopes the ontology pass.
  const [mode, setMode] = useState<HarmonizeMode>('both');
  const [targetSchema, setTargetSchema] = useState<string | undefined>(undefined);
  const [ontologyColumns, setOntologyColumns] = useState<string[]>([]);
  // Client-side preview of the selected file (header + first rows) so the
  // curator can sanity-check the upload and so column names can power the
  // ontology-column autocomplete.
  const [preview, setPreview] = useState<ParsedPreview | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const { data: engineSchemas } = useQuery({ queryKey: ['engine-target-schemas'], queryFn: listEngineTargetSchemas });
  // The study this upload session is following. Falls back (after a reload) to
  // the most recently-started job so the in-page view is restored too.
  const [currentStudyId, setCurrentStudyId] = useState<string | null>(null);

  const followed = useMemo(() => {
    if (currentStudyId) return jobs.find((j) => j.studyId === currentStudyId) ?? null;
    // After a refresh we lose currentStudyId; show the newest active job so the
    // upload page reflects in-flight work (the tray shows the rest).
    const active = jobs.filter((j) => j.phase === 'queued' || j.phase === 'processing');
    return active.length ? active[0] : null;
  }, [currentStudyId, jobs]);

  const handleFileSelected = (f: File) => {
    setFile(f);
    setError(null);
    setState('idle');
    setPreview(null);
    setShowAllRows(false);
    setOntologyColumns([]);
    // Parse a preview client-side (no upload yet) so the curator can review
    // the file and the column names can drive the ontology-column picker.
    parseDelimitedPreview(f)
      .then(setPreview)
      .catch(() => toast.error('Could not preview this file.'));
  };

  const handleUpload = async () => {
    if (!file) return;
    const cols = ontologyColumns.map((c) => c.trim()).filter(Boolean);
    setState('uploading');
    setError(null);
    try {
      const res = await uploadAndHarmonize(file, {
        mode,
        targetSchema,
        ontologyColumns: cols,
      });
      setCurrentStudyId(res.study_id);
      setState('idle');
      setFile(null);
      setPreview(null);
      qc.invalidateQueries({ queryKey: ['studies'] });
      // Hand off to the persistent tracker — it polls the backend, survives
      // refresh/tab-switch, and drives both this page and the docked tray.
      track({
        studyId: res.study_id,
        studyName: res.study_name,
        rowCount: res.row_count,
        columnCount: res.column_count,
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Upload failed';
      setError(msg);
      setState('error');
      toast.error(msg);
    }
  };

  const processing = followed && (followed.phase === 'queued' || followed.phase === 'processing');
  const done = followed && followed.phase === 'done';

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <PageHeader
        title="Upload study metadata"
        description="Upload a CSV/TSV file with clinical metadata. The pipeline maps columns to the curated reference schema automatically."
      />

      <div>
        <FileUploader
          onFileSelected={handleFileSelected}
          disabled={isGuest || state === 'uploading' || !!processing}
        />
        {isGuest && (
          <p className="mt-2 text-center text-xs text-slate-400">
            Preview only — sign in as a curator to upload and harmonize your own study.
          </p>
        )}
      </div>

      {/* File preview — header + first rows, parsed client-side before upload */}
      {file && preview && !processing && !done && (
        <Card>
          <CardBody className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Table2 className="h-4 w-4 text-slate-400" />
                <p className="text-sm font-semibold text-slate-900">Preview</p>
                <span className="text-xs text-slate-500">
                  {preview.columns.length} columns · showing {showAllRows ? preview.rows.length : Math.min(5, preview.rows.length)} of {preview.rows.length}
                  {preview.truncated ? '+ rows' : ' rows'}
                </span>
              </div>
              {preview.rows.length > 5 && (
                <button
                  type="button"
                  onClick={() => setShowAllRows((v) => !v)}
                  className="text-xs font-semibold text-primary-600 hover:text-primary-700"
                >
                  {showAllRows ? 'Show less' : `Show ${preview.rows.length} rows`}
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
              <table className="min-w-full border-collapse text-xs">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    <th className="border-b border-r border-slate-200 px-2 py-1.5 text-left font-semibold text-slate-400">#</th>
                    {preview.columns.map((c, i) => (
                      <th
                        key={`${c}-${i}`}
                        className="whitespace-nowrap border-b border-slate-200 px-3 py-1.5 text-left font-semibold text-slate-700"
                      >
                        {c || <span className="italic text-slate-400">(unnamed)</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(showAllRows ? preview.rows : preview.rows.slice(0, 5)).map((row, ri) => (
                    <tr key={ri} className="even:bg-slate-50/50">
                      <td className="border-r border-slate-200 px-2 py-1 text-slate-400">{ri + 1}</td>
                      {preview.columns.map((_, ci) => (
                        <td key={ci} className="whitespace-nowrap px-3 py-1 text-slate-700">
                          {row[ci] ?? ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.truncated && (
              <p className="text-xs text-slate-400">
                Large file — preview limited to the first rows. The full file is sent on run.
              </p>
            )}
          </CardBody>
        </Card>
      )}

      {/* Selected file → options + run */}
      {file && !processing && !done && (
        <>
          <Card>
            <CardBody className="space-y-5">
              <div>
                <p className="text-sm font-semibold text-slate-900">Run mode</p>
                <p className="text-xs text-slate-500">Choose which mappers run on this upload.</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {MODES.map((m) => (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => setMode(m.value)}
                      className={`rounded-xl border p-3 text-left transition ${
                        mode === m.value
                          ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                          : 'border-slate-200 hover:border-slate-300'
                      }`}
                    >
                      <span className="block text-sm font-semibold text-slate-900">{m.label}</span>
                      <span className="mt-0.5 block text-xs text-slate-500">{m.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {mode !== 'ontology' && (
                <div>
                  <label htmlFor="target-standard" className="text-sm font-semibold text-slate-900">
                    Target standard
                  </label>
                  <p className="text-xs text-slate-500">Which standard schema to map the columns into.</p>
                  <select
                    id="target-standard"
                    className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    value={targetSchema ?? ''}
                    onChange={(e) => setTargetSchema(e.target.value || undefined)}
                  >
                    <option value="">Default{engineSchemas?.length ? ` (${engineSchemas[0].label})` : ''}</option>
                    {engineSchemas?.map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.label} — {s.fields} fields
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {mode !== 'schema' && (
                <div>
                  <label htmlFor="onto-cols" className="text-sm font-semibold text-slate-900">
                    Ontology columns (optional)
                  </label>
                  <p className="text-xs text-slate-500">
                    Type to pick columns from your file to resolve against ontologies.
                    Leave blank to resolve all columns.
                  </p>
                  <ColumnTokenInput
                    id="onto-cols"
                    value={ontologyColumns}
                    onChange={setOntologyColumns}
                    options={preview?.columns ?? []}
                    placeholder={preview ? 'Start typing a column name…' : 'PRIMARY_SITE, SAMPLE_TYPE'}
                  />
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary-50 text-primary-600">
                  <FileSpreadsheet className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">{file.name}</p>
                  <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              </div>
              <Button
                onClick={handleUpload}
                loading={state === 'uploading'}
                icon={state === 'uploading' ? undefined : <Sparkles className="h-4 w-4" />}
              >
                {state === 'uploading' ? 'Uploading…' : 'Run harmonization'}
              </Button>
            </CardBody>
          </Card>
        </>
      )}

      {/* Live processing */}
      {processing && followed && (
        <Card className="border-primary-200">
          <CardBody className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <Loader2 className="mt-0.5 h-6 w-6 animate-spin text-primary-600" />
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">Harmonizing {followed.studyName}…</h3>
                  <p className="mt-0.5 text-sm text-slate-500">
                    {followed.message}
                    {followed.rowCount != null && (
                      <> · {followed.rowCount.toLocaleString()} rows</>
                    )}
                    {followed.columnCount != null && <> · {followed.columnCount} columns</>}
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="sm" className="text-rose-600 hover:bg-rose-50" icon={<X className="h-3.5 w-3.5" />} onClick={() => cancel(followed.studyId)}>
                Cancel
              </Button>
            </div>

            {/* Progress bar */}
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-primary-500 transition-all duration-500"
                style={{ width: `${Math.max(5, followed.pct)}%` }}
              />
            </div>

            {/* Stage pills */}
            <div className="flex flex-wrap gap-2">
              {[
                { key: 'parse', label: 'Read file' },
                { key: 'schema', label: 'Schema mapping' },
                { key: 'ontology', label: 'Ontology' },
                { key: 'done', label: 'Finalize' },
              ].map((s) => {
                const reached = followed.pct >= stagePct(s.key);
                const active = followed.stage === s.key;
                return (
                  <span
                    key={s.key}
                    className={`chip ${active ? 'bg-primary-600 text-white' : reached ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
                  >
                    {reached && !active ? <CheckCircle2 className="h-3 w-3" /> : null}
                    {s.label}
                  </span>
                );
              })}
            </div>

            <p className="text-xs text-slate-400">
              You can leave this page — progress keeps running and stays visible in the tray (bottom-right), even after a refresh.
            </p>
          </CardBody>
        </Card>
      )}

      {/* Success */}
      {done && followed && (
        <Card className="border-emerald-200 bg-emerald-50/40">
          <CardBody className="space-y-5">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-6 w-6 text-emerald-600" />
              <div>
                <h3 className="text-lg font-semibold text-emerald-900">Harmonization complete</h3>
                <p className="mt-0.5 text-sm text-emerald-700">{followed.message || 'Done.'}</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Stat label="Study" value={followed.studyName} />
              <Stat label="Rows" value={followed.rowCount != null ? followed.rowCount.toLocaleString() : '—'} />
              <Stat label="Columns" value={followed.columnCount != null ? followed.columnCount.toLocaleString() : '—'} />
            </div>

            <div className="flex flex-wrap gap-3">
              <Button onClick={() => navigate(`/review/${followed.studyId}`)} icon={<ArrowRight className="h-4 w-4" />}>
                Review mappings
              </Button>
              <Button variant="secondary" onClick={() => navigate(`/quality/${followed.studyId}`)}>
                View quality dashboard
              </Button>
              <Button variant="ghost" onClick={() => setCurrentStudyId(null)}>
                Upload another
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Error */}
      {state === 'error' && error && (
        <Card className="border-rose-200 bg-rose-50/50">
          <CardBody className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-rose-600" />
            <div>
              <h3 className="text-sm font-semibold text-rose-900">Harmonization failed</h3>
              <p className="mt-0.5 text-sm text-rose-700">{error}</p>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Pipeline explainer */}
      <Card>
        <CardBody>
          <h3 className="text-sm font-semibold text-slate-900">How the pipeline works</h3>
          <p className="mb-5 mt-1 text-xs text-slate-500">
            Powered by the MetaHarmonizer SchemaMapEngine — a 4-stage cascade.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {STAGES.map((s) => (
              <div key={s.stage} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                <span className={`chip ${s.tone}`}>{s.stage}</span>
                <p className="mt-2 text-sm font-semibold text-slate-900">{s.title}</p>
                <p className="mt-1 text-xs text-slate-500">{s.desc}</p>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-white p-3 text-center">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-0.5 truncate text-lg font-bold text-slate-900" title={value}>
        {value}
      </div>
    </div>
  );
}

/** Progress threshold (%) at which a stage is considered reached. */
function stagePct(key: string): number {
  switch (key) {
    case 'parse': return 10;
    case 'schema': return 30;
    case 'ontology': return 90;
    case 'done': return 100;
    default: return 100;
  }
}
