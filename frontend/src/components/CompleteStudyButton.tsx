import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { CircleCheck, AlertTriangle, X } from 'lucide-react';
import { toast } from 'sonner';
import { useCompleteStudy } from '../hooks/queries';
import { useJobs } from '../context/JobsContext';

interface Props {
  studyId: string;
  studyName?: string;
  /** Visual variant of the trigger button. */
  variant?: 'solid' | 'outline';
  size?: 'sm' | 'md';
  /** Where to go after completing. Defaults to staying put (no navigation). */
  redirectTo?: string;
  className?: string;
}

/**
 * "Complete study" trigger + confirmation dialog, reusable across pages.
 * Completing files a study away (kept for stats, removed from the work list);
 * the dialog makes the curator confirm because it can't be undone from the UI.
 */
export default function CompleteStudyButton({
  studyId,
  studyName,
  variant = 'outline',
  size = 'md',
  redirectTo,
  className = '',
}: Props) {
  const [open, setOpen] = useState(false);
  const complete = useCompleteStudy();
  const { dismiss } = useJobs();
  const navigate = useNavigate();

  const onConfirm = () => {
    complete.mutate(studyId, {
      onSuccess: () => {
        dismiss(studyId);
        setOpen(false);
        toast.success('Study completed');
        if (redirectTo) navigate(redirectTo);
      },
      onError: () => toast.error('Could not complete study'),
    });
  };

  const sizeCls = size === 'sm' ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm';
  const trigger =
    variant === 'solid'
      ? `inline-flex shrink-0 items-center gap-2 rounded-full bg-emerald-600 font-semibold text-white shadow-sm transition hover:bg-emerald-700 active:scale-95 disabled:opacity-60 ${sizeCls}`
      : `group/btn inline-flex shrink-0 items-center gap-2 rounded-full border border-emerald-200 bg-white font-semibold text-emerald-700 shadow-sm transition hover:border-emerald-300 hover:bg-emerald-50 hover:shadow active:scale-95 disabled:opacity-60 dark:border-emerald-500/30 dark:bg-slate-900 dark:text-emerald-300 dark:hover:bg-emerald-500/10 ${sizeCls}`;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={complete.isPending}
        title="Mark this study complete"
        className={`${trigger} ${className}`}
      >
        <CircleCheck className="h-4 w-4 transition group-hover/btn:scale-110" />
        Complete
      </button>

      {open && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-20"
          onClick={() => !complete.isPending && setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl dark:bg-slate-900"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-600">
                <AlertTriangle className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Complete this study?</h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Completing <span className="font-semibold">{studyName ?? 'this study'}</span> finalizes it and
                  removes it from your active work list. This <span className="font-semibold">cannot be undone</span> from here.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Download every export you need <span className="font-semibold">before</span> completing — once filed away it leaves your review queue.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                disabled={complete.isPending}
                className="ml-auto rounded-lg p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-50"
                aria-label="Cancel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setOpen(false)}
                disabled={complete.isPending}
                className="btn-secondary btn-sm disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={complete.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                <CircleCheck className="h-4 w-4" />
                {complete.isPending ? 'Completing…' : 'Complete study'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
