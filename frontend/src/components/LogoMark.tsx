import { cn } from '../lib/cn';

// Ordered 3×3 grid = the "harmonized" mark. Carries its own colors so it reads
// identically on light and dark surfaces.
const GRID_TONES = [
  '#2160c9', '#b9d5f5', '#b9d5f5',
  '#2160c9', '#5c9ae0', '#b9d5f5',
  '#2160c9', '#b9d5f5', '#2160c9',
];

/**
 * MetaHarmonizer logo mark — an ordered 3×3 grid of squares: scattered study
 * metadata brought into harmony. Theme-agnostic (its own colors).
 */
export default function LogoMark({
  className,
  size = 36,
  mono = false,
}: {
  className?: string;
  size?: number;
  /** Render every square in `currentColor` (e.g. white on a colored panel). */
  mono?: boolean;
}) {
  const s = 10;
  const g = 3;
  const o = 1.5;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      role="img"
      aria-hidden="true"
      className={cn('shrink-0', className)}
    >
      {GRID_TONES.map((tone, i) => (
        <rect
          key={i}
          x={o + (i % 3) * (s + g)}
          y={o + Math.floor(i / 3) * (s + g)}
          width={s}
          height={s}
          rx={1.4}
          fill={mono ? 'currentColor' : tone}
        />
      ))}
    </svg>
  );
}

const SCATTER_CELLS: [number, number, string][] = [
  [6, 26, '#b9d5f5'], [16, 10, '#2160c9'], [16, 40, '#b9d5f5'],
  [26, 20, '#dcebfb'], [26, 34, '#2160c9'], [36, 6, '#5c9ae0'],
  [36, 26, '#2160c9'], [46, 18, '#b9d5f5'], [44, 38, '#dcebfb'],
];

/**
 * The dispersed "raw metadata" mark — scattered squares that, in the auth
 * lockup, resolve into the ordered LogoMark grid. Theme-agnostic.
 */
export function ScatterMark({
  className,
  size = 44,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size * 0.86}
      viewBox="0 0 58 50"
      fill="none"
      role="img"
      aria-hidden="true"
      className={cn('shrink-0', className)}
    >
      {SCATTER_CELLS.map(([x, y, f], i) => (
        <rect key={i} x={x} y={y} width={8} height={8} rx={1.2} fill={f} />
      ))}
    </svg>
  );
}
