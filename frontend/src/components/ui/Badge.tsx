import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type Tone = 'slate' | 'primary' | 'green' | 'amber' | 'rose' | 'indigo' | 'purple' | 'teal';

const TONE: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-700 dark:bg-slate-700/50 dark:text-slate-300',
  primary: 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300',
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  rose: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
  indigo: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300',
  purple: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  teal: 'bg-accent-100 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300',
};

export default function Badge({
  tone = 'slate',
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn('chip', TONE[tone], className)}>{children}</span>;
}
