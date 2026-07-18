import { useEffect, useMemo, useRef } from 'react';

/**
 * Harmonization constellation — a GPU-friendly <canvas> "star map" of a study's
 * column mappings. Each column is a star: clustered by the pipeline stage that
 * resolved it, coloured by that stage, and brightened/enlarged by confidence.
 * Faint links connect nearby stars within a cluster. It gently drifts + twinkles
 * (respecting prefers-reduced-motion). This is the study's real data, not decor.
 */

export type ConstellationItem = {
  stage: string;
  confidence: number | null;
};

const STAGE_COLOR: Record<string, [number, number, number]> = {
  stage1: [41, 134, 226], // blue
  stage2: [230, 159, 0], // orange
  stage3: [23, 173, 132], // teal
  stage4: [204, 121, 167], // pink
  unmapped: [148, 163, 184], // slate
  invalid: [244, 63, 94], // rose
};
const STAGE_ORDER = ['stage1', 'stage2', 'stage3', 'stage4', 'unmapped', 'invalid'];
const STAGE_LABEL: Record<string, string> = {
  stage1: 'Dict / Fuzzy',
  stage2: 'Value / Ontology',
  stage3: 'Semantic',
  stage4: 'LLM',
  unmapped: 'Unmapped',
  invalid: 'Invalid',
};

export default function Constellation({
  items,
  className,
  height = 260,
}: {
  items: ConstellationItem[];
  className?: string;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const legend = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      const s = it.stage || 'unmapped';
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return STAGE_ORDER.filter((s) => counts.has(s)).map((s) => ({
      stage: s,
      label: STAGE_LABEL[s] ?? s,
      count: counts.get(s) ?? 0,
      color: STAGE_COLOR[s] ?? STAGE_COLOR.unmapped,
    }));
  }, [items]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    type Star = {
      bx: number;
      by: number;
      r: number;
      phase: number;
      amp: number;
      color: [number, number, number];
    };
    let W = 0;
    let H = 0;
    let stars: Star[] = [];
    let links: Array<[number, number]> = [];

    const build = () => {
      W = wrap.clientWidth;
      H = height;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const present = STAGE_ORDER.filter((s) => items.some((it) => (it.stage || 'unmapped') === s));
      const n = present.length || 1;
      stars = [];
      const ranges: Array<{ start: number; end: number }> = [];

      present.forEach((s, i) => {
        const cx = ((i + 1) / (n + 1)) * W;
        const cy = H * 0.46;
        const group = items.filter((it) => (it.stage || 'unmapped') === s);
        const radius = Math.min(W / (n + 1), H) * 0.44;
        const start = stars.length;
        for (const it of group) {
          const a = Math.random() * Math.PI * 2;
          const rr = Math.sqrt(Math.random()) * radius;
          const conf = it.confidence == null ? 0.4 : Math.max(0, Math.min(1, it.confidence));
          stars.push({
            bx: cx + Math.cos(a) * rr,
            by: cy + Math.sin(a) * rr,
            r: 1.3 + conf * 2.6,
            phase: Math.random() * Math.PI * 2,
            amp: 1 + Math.random() * 2,
            color: STAGE_COLOR[s] ?? STAGE_COLOR.unmapped,
          });
        }
        ranges.push({ start, end: stars.length });
      });

      // Connect each star to its nearest same-cluster neighbour (bounded).
      links = [];
      for (const { start, end } of ranges) {
        for (let i = start; i < end; i++) {
          let best = -1;
          let bestD = Infinity;
          for (let j = start; j < end; j++) {
            if (j === i) continue;
            const dx = stars[i].bx - stars[j].bx;
            const dy = stars[i].by - stars[j].by;
            const d = dx * dx + dy * dy;
            if (d < bestD) {
              bestD = d;
              best = j;
            }
          }
          if (best > i && bestD < 62 * 62) links.push([i, best]);
        }
      }
    };

    build();

    const glow = stars.length > 350 ? 0 : 7;
    let raf = 0;
    let t = 0;
    const frame = () => {
      t += 0.016;
      ctx.clearRect(0, 0, W, H);

      ctx.lineWidth = 1;
      for (const [i, j] of links) {
        const a = stars[i];
        const b = stars[j];
        const ax = a.bx + Math.sin(t + a.phase) * a.amp;
        const ay = a.by + Math.cos(t + a.phase) * a.amp;
        const bx = b.bx + Math.sin(t + b.phase) * b.amp;
        const by = b.by + Math.cos(t + b.phase) * b.amp;
        const [r, g, bl] = a.color;
        ctx.strokeStyle = `rgba(${r},${g},${bl},0.10)`;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }

      for (const s of stars) {
        const x = s.bx + Math.sin(t + s.phase) * s.amp;
        const y = s.by + Math.cos(t + s.phase) * s.amp;
        const tw = 0.6 + 0.4 * Math.sin(t * 1.5 + s.phase);
        const [r, g, b] = s.color;
        ctx.beginPath();
        ctx.fillStyle = `rgba(${r},${g},${b},${0.82 * tw + 0.18})`;
        ctx.shadowBlur = glow;
        ctx.shadowColor = `rgba(${r},${g},${b},0.6)`;
        ctx.arc(x, y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    frame();

    const ro = new ResizeObserver(() => build());
    ro.observe(wrap);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [items, height]);

  return (
    <div
      ref={wrapRef}
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height,
        borderRadius: 16,
        overflow: 'hidden',
        background:
          'radial-gradient(120% 120% at 50% 25%, #123153 0%, #0d1e33 55%, #081019 100%)',
      }}
    >
      <canvas ref={canvasRef} style={{ display: 'block' }} />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-wrap justify-center gap-x-4 gap-y-1 px-3 pb-2">
        {legend.map((l) => (
          <span key={l.stage} className="flex items-center gap-1.5 text-[11px] font-medium text-white/70">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: `rgb(${l.color[0]},${l.color[1]},${l.color[2]})` }}
            />
            {l.label}
            <span className="text-white/50">{l.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
