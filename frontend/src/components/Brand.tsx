import { Link } from 'react-router-dom';
import { cn } from '../lib/cn';
import LogoMark, { ScatterMark } from './LogoMark';

/** Clickable identity lockup that returns the user home:
 *  scattered (raw metadata) → wordmark → ordered grid (harmonized). */
export default function Brand({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      aria-label="MetaHarmonizer — go to home"
      className={cn(
        'group flex items-center gap-2 rounded-xl px-1 py-1 transition hover:opacity-90',
        className,
      )}
    >
      <ScatterMark
        size={28}
        className="transition-transform duration-300 group-hover:-translate-x-0.5"
      />
      <span className="text-[17px] font-extrabold tracking-tight text-slate-900 transition-transform duration-300 group-hover:scale-[1.02] dark:text-slate-100">
        Meta<span className="brand-word">Harmonizer</span>
      </span>
      <LogoMark
        size={22}
        className="transition-transform duration-300 group-hover:scale-105"
      />
    </Link>
  );
}
