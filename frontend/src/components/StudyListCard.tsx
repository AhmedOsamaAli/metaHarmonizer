import { useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { FileSpreadsheet, ArrowRight, CircleCheck, CheckCircle2, AlertTriangle, X } from 'lucide-react';
import { toast } from 'sonner';
import type { Study } from '../api/types';
import { Card } from './ui/Card';
import Badge from './ui/Badge';
import { useCompleteStudy } from '../hooks/queries';
import { useJobs } from '../context/JobsContext';

const CONFETTI = ['#22c55e', '#16a34a', '#86efac', '#4ade80', '#bbf7d0', '#34d399'];

/** A green burst of particles flying outward from the card centre. */
function Confetti() {
  return (
    <>
      {Array.from({ length: 18 }).map((_, i) => {
        const angle = (i / 18) * Math.PI * 2;
        const dist = 55 + Math.random() * 40;
        return (
          <motion.span
            key={i}
            className="absolute left-1/2 top-1/2 h-2 w-2 rounded-[2px]"
            style={{ backgroundColor: CONFETTI[i % CONFETTI.length] }}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{
              x: Math.cos(angle) * dist,
              y: Math.sin(angle) * dist,
              opacity: 0,
              scale: 0.3,
              rotate: Math.random() * 360,
            }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        );
      })}
    </>
  );
}

/** Study card used in the picker list, with a celebratory delete + a
 *  Checking "Complete" turns the card green, pops a confetti burst, then the
 *  card leaves the work list. The study is kept (its work still counts toward
 *  the dashboard) but filed away and dropped from the job-tracking tray.
 *  Studies left incomplete are auto-removed after a week. */
export default function StudyListCard({ study, basePath }: { study: Study; basePath: string }) {
  const navigate = useNavigate();
  const complete = useCompleteStudy();
  const { dismiss } = useJobs();
  const [celebrating, setCelebrating] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const onComplete = () => {
    if (celebrating) return;
    setConfirming(false);
    setCelebrating(true);
    // Let the celebration play, then mark complete (the exit animates as the
    // study leaves the work list) and clear it from the bottom job tray.
    window.setTimeout(() => {
      complete.mutate(study.id, {
        onSuccess: () => dismiss(study.id),
        onError: () => {
          setCelebrating(false);
          toast.error('Could not complete study');
        },
      });
    }, 850);
  };

  return (
    <motion.div
      layout
      exit={{ opacity: 0, scale: 0.6, transition: { duration: 0.35, ease: 'easeIn' } }}
    >
      <Card className="relative overflow-hidden transition hover:border-primary-300 hover:shadow-card dark:hover:border-primary-500/50">
        <AnimatePresence>
          {celebrating && (
            <motion.div
              className="absolute inset-0 z-10 grid place-items-center bg-emerald-500"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <Confetti />
              <motion.div
                initial={{ scale: 0, rotate: -30 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: 'spring', stiffness: 320, damping: 14 }}
                className="flex flex-col items-center gap-1 text-white"
              >
                <CheckCircle2 className="h-10 w-10" />
                <span className="text-sm font-semibold">Done!</span>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Main clickable area */}
        <button
          onClick={() => navigate(`${basePath}/${study.id}`)}
          className="group flex w-full items-center justify-between gap-3 p-4 text-left"
        >
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-500/15 dark:text-primary-300">
              <FileSpreadsheet className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold text-slate-900 dark:text-slate-100">{study.name}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{study.row_count ?? '—'} rows</span>·
                <span>{study.column_count ?? '—'} columns</span>
                {study.status && <Badge tone="slate">{study.status}</Badge>}
              </p>
              {study.upload_date && (
                <p className="mt-0.5 text-[11px] text-slate-400">Uploaded {timeAgo(study.upload_date)}</p>
              )}
            </div>
          </div>
          <ArrowRight className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-primary-500 dark:text-slate-600" />
        </button>

        {/* Action footer — completing files the study away (removed from the
            work list + job tray; the study itself is kept). */}
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-800/40">
          <p className="text-[11px] leading-tight text-slate-400">
            Completing files this study away and clears it from your work list.
            <br className="hidden sm:block" />
            Left incomplete, it auto-deletes in a week.
          </p>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={celebrating}
            title="Mark complete and remove this study"
            className="group/btn inline-flex shrink-0 items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-700 shadow-sm transition hover:border-emerald-300 hover:bg-emerald-50 hover:shadow active:scale-95 disabled:opacity-60 dark:border-emerald-500/30 dark:bg-slate-900 dark:text-emerald-300 dark:hover:bg-emerald-500/10"
          >
            <CircleCheck className="h-4 w-4 transition group-hover/btn:scale-110" />
            Complete
          </button>
        </div>
      </Card>

      {/* Confirm before finalizing */}
      {confirming && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-20"
          onClick={() => setConfirming(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-5 text-left shadow-xl dark:bg-slate-900"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300">
                <AlertTriangle className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Complete this study?</h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Completing <span className="font-semibold">{study.name}</span> finalizes it and
                  removes it from your active work list. This <span className="font-semibold">cannot be undone</span> from here.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Download every export you need <span className="font-semibold">before</span> completing.
                </p>
              </div>
              <button
                onClick={() => setConfirming(false)}
                className="ml-auto rounded-lg p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Cancel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirming(false)} className="btn-secondary btn-sm">
                Cancel
              </button>
              <button
                onClick={onComplete}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
              >
                <CircleCheck className="h-4 w-4" />
                Complete study
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </motion.div>
  );
}

/** Human-friendly relative time, e.g. "just now", "3m ago", "2h ago", "5d ago". */
function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return '';
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
