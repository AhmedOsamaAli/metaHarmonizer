import type { ComponentType } from 'react';
import { Activity, BarChart3, Download, Shield, Table2, Upload } from 'lucide-react';
import { cn } from '../lib/cn';
import OntologyIcon from './icons/OntologyIcon';

type IconComp = ComponentType<{ className?: string }>;

/** Small "scatter → grid" brand motif, mixed amongst the tab icons. */
function Motif({ className }: { className?: string }) {
  const scatter: [number, number][] = [[2, 18], [12, 6], [10, 30], [22, 22], [20, 36]];
  const grid: [number, number][] = [];
  for (let c = 0; c < 3; c++) {
    for (let r = 0; r < 3; r++) grid.push([46 + c * 8, 12 + r * 8]);
  }
  return (
    <svg viewBox="0 0 70 44" fill="currentColor" aria-hidden className={className}>
      {[...scatter, ...grid].map(([x, y], i) => (
        <rect key={i} x={x} y={y} width={5} height={5} rx={1} />
      ))}
    </svg>
  );
}

type Deco = { c: IconComp | 'motif'; top: number; left: number; rot: number; size: number; op: number };

// Hand-placed to look scattered (no rigid tiling), each tilted a little — a mix
// of the "scatter → grid" motif and the app's tab icons.
const ITEMS: Deco[] = [
  { c: 'motif', top: 24, left: 3, rot: -8, size: 66, op: 0.16 },
  { c: Upload, top: 30, left: 33, rot: 11, size: 30, op: 0.13 },
  { c: 'motif', top: 22, left: 63, rot: 6, size: 58, op: 0.15 },
  { c: Table2, top: 28, left: 88, rot: -13, size: 30, op: 0.12 },
  { c: OntologyIcon, top: 43, left: 9, rot: 14, size: 36, op: 0.14 },
  { c: 'motif', top: 49, left: 46, rot: -6, size: 70, op: 0.15 },
  { c: BarChart3, top: 35, left: 73, rot: 9, size: 30, op: 0.12 },
  { c: Download, top: 61, left: 90, rot: -15, size: 28, op: 0.13 },
  { c: 'motif', top: 71, left: 21, rot: 10, size: 60, op: 0.15 },
  { c: Shield, top: 75, left: 56, rot: -9, size: 28, op: 0.12 },
  { c: Activity, top: 87, left: 79, rot: 13, size: 30, op: 0.13 },
  { c: 'motif', top: 90, left: 6, rot: -11, size: 56, op: 0.15 },
];

// A calmer subset for the login/sign-up pages ("appears but less").
const SPARSE = new Set([0, 3, 5, 8, 10]);

/**
 * Faint background watermark: the brand's "scatter → grid" motif interleaved
 * with the app's tab icons, scattered at organic positions and tilted slightly.
 * Light mode leans on the system light-blue; dark mode a faint sky tint. Scope,
 * position + recolor via `className` (e.g. `fixed inset-0 -z-10`, `text-white`);
 * pass `sparse` for a lighter set on auth pages.
 */
export default function SquaresBackdrop({
  className,
  sparse = false,
}: {
  className?: string;
  sparse?: boolean;
}) {
  const items = sparse ? ITEMS.filter((_, i) => SPARSE.has(i)) : ITEMS;
  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none select-none overflow-hidden text-primary-400 dark:text-sky-300',
        className,
      )}
    >
      {items.map((d, i) => {
        const isMotif = d.c === 'motif';
        const Comp: IconComp = isMotif ? Motif : (d.c as IconComp);
        return (
          <span
            key={i}
            className="absolute"
            style={{
              top: `${d.top}%`,
              left: `${d.left}%`,
              width: d.size,
              height: isMotif ? Math.round(d.size * 0.63) : d.size,
              opacity: d.op * 1.7 * (sparse ? 0.7 : 1),
              transform: `rotate(${d.rot}deg)`,
            }}
          >
            <Comp className="h-full w-full" />
          </span>
        );
      })}
    </div>
  );
}
