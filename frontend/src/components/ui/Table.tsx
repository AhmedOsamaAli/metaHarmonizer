import type { HTMLAttributes } from 'react';
import { cn } from '../../lib/cn';

/**
 * Presentational table primitives — a consistent, professional table shell
 * (rounded card container, slate tokens, dense rows, sticky-capable header).
 * These carry styling only; sorting/selection logic stays in the page.
 */

export function TableFrame({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
      {...rest}
    />
  );
}

export function Table({ className, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return <table className={cn('w-full border-collapse text-sm', className)} {...rest} />;
}

export function THead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn('border-b border-slate-200 bg-slate-50/80 text-slate-500 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400', className)}
      {...rest}
    />
  );
}

export function TBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-slate-100 dark:divide-slate-800', className)} {...rest} />;
}

export function Th({ className, ...rest }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        'px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide',
        className,
      )}
      {...rest}
    />
  );
}

export function Td({ className, ...rest }: HTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-3 py-2.5 align-middle text-slate-700 dark:text-slate-300', className)} {...rest} />;
}
