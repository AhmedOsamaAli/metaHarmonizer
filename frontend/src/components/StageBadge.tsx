
import { cn } from '../lib/cn';

interface Props {
  stage: string | null;
}

const STAGE_LABELS: Record<string, { label: string; color: string }> = {
  // Clearly-distinct, colour-blind-safe categorical hues (blue / orange / teal /
  // pink — no blue→blue or blue→purple ramps). S1–S4 text is a redundant cue.
  stage1: { label: 'S1 Dict/Fuzzy', color: 'bg-blue-50 text-blue-700 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/25' },
  stage2: { label: 'S2 Value/Ontology', color: 'bg-orange-50 text-orange-700 ring-orange-600/20 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/25' },
  stage3: { label: 'S3 Semantic', color: 'bg-teal-50 text-teal-700 ring-teal-600/20 dark:bg-teal-500/10 dark:text-teal-300 dark:ring-teal-500/25' },
  stage4: { label: 'S4 LLM', color: 'bg-pink-50 text-pink-700 ring-pink-600/20 dark:bg-pink-500/10 dark:text-pink-300 dark:ring-pink-500/25' },
  invalid: { label: 'Invalid', color: 'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/25' },
  unmapped: { label: 'Unmapped', color: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-700/40 dark:text-slate-300 dark:ring-slate-500/25' },
};

export default function StageBadge({ stage }: Props) {
  const info = STAGE_LABELS[stage ?? 'unmapped'] ?? STAGE_LABELS.unmapped;
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        info.color,
      )}
    >
      {info.label}
    </span>
  );
}
