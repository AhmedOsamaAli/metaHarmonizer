import { useId } from 'react';
import { cn } from '../lib/cn';

/**
 * MetaHarmonizer logo mark — a rounded, softly-3D gradient tile carrying a
 * "many → one" harmonization glyph: three raw source fields converging into a
 * single curated field. Renders identically in light and dark mode (it carries
 * its own gradient), so it can sit on any surface.
 */
export default function LogoMark({
  className,
  size = 36,
}: {
  className?: string;
  size?: number;
}) {
  const uid = useId().replace(/[:]/g, '');
  const bg = `mhBg${uid}`;
  const node = `mhNode${uid}`;
  const sheen = `mhSheen${uid}`;

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
      <defs>
        <linearGradient id={bg} x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4f9ae8" />
          <stop offset="0.55" stopColor="#1f6fc4" />
          <stop offset="1" stopColor="#1b4f8f" />
        </linearGradient>
        <linearGradient id={node} x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#d3f8e9" />
        </linearGradient>
        <radialGradient id={sheen} cx="0.35" cy="0.28" r="0.85">
          <stop stopColor="#ffffff" stopOpacity="0.4" />
          <stop offset="0.6" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Tile with a soft top-left sheen for depth */}
      <rect x="1" y="1" width="38" height="38" rx="11.5" fill={`url(#${bg})`} />
      <rect x="1" y="1" width="38" height="38" rx="11.5" fill={`url(#${sheen})`} />
      <rect
        x="1.6"
        y="1.6"
        width="36.8"
        height="36.8"
        rx="10.9"
        stroke="#ffffff"
        strokeOpacity="0.18"
        strokeWidth="1.2"
      />

      {/* Converging links: three sources harmonize into one target */}
      <g stroke="#ffffff" strokeOpacity="0.9" strokeWidth="1.7" strokeLinecap="round" fill="none">
        <path d="M13 11.5 C 21 11.5, 20.5 20, 26.5 20" />
        <path d="M13 20 H 26.5" />
        <path d="M13 28.5 C 21 28.5, 20.5 20, 26.5 20" />
      </g>

      {/* Source nodes (raw fields) */}
      <g fill={`url(#${node})`}>
        <circle cx="12" cy="11.5" r="3" />
        <circle cx="12" cy="20" r="3" />
        <circle cx="12" cy="28.5" r="3" />
      </g>

      {/* Target node (harmonized field) with an accent ring */}
      <circle cx="28" cy="20" r="4.8" fill={`url(#${node})`} />
      <circle cx="28" cy="20" r="4.8" stroke="#17ad84" strokeOpacity="0.7" strokeWidth="1.4" />
      <circle cx="28" cy="20" r="1.9" fill="#1f6fc4" />
    </svg>
  );
}
