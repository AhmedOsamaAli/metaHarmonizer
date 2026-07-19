import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, AlertCircle, FileSpreadsheet, ArrowRight, Sparkles, Table2, Upload, Maximize2, X } from 'lucide-react';
import { toast } from 'sonner';
import FileUploader from '../components/FileUploader';
import JobsPanel from '../components/JobsPanel';
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
  { stage: 'Stage 1', title: 'Dict / Fuzzy', desc: 'Dictionary lookup + RapidFuzz string matching against curated fields', tone: 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300' },
  { stage: 'Stage 2', title: 'Value / Ontology', desc: 'Column value overlap analysis using ontology-aware matching', tone: 'bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300' },
  { stage: 'Stage 3', title: 'Semantic', desc: 'Sentence-transformer embeddings (all-MiniLM-L6-v2) cosine similarity', tone: 'bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300' },
  { stage: 'Stage 4', title: 'LLM', desc: 'Large-language-model fallback for columns unmatched by earlier stages', tone: 'bg-pink-50 text-pink-700 dark:bg-pink-500/10 dark:text-pink-300' },
];

export default function UploadPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { track, jobs } = useJobs();
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
  const [previewOpen, setPreviewOpen] = useState(false);
  const { data: engineSchemas } = useQuery({ queryKey: ['engine-target-schemas'], queryFn: listEngineTargetSchemas });
  // The study this upload session is following. Falls back (after a reload) to
  // the most recently-started job so the in-page view is restored too.
  // The run whose "complete → review" card we surface inline once it finishes.
  // Harmonization is never required to stay in view: every run continues in the
  // docked tray (bottom-right), so the upload form below is never blocked while
  // a run is processing (or being cancelled). We only keep a handle to the
  // most-recently-started run so its success card can appear here.
  const [currentStudyId, setCurrentStudyId] = useState<string | null>(null);

  const followed = useMemo(
    () => (currentStudyId ? jobs.find((j) => j.studyId === currentStudyId) ?? null : null),
    [currentStudyId, jobs],
  );

  const handleFileSelected = (f: File) => {
    setFile(f);
    setError(null);
    setState('idle');
    setPreview(null);
    setPreviewOpen(false);
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
      // The run continues in the background (docked tray, bottom-right); the
      // form is immediately free for the next upload.
      toast.success(`Harmonizing ${res.study_name} — progress shows in the jobs tray.`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Upload failed';
      setError(msg);
      setState('error');
      toast.error(msg);
    }
  };

  const done = followed && followed.phase === 'done';

  useEffect(() => {
    if (!previewOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewOpen(false);
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [previewOpen]);

  return (
    <div className={`mx-auto space-y-7 ${file ? 'max-w-5xl' : 'max-w-3xl'}`}>
      <PageHeader
        title="Upload study metadata"
        description="Upload a CSV/TSV of clinical metadata to map columns to the curated reference schema."
        icon={<Upload className="h-6 w-6" />}
      />

      <div>
        <FileUploader
          onFileSelected={handleFileSelected}
          disabled={isGuest || state === 'uploading'}
          selectedName={file?.name ?? null}
        />
        {isGuest && (
          <p className="mt-2 text-center text-xs text-slate-400 dark:text-slate-500">
            Preview only — sign in as a curator to upload and harmonize your own study.
          </p>
        )}
      </div>

      {/* Live + failed harmonization runs (replaces the old floating tray). */}
      <JobsPanel />

      {/* Success — the most-recently-started run, once it finishes. Shown here,
          in place of the run controls (which clear on submit). */}
      {done && followed && !file && (
        <Card className="border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/30 dark:bg-emerald-500/10">
          <CardBody className="space-y-5">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              <div>
                <h3 className="text-lg font-semibold text-emerald-900 dark:text-emerald-200">Harmonization complete</h3>
                <p className="mt-0.5 text-sm text-emerald-700 dark:text-emerald-300">{followed.message || 'Done.'}</p>
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
        <Card className="border-rose-200 bg-rose-50/50 dark:border-rose-500/30 dark:bg-rose-500/10">
          <CardBody className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-rose-600 dark:text-rose-400" />
            <div>
              <h3 className="text-sm font-semibold text-rose-900 dark:text-rose-200">Harmonization failed</h3>
              <p className="mt-0.5 text-sm text-rose-700 dark:text-rose-300">{error}</p>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Selected file → run action on top, options + preview side by side */}
      {file && (
        <>
          <Card>
            <CardBody className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-500/15 dark:text-primary-300">
                  <FileSpreadsheet className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{file.name}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{(file.size / 1024).toFixed(1)} KB</p>
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

          <div className={preview ? 'grid gap-5 lg:grid-cols-2 lg:items-start' : ''}>
            <Card>
              <CardBody className="space-y-5">
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Run mode</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Choose which mappers run on this upload.</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {MODES.map((m) => (
                      <button
                        key={m.value}
                        type="button"
                        onClick={() => setMode(m.value)}
                        className={`rounded-xl border p-3 text-left transition ${
                          mode === m.value
                            ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200 dark:border-primary-500/60 dark:bg-primary-500/15 dark:ring-primary-500/30'
                            : 'border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600'
                        }`}
                      >
                        <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">{m.label}</span>
                        <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{m.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {mode !== 'ontology' && (
                  <div>
                    <label htmlFor="target-standard" className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      Target standard
                    </label>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Which standard schema to map the columns into.</p>
                    <select
                      id="target-standard"
                      className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
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
                    <label htmlFor="onto-cols" className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      Ontology columns (optional)
                    </label>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
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

            {preview && (
              <Card>
                <CardBody className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <Table2 className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
                      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Preview</p>
                      <span className="truncate text-xs text-slate-500 dark:text-slate-400">
                        {preview.columns.length} cols · {preview.rows.length}{preview.truncated ? '+' : ''} rows
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPreviewOpen(true)}
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      <Maximize2 className="h-3.5 w-3.5" />
                      Expand
                    </button>
                  </div>
                  <PreviewTable columns={preview.columns} rows={preview.rows.slice(0, 5)} heightClass="max-h-64" />
                  <button
                    type="button"
                    onClick={() => setPreviewOpen(true)}
                    className="w-full rounded-lg py-1 text-center text-xs font-semibold text-primary-600 transition hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-500/10"
                  >
                    {preview.rows.length > 5
                      ? `View all ${preview.rows.length}${preview.truncated ? '+' : ''} rows`
                      : 'Open full preview'}
                  </button>
                </CardBody>
              </Card>
            )}
          </div>
        </>
      )}

      {previewOpen && preview && file &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm animate-fade-in"
            onClick={() => setPreviewOpen(false)}
          >
            <div
              className="w-full max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-pop dark:border-slate-700 dark:bg-slate-900"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5 dark:border-slate-800">
                <div className="flex min-w-0 items-center gap-2">
                  <Table2 className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
                  <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{file.name}</p>
                  <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
                    {preview.columns.length} columns · {preview.rows.length}{preview.truncated ? '+' : ''} rows
                  </span>
                </div>
                <button
                  type="button"
                  aria-label="Close preview"
                  onClick={() => setPreviewOpen(false)}
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="p-4">
                <PreviewTable columns={preview.columns} rows={preview.rows} heightClass="max-h-[calc(100vh-9rem)]" />
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Pipeline explainer — only before a file is picked and while no run is
          being tracked, so the run status stays in view. */}
      {!file && !followed && (
        <Card>
          <CardBody>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">How the pipeline works</h3>
            <p className="mb-5 mt-1 text-xs text-slate-500 dark:text-slate-400">
              Powered by the MetaHarmonizer SchemaMapEngine — a 4-stage cascade.
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {STAGES.map((s) => (
                <div key={s.stage} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-800/40">
                  <span className={`chip ${s.tone}`}>{s.stage}</span>
                  <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{s.title}</p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{s.desc}</p>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-white p-3 text-center dark:border-emerald-500/30 dark:bg-slate-900">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-0.5 truncate text-lg font-bold text-slate-900 dark:text-slate-100" title={value}>
        {value}
      </div>
    </div>
  );
}

function PreviewTable({
  columns,
  rows,
  heightClass = 'max-h-80',
}: {
  columns: string[];
  rows: string[][];
  heightClass?: string;
}) {
  return (
    <div className={`${heightClass} overflow-auto overscroll-contain rounded-lg border border-slate-200 dark:border-slate-800`}>
      <table className="min-w-full border-collapse text-xs">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>
            <th className="border-b border-r border-slate-200 px-2 py-1.5 text-left font-semibold text-slate-400 dark:border-slate-700 dark:text-slate-500">#</th>
            {columns.map((c, i) => (
              <th
                key={`${c}-${i}`}
                className="whitespace-nowrap border-b border-slate-200 px-3 py-1.5 text-left font-semibold text-slate-700 dark:border-slate-700 dark:text-slate-300"
              >
                {c || <span className="italic text-slate-400 dark:text-slate-500">(unnamed)</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="even:bg-slate-50/50 dark:even:bg-slate-800/40">
              <td className="border-r border-slate-200 px-2 py-1 text-slate-400 dark:border-slate-700 dark:text-slate-500">{ri + 1}</td>
              {columns.map((_, ci) => (
                <td key={ci} className="whitespace-nowrap px-3 py-1 text-slate-700 dark:text-slate-300">
                  {row[ci] ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

