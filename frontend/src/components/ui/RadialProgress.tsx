import AnimatedNumber from './AnimatedNumber';

/** Lightweight, dependency-free SVG progress ring with an animated stroke. */
export default function RadialProgress({
  value,
  size = 132,
  stroke = 12,
  label,
  sublabel,
  tone = '#2547e8',
  track = '#e2e8f0',
  dark = false,
  hideValue = false,
}: {
  /** 0..1 */
  value: number;
  size?: number;
  stroke?: number;
  label?: string;
  sublabel?: string;
  tone?: string;
  track?: string;
  /** Render center text light, for dark/gradient backgrounds. */
  dark?: boolean;
  /** Hide the center % text (for compact/inline rings). */
  hideValue?: boolean;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped);

  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.22,1,0.36,1)' }}
        />
      </svg>
      {!hideValue && (
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className={`text-2xl font-bold ${dark ? 'text-white' : 'text-slate-900 dark:text-slate-100'}`}>
              <AnimatedNumber value={clamped * 100} decimals={0} suffix="%" />
            </div>
            {label && (
              <div
                className={`text-[11px] font-medium uppercase tracking-wide ${dark ? 'text-white/70' : 'text-slate-400'}`}
              >
                {label}
              </div>
            )}
            {sublabel && (
              <div className={`text-[11px] ${dark ? 'text-white/60' : 'text-slate-400'}`}>{sublabel}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
