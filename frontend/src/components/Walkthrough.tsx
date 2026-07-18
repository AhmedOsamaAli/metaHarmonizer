/*
 * Guided feature showcase.
 *
 * A self-contained slideshow of the features a curator actually uses, shown in
 * a centered, always-in-viewport modal with screenshot-style mock previews. It
 * does NOT drive or overlay the real pages — it's a fixed, professional
 * walkthrough that always fits on screen and never touches live data.
 *
 * It auto-opens once for a new curator (first login) and always for the
 * no-account guest preview. There is intentionally no persistent trigger in the top nav.
 */
import { motion } from 'framer-motion';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  CheckCheck,
  ChevronDown,
  Database,
  Download,
  FileJson,
  FileSpreadsheet,
  FolderArchive,
  Layers,
  Microscope,
  Pencil,
  Rocket,
  ShieldCheck,
  Sparkles,
  Table2,
  Tags,
  Upload,
  Wand2,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface TourValue {
  /** Open the showcase on demand. */
  start: () => void;
}

const TourContext = createContext<TourValue | null>(null);
const SEEN_KEY = 'mh_tour_seen_v4';

/* ------------------------------------------------------------------ */
/* Screenshot-style mock previews (pure presentation, no live data).  */
/* ------------------------------------------------------------------ */

/** A little "app window" frame so each preview reads like a screenshot. */
function Frame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-1.5 border-b border-slate-100 bg-slate-50 px-3 py-2">
        <span className="h-2 w-2 rounded-full bg-rose-300" />
        <span className="h-2 w-2 rounded-full bg-amber-300" />
        <span className="h-2 w-2 rounded-full bg-emerald-300" />
        <span className="ml-2 truncate text-[10px] font-medium text-slate-400">{label}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function PipelineMock() {
  const steps = [
    { icon: Upload, label: 'Upload' },
    { icon: Table2, label: 'Schema' },
    { icon: Microscope, label: 'Ontology' },
    { icon: Check, label: 'Review' },
    { icon: Download, label: 'Export' },
  ];
  return (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      {steps.map((s, i) => (
        <div key={s.label} className="flex items-center gap-1.5">
          <div className="flex flex-col items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <s.icon className="h-4 w-4 text-primary-600" />
            <span className="text-[10px] font-medium text-slate-600 dark:text-slate-300">{s.label}</span>
          </div>
          {i < steps.length - 1 && <ArrowRight className="h-3 w-3 text-slate-300" />}
        </div>
      ))}
    </div>
  );
}

function UploadMock() {
  return (
    <div className="space-y-3">
      <div className="rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 py-5 text-center">
        <Upload className="mx-auto h-6 w-6 text-slate-400" />
        <p className="mt-1 text-xs text-slate-500">Drop a study CSV / TSV</p>
      </div>
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">
          Target: GDC <ChevronDown className="h-3 w-3 text-slate-400" />
        </span>
        <span className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white">
          Run harmonization
        </span>
      </div>
    </div>
  );
}

function EngineMock() {
  const stages: Array<[string, string, string, string]> = [
    ['1', 'Dictionary + fuzzy', 'exact & close name matches', 'bg-blue-500'],
    ['2', 'Value / ontology', 'compares the actual values', 'bg-orange-500'],
    ['3', 'Semantic (AI)', 'meaning-based similarity', 'bg-teal-500'],
    ['4', 'LLM fallback', 'only the hardest leftovers', 'bg-pink-500'],
  ];
  return (
    <div className="space-y-1.5 text-xs">
      {stages.map(([n, label, desc, tone]) => (
        <div key={n} className="flex items-center gap-2">
          <span
            className={`grid h-5 w-5 shrink-0 place-items-center rounded-full ${tone} text-[10px] font-bold text-white`}
          >
            {n}
          </span>
          <div className="flex flex-1 items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5">
            <span className="font-semibold text-slate-800 dark:text-slate-200">{label}</span>
            <span className="truncate text-[10px] text-slate-400">{desc}</span>
          </div>
        </div>
      ))}
      <p className="pt-1 text-center text-[10px] leading-relaxed text-slate-400">
        Each column stops at the first confident stage — cheap matches first, AI only when needed.
      </p>
    </div>
  );
}

function BatchMock() {
  const group: Array<[string, string]> = [
    ['tumor_site', '100%'],
    ['Tumor Site', '98%'],
    ['site_of_tumor', '95%'],
  ];
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 text-xs">
      {/* Batch action bar */}
      <div className="flex items-center justify-between bg-primary-50 px-3 py-1.5">
        <span className="flex items-center gap-1.5 font-semibold text-primary-700">
          <CheckCheck className="h-3.5 w-3.5" />3 selected
        </span>
        <span className="flex items-center gap-1">
          <span className="rounded bg-primary-600 px-2 py-0.5 text-[10px] font-semibold text-white">Accept</span>
          <span className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-500">
            Reject
          </span>
        </span>
      </div>
      {/* Look-alike group, kept adjacent so it can be cleared together */}
      <div className="border-l-2 border-primary-400">
        {group.map(([col, conf]) => (
          <div
            key={col}
            className="grid grid-cols-[auto_1fr_auto] items-center gap-2 border-t border-slate-100 bg-primary-50/30 px-3 py-1.5"
          >
            <span className="grid h-4 w-4 place-items-center rounded bg-primary-600 text-white">
              <Check className="h-2.5 w-2.5" />
            </span>
            <span className="flex items-center gap-1 truncate text-slate-700 dark:text-slate-300">
              <code className="rounded bg-slate-100 px-1 text-[11px]">{col}</code>
              <ArrowRight className="h-3 w-3 shrink-0 text-slate-300" />primary_site
            </span>
            <span className="text-[10px] font-semibold text-emerald-600">{conf}</span>
          </div>
        ))}
      </div>
      {/* A single, ungrouped row still supports per-row edit */}
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2 border-t border-slate-100 px-3 py-1.5">
        <span className="h-4 w-4 rounded border border-slate-300" />
        <span className="flex items-center gap-1 truncate text-slate-700 dark:text-slate-300">
          <code className="rounded bg-slate-100 px-1 text-[11px]">MSI_status</code>
          <ArrowRight className="h-3 w-3 shrink-0 text-slate-300" />msi_status
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[10px] font-semibold text-emerald-600">96%</span>
          <span className="grid h-4 w-4 place-items-center rounded bg-slate-100 text-slate-500">
            <Pencil className="h-2.5 w-2.5" />
          </span>
        </span>
      </div>
    </div>
  );
}

function LearnMock() {
  return (
    <div className="space-y-2.5 text-xs">
      <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
        <span className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-300">
          <Wand2 className="h-3.5 w-3.5 text-primary-600" />Remember my decisions
        </span>
        <span className="flex h-4 w-7 items-center rounded-full bg-primary-600 px-0.5">
          <span className="ml-auto h-3 w-3 rounded-full bg-white" />
        </span>
      </div>
      <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">Your next study</p>
        <div className="flex items-center gap-1.5">
          <code className="rounded bg-white px-1 text-[11px] text-slate-700 dark:text-slate-300">tumor_site</code>
          <ArrowRight className="h-3 w-3 shrink-0 text-slate-300" />
          <span className="font-semibold text-slate-800 dark:text-slate-200">primary_site</span>
          <span className="ml-auto flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
            <Check className="h-2.5 w-2.5" />auto-filled
          </span>
        </div>
      </div>
      <p className="text-center text-[10px] leading-relaxed text-slate-400">
        Applied from your own history — an admin can promote a rule to the whole team.
      </p>
    </div>
  );
}

function OntologyMock() {
  const rows: Array<[string, string, string]> = [
    ['Hepatocellular Carcinoma', 'HCC', 'NCIT:C3099'],
    ['brain', 'Brain', 'UBERON:0000955'],
  ];
  return (
    <div className="space-y-2 text-xs">
      {rows.map(([raw, term, code]) => (
        <div
          key={raw}
          className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2"
        >
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-slate-500">{raw}</span>
            <ArrowRight className="h-3 w-3 shrink-0 text-slate-300" />
            <span className="font-semibold text-slate-800 dark:text-slate-200">{term}</span>
            <span className="shrink-0 rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
              {code}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <span className="grid h-5 w-5 place-items-center rounded bg-emerald-50 text-emerald-600">
              <Check className="h-3 w-3" />
            </span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
              Override
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function QualityMock() {
  return (
    <div className="flex items-center gap-4">
      <div
        className="relative grid h-20 w-20 shrink-0 place-items-center rounded-full"
        style={{ background: 'conic-gradient(#2563eb 66%, #e2e8f0 0)' }}
      >
        <div className="grid h-14 w-14 place-items-center rounded-full bg-white">
          <span className="text-sm font-bold text-slate-900 dark:text-slate-100">66%</span>
        </div>
      </div>
      <div className="flex-1 space-y-1.5 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-500">Columns mapped</span>
          <span className="font-semibold text-slate-800 dark:text-slate-200">13 / 24</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">Avg confidence</span>
          <span className="font-semibold text-slate-800 dark:text-slate-200">0.82</span>
        </div>
        <div className="flex gap-1 pt-1" title="Match stages">
          <span className="h-1.5 flex-[10] rounded-full bg-blue-500" />
          <span className="h-1.5 flex-[3] rounded-full bg-orange-500" />
          <span className="h-1.5 flex-[2] rounded-full bg-teal-500" />
        </div>
      </div>
    </div>
  );
}

function ExportMock() {
  const items = [
    { icon: FileSpreadsheet, label: 'Harmonized CSV', sub: 'renamed fields + ontology IDs' },
    { icon: Database, label: 'cBioPortal format', sub: 'TSV with clinical headers' },
    { icon: FolderArchive, label: 'cBioPortal study folder', sub: '.zip · meta + data files' },
    { icon: FileJson, label: 'Mapping report', sub: '.json · full audit trail' },
    { icon: Tags, label: 'Labeled dataset', sub: 'CSV / JSONL · training corpus' },
  ];
  return (
    <div className="space-y-1.5">
      {items.map((it) => (
        <div
          key={it.label}
          className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5"
        >
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary-50 text-primary-600">
            <it.icon className="h-3.5 w-3.5" />
          </span>
          <p className="flex-1 truncate text-xs font-semibold text-slate-800 dark:text-slate-200">{it.label}</p>
          <span className="shrink-0 text-[10px] text-slate-400">{it.sub}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Slide model.                                                       */
/* ------------------------------------------------------------------ */

interface Slide {
  icon: ReactNode;
  tone: string;
  title: string;
  /** One line: what the curator does here. */
  action: string;
  visual: ReactNode;
}

const FEATURE_SLIDES: Slide[] = [
  {
    icon: <Sparkles className="h-5 w-5" />,
    tone: 'bg-primary-50 text-primary-700',
    title: 'What MetaHarmonizer does',
    action: 'Turns a messy study spreadsheet into standardized, cBioPortal-ready data — in five steps.',
    visual: (
      <Frame label="workflow">
        <PipelineMock />
      </Frame>
    ),
  },
  {
    icon: <Upload className="h-5 w-5" />,
    tone: 'bg-teal-50 text-teal-700',
    title: 'Upload & harmonize',
    action: 'Drop a study, pick a target standard (GDC, cBioPortal, cMD…) — mapping runs automatically.',
    visual: (
      <Frame label="Upload">
        <UploadMock />
      </Frame>
    ),
  },
  {
    icon: <Layers className="h-5 w-5" />,
    tone: 'bg-indigo-50 text-indigo-700',
    title: 'How the engine maps',
    action: 'A 4-stage cascade — cheap dictionary matches first, AI embeddings and an LLM only for the hard ones.',
    visual: (
      <Frame label="Mapping engine">
        <EngineMock />
      </Frame>
    ),
  },
  {
    icon: <CheckCheck className="h-5 w-5" />,
    tone: 'bg-violet-50 text-violet-700',
    title: 'Review & accept in batches',
    action: 'Accept, reject, or edit any match — and since look-alike columns are grouped, clear a whole group at once.',
    visual: (
      <Frame label="Schema review">
        <BatchMock />
      </Frame>
    ),
  },
  {
    icon: <Wand2 className="h-5 w-5" />,
    tone: 'bg-amber-50 text-amber-700',
    title: 'It learns your decisions',
    action: 'Turn on "Remember my decisions" and the same columns are pre-filled on your next study — no repeating yourself.',
    visual: (
      <Frame label="Learned decisions">
        <LearnMock />
      </Frame>
    ),
  },
  {
    icon: <Microscope className="h-5 w-5" />,
    tone: 'bg-rose-50 text-rose-600',
    title: 'Confirm ontology codes',
    action: 'Each value resolves to a real code — NCIt for disease, UBERON for body site — to accept or override.',
    visual: (
      <Frame label="Ontology review">
        <OntologyMock />
      </Frame>
    ),
  },
  {
    icon: <BarChart3 className="h-5 w-5" />,
    tone: 'bg-sky-50 text-sky-700',
    title: 'Track quality',
    action: 'See coverage, confidence, and match-stage mix at a glance before you ship a study.',
    visual: (
      <Frame label="Quality">
        <QualityMock />
      </Frame>
    ),
  },
  {
    icon: <Download className="h-5 w-5" />,
    tone: 'bg-emerald-50 text-emerald-700',
    title: 'Export in any format',
    action: 'Harmonized CSV, cBioPortal files, a JSON audit report, or a labeled dataset to retrain the engine.',
    visual: (
      <Frame label="Export">
        <ExportMock />
      </Frame>
    ),
  },
];

/* ------------------------------------------------------------------ */
/* Provider + modal.                                                  */
/* ------------------------------------------------------------------ */

export function TourProvider({ children }: { children: ReactNode }) {
  const { user, isGuest, exitGuest } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);

  const start = useCallback(() => {
    setIdx(0);
    setOpen(true);
  }, []);

  const finish = useCallback(() => {
    setOpen(false);
    try {
      localStorage.setItem(SEEN_KEY, '1');
    } catch {
      /* ignore */
    }
    // A guest has no account to return to, so send them to sign in / sign up.
    if (isGuest) {
      exitGuest();
      navigate('/login');
    }
  }, [isGuest, exitGuest, navigate]);

  // Auto-open once for a newly-signed-in curator who hasn't seen it.
  useEffect(() => {
    if (!user) return;
    let seen = false;
    try {
      seen = localStorage.getItem(SEEN_KEY) === '1';
    } catch {
      seen = false;
    }
    if (!seen && user.role === 'curator') {
      setIdx(0);
      setOpen(true);
    }
  }, [user]);

  // The no-account preview always opens the showcase on entry.
  useEffect(() => {
    if (isGuest) {
      setIdx(0);
      setOpen(true);
    }
  }, [isGuest]);

  // Closing slide adapts to who's viewing.
  const closingSlide = useMemo<Slide>(() => {
    if (isGuest) {
      return {
        icon: <Rocket className="h-5 w-5" />,
        tone: 'bg-primary-50 text-primary-700',
        title: 'Ready to try it for real?',
        action: 'Create an account with any email to start curating — trusted-domain emails are approved instantly.',
        visual: (
          <Frame label="Get started">
            <div className="flex flex-col items-center gap-2 py-2 text-center">
              <ShieldCheck className="h-8 w-8 text-primary-600" />
              <p className="text-xs text-slate-500">
                You&apos;ve been exploring a read-only demo study. Sign in to work with your own data.
              </p>
            </div>
          </Frame>
        ),
      };
    }
    if (user?.role === 'admin') {
      return {
        icon: <ShieldCheck className="h-5 w-5" />,
        tone: 'bg-amber-50 text-amber-700',
        title: "You're an administrator",
        action: 'Approve pending accounts and admin requests from the Admin console — plus everything a curator can do.',
        visual: (
          <Frame label="Your access">
            <div className="flex flex-col items-center gap-2 py-2 text-center">
              <ShieldCheck className="h-8 w-8 text-amber-500" />
              <p className="text-xs text-slate-500">
                Admins manage team access; curators upload, review, confirm codes, and export.
              </p>
            </div>
          </Frame>
        ),
      };
    }
    return {
      icon: <Rocket className="h-5 w-5" />,
      tone: 'bg-emerald-50 text-emerald-700',
      title: "You're all set",
      action: 'Head to Upload to harmonize your first study — the workflow follows the steps above.',
      visual: (
        <Frame label="Get started">
          <div className="flex flex-col items-center gap-2 py-2 text-center">
            <Rocket className="h-8 w-8 text-emerald-500" />
            <p className="text-xs text-slate-500">Upload a study and MetaHarmonizer takes it from there.</p>
          </div>
        </Frame>
      ),
    };
  }, [isGuest, user?.role]);

  const slides = useMemo(() => [...FEATURE_SLIDES, closingSlide], [closingSlide]);
  const value = useMemo<TourValue>(() => ({ start }), [start]);

  // Arrow keys move between slides (← back, → forward); Escape closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setIdx((i) => Math.min(slides.length - 1, i + 1));
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setIdx((i) => Math.max(0, i - 1));
      } else if (e.key === 'Escape') {
        finish();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, slides.length, finish]);

  const safeIdx = Math.min(idx, slides.length - 1);
  const slide = slides[safeIdx];
  const isLast = safeIdx === slides.length - 1;
  const next = () => setIdx((i) => Math.min(slides.length - 1, i + 1));
  const back = () => setIdx((i) => Math.max(0, i - 1));

  return (
    <TourContext.Provider value={value}>
      {children}

      {/* Only shown while someone is actually in the app (guest or signed-in),
          so finishing as a guest — which clears both — closes it cleanly. */}
      {open && slide && (isGuest || !!user) && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="w-[min(34rem,100%)] rounded-3xl border border-slate-200 bg-white p-6 shadow-pop"
          >
            {/* Header: icon + title + the one-line curator action. */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${slide.tone}`}
                >
                  {slide.icon}
                </span>
                <div>
                  <h2 className="text-base font-bold leading-tight text-slate-900 dark:text-slate-100">{slide.title}</h2>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{slide.action}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={finish}
                aria-label="Close showcase"
                className="-mr-1 -mt-1 shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Screenshot-style preview (re-animates as slides change). */}
            <motion.div
              key={safeIdx}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.18 }}
              className="mt-4"
            >
              {slide.visual}
            </motion.div>

            {/* Footer: progress dots + navigation. */}
            <div className="mt-5 flex items-center justify-between">
              <div className="flex items-center gap-1">
                {slides.map((_, i) => (
                  <button
                    key={i}
                    type="button"
                    aria-label={`Go to slide ${i + 1}`}
                    onClick={() => setIdx(i)}
                    className={`h-1.5 rounded-full transition-all ${
                      i === safeIdx ? 'w-6 bg-primary-600' : 'w-2 bg-slate-200 hover:bg-slate-300'
                    }`}
                  />
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={back}
                  disabled={safeIdx === 0}
                  className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Back
                </button>
                {isLast ? (
                  <button
                    type="button"
                    onClick={finish}
                    className="flex items-center gap-1 rounded-lg bg-primary-600 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-primary-700"
                  >
                    {isGuest ? 'Sign in' : 'Done'}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={next}
                    className="flex items-center gap-1 rounded-lg bg-primary-600 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-primary-700"
                  >
                    Next
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </TourContext.Provider>
  );
}

export function useTour(): TourValue {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error('useTour must be used within a TourProvider');
  return ctx;
}
