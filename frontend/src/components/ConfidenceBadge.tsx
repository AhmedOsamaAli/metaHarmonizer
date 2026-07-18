
import { cn } from '../lib/cn';

interface Props {
  score: number | null;
  size?: 'sm' | 'md';
}

/**
 * Colour-coded confidence badge (green→amber→red ramp; the High/Med/Low label
 * is a redundant non-colour cue):
 *  >=0.9 green (high), 0.5-0.9 amber (review), <0.5 red (low)
 */
export default function ConfidenceBadge({ score, size = 'md' }: Props) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-slate-400">—</span>;
  }

  let cls: string;
  let text: string;
  if (score >= 0.9) {
    cls = 'bg-emerald-50 text-emerald-700 ring-emerald-600/20';
    text = 'High';
  } else if (score >= 0.5) {
    cls = 'bg-amber-50 text-amber-700 ring-amber-600/20';
    text = 'Med';
  } else {
    cls = 'bg-rose-50 text-rose-700 ring-rose-600/20';
    text = 'Low';
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full font-medium ring-1 ring-inset',
        size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm',
        cls,
      )}
      title={`Confidence: ${(score * 100).toFixed(1)}%`}
    >
      {(score * 100).toFixed(0)}%
      <span className="text-[10px] opacity-70">{text}</span>
    </span>
  );
}
