import { useId } from 'react';
import { cn } from '../lib/cn';

/**
 * MetaHarmonizer logo mark — a softly-3D gradient tile carrying a microscope
 * (the lab / science identity) with a small harmonized specimen on the stage.
 * It carries its own gradient, so it renders identically in light and dark mode.
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

      <g
        transform="translate(8,7.2)"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 22h18" />
        <path d="M6 18h8" />
        <path d="M14 22a7 7 0 1 0 0-14h-1" />
        <path d="M9 14h2" />
        <path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3" />
      </g>
      <path
        transform="translate(8,7.2)"
        d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z"
        fill={`url(#${node})`}
        stroke="#ffffff"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="18.6" cy="24.4" r="2" fill="#26d6a3" />
      <circle cx="14.4" cy="24.4" r="1.1" fill="#ffffff" fillOpacity="0.85" />
      <circle cx="22.8" cy="24.4" r="1.1" fill="#ffffff" fillOpacity="0.85" />
    </svg>
  );
}
