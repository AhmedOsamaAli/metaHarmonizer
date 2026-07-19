import type { ReactNode } from 'react';
import LogoMark, { ScatterMark } from './LogoMark';
import SquaresBackdrop from './SquaresBackdrop';
import ThemeToggle from './ThemeToggle';

/** Two-pane auth screen: brand/marketing on the left, form card on the right. */
export default function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <div className="absolute right-4 top-4 z-20">
        <ThemeToggle />
      </div>
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-primary-700 via-primary-600 to-primary-800 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <SquaresBackdrop sparse className="absolute inset-0 text-white dark:text-white" />
        <div className="relative flex items-center gap-3 text-white">
          <LogoMark size={40} mono className="text-white" />
          <span className="text-xl font-extrabold tracking-tight">MetaHarmonizer</span>
        </div>

        <div className="max-w-md text-white">
          <h2 className="text-3xl font-bold leading-tight">
            Harmonize clinical metadata with confidence.
          </h2>
          <p className="mt-4 text-primary-100">
            A curator-in-the-loop workspace for mapping study metadata to the curated
            reference schema and biomedical ontologies — auditable, reproducible, and fast.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-primary-50">
            {[
              '4-stage harmonization cascade with confidence scoring',
              'Ontology-aware value mapping (NCIt, UBERON & more)',
              'Append-only audit trail and role-based review',
            ].map((line) => (
              <li key={line} className="flex items-start gap-2.5">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-300" />
                {line}
              </li>
            ))}
          </ul>
        </div>

        <div aria-hidden />

        {/* Decorative grid */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-10 h-80 w-80 rounded-full bg-accent-400/20 blur-3xl" />
      </div>

      {/* Form panel */}
      <div className="relative flex items-center justify-center overflow-hidden bg-slate-50 px-4 py-12 dark:bg-slate-950 sm:px-8">
        <SquaresBackdrop sparse className="absolute inset-0" />
        <div className="relative w-full max-w-sm animate-fade-in">
          <div className="mb-8 flex items-center justify-center gap-3">
            <ScatterMark size={38} />
            <span className="text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
              Meta<span className="brand-word">Harmonizer</span>
            </span>
            <LogoMark size={24} />
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}

          <div className="mt-7">{children}</div>

          {footer && <div className="mt-6 text-center text-sm text-slate-500">{footer}</div>}
        </div>
      </div>
    </div>
  );
}
