
import { cn } from '../lib/cn';

interface Props {
  status: string;
}

const STATUS_STYLES: Record<string, { label: string; ring: string; dot: string }> = {
  // Pill + status dot; the label text is a redundant non-colour cue.
  accepted: { label: 'Accepted', ring: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/25', dot: 'bg-emerald-500' },
  rejected: { label: 'Rejected', ring: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/25', dot: 'bg-rose-500' },
  pending: { label: 'Pending', ring: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/25', dot: 'bg-amber-500' },
};

export default function StatusBadge({ status }: Props) {
  const info =
    STATUS_STYLES[status] ?? {
      label: status,
      ring: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-700/40 dark:text-slate-300 dark:ring-slate-500/25',
      dot: 'bg-slate-400',
    };
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        info.ring,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', info.dot)} />
      {info.label}
    </span>
  );
}
