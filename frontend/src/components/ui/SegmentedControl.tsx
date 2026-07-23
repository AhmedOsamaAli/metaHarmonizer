import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export interface Segment<T extends string> {
  value: T;
  label: ReactNode;
  count?: number;
  icon?: ReactNode;
  /** Optional accent tone for the active count pill (defaults to primary). */
  tone?: 'primary' | 'emerald' | 'amber' | 'rose' | 'slate';
}

const COUNT_TONE: Record<NonNullable<Segment<string>['tone']>, string> = {
  primary: 'bg-primary-50 text-primary-700 dark:bg-primary-500/20 dark:text-primary-300',
  emerald: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300',
  amber: 'bg-amber-50 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300',
  rose: 'bg-rose-50 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300',
  slate: 'bg-slate-200/70 text-slate-600 dark:bg-slate-600/50 dark:text-slate-300',
};

const ACTIVE_TONE: Record<NonNullable<Segment<string>['tone']>, string> = {
  primary: 'bg-primary-600 text-white shadow-soft',
  emerald: 'bg-emerald-600 text-white shadow-soft',
  amber: 'bg-amber-600 text-white shadow-soft',
  rose: 'bg-rose-600 text-white shadow-soft',
  slate: 'bg-slate-600 text-white shadow-soft',
};

const INACTIVE_TONE: Record<NonNullable<Segment<string>['tone']>, string> = {
  primary: 'text-primary-600 hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-500/10',
  emerald: 'text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-500/10',
  amber: 'text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-500/10',
  rose: 'text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10',
  slate: 'text-slate-500 hover:bg-slate-200/60 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-700/50 dark:hover:text-slate-100',
};

/**
 * A clean segmented control (iOS/Linear style): a pill track with a raised
 * active segment. Used for status/scope toggles instead of ad-hoc coloured
 * buttons, for a calmer, more professional look.
 */
export default function SegmentedControl<T extends string>({
  value,
  onChange,
  segments,
  className,
  size = 'md',
}: {
  value: T;
  onChange: (value: T) => void;
  segments: Segment<T>[];
  className?: string;
  size?: 'sm' | 'md';
}) {
  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800/60',
        className,
      )}
    >
      {segments.map((s) => {
        const active = s.value === value;
        return (
          <button
            key={s.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(s.value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg font-medium transition',
              size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm',
              active ? ACTIVE_TONE[s.tone ?? 'primary'] : INACTIVE_TONE[s.tone ?? 'primary'],
            )}
          >
            {s.icon}
            {s.label}
            {s.count !== undefined && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-xs font-semibold',
                  active ? 'bg-white/25 text-white' : COUNT_TONE[s.tone ?? 'primary'],
                )}
              >
                {s.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
