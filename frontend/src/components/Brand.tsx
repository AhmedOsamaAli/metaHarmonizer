import { Link } from 'react-router-dom';
import { cn } from '../lib/cn';

/** Clickable wordmark that always returns the user to the dashboard home. */
export default function Brand({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      aria-label="MetaHarmonizer — go to home"
      className={cn(
        'group flex items-center gap-2.5 rounded-xl px-1 py-1 transition hover:opacity-90',
        className,
      )}
    >
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 text-lg shadow-sm">
        🔬
      </span>
      <span className="flex items-baseline gap-2">
        <span className="text-[17px] font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          Meta<span className="text-primary-600">Harmonizer</span>
        </span>
        <span className="hidden rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 sm:inline">
          v0.1.0
        </span>
      </span>
    </Link>
  );
}
