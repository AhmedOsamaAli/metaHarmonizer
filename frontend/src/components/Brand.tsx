import { Link } from 'react-router-dom';
import { cn } from '../lib/cn';
import LogoMark from './LogoMark';

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
      <LogoMark
        size={36}
        className="shadow-sm transition-transform duration-300 group-hover:scale-105 group-hover:rotate-3"
      />
      <span className="text-[17px] font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
        Meta<span className="text-primary-600 dark:text-primary-400">Harmonizer</span>
      </span>
    </Link>
  );
}
