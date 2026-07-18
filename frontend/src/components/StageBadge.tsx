
import { cn } from '../lib/cn';

interface Props {
  stage: string | null;
}

const STAGE_LABELS: Record<string, { label: string; color: string }> = {
  // Clearly-distinct, colour-blind-safe categorical hues (blue / orange / teal /
  // pink — no blue→blue or blue→purple ramps). S1–S4 text is a redundant cue.
  stage1: { label: 'S1 Dict/Fuzzy', color: 'bg-blue-50 text-blue-700 ring-blue-600/20' },
  stage2: { label: 'S2 Value/Ontology', color: 'bg-orange-50 text-orange-700 ring-orange-600/20' },
  stage3: { label: 'S3 Semantic', color: 'bg-teal-50 text-teal-700 ring-teal-600/20' },
  stage4: { label: 'S4 LLM', color: 'bg-pink-50 text-pink-700 ring-pink-600/20' },
  invalid: { label: 'Invalid', color: 'bg-red-50 text-red-700 ring-red-600/20' },
  unmapped: { label: 'Unmapped', color: 'bg-slate-100 text-slate-600 ring-slate-500/20' },
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
