import type { ReactNode } from 'react';

export default function PageHeader({
  title,
  description,
  actions,
  children,
  icon,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-start gap-3">
        {icon && (
          <span className="mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-500/15 dark:text-primary-300">
            {icon}
          </span>
        )}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">{description}</p>}
          {children}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
