import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type Tone = 'slate' | 'primary' | 'green' | 'amber' | 'rose' | 'indigo' | 'purple' | 'teal';

const TONE: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-700 dark:text-slate-300',
  primary: 'bg-primary-50 text-primary-700',
  green: 'bg-emerald-100 text-emerald-700',
  amber: 'bg-amber-100 text-amber-800',
  rose: 'bg-rose-100 text-rose-700',
  indigo: 'bg-indigo-100 text-indigo-700',
  purple: 'bg-purple-100 text-purple-700',
  teal: 'bg-accent-100 text-accent-700',
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
