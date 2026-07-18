import { useRef, useState } from 'react';
import { motion, useMotionValue, useSpring } from 'framer-motion';
import type { StageBreakdown } from '../api/types';

/**
 * A 3D, tilt-reactive visualization of the four-stage harmonization pipeline.
 *
 * The stages are rendered as a descending staircase of glass "plates" in
 * perspective — raw columns enter at the top and animated packets flow down
 * through each stage until they settle as mapped terms. It doubles as a
 * plain-English explainer of how a study is harmonized. Built with CSS 3D
 * transforms + framer-motion (no extra deps) so it stays on the primary-blue /
 * teal palette.
 */

type StageDef = {
  key: string;
  label: string;
  color: string;
  glow: string;
};

// Canonical pipeline order (top → bottom), matching the engine's stage cascade.
const STAGES: StageDef[] = [
  { key: 'stage1', label: 'Dictionary / Fuzzy', color: '#2986e2', glow: 'rgba(41,134,226,0.5)' },
  { key: 'stage2', label: 'Value / Ontology', color: '#6366f1', glow: 'rgba(99,102,241,0.5)' },
  { key: 'stage3', label: 'Semantic', color: '#a855f7', glow: 'rgba(168,85,247,0.5)' },
  { key: 'stage4', label: 'LLM', color: '#17ad84', glow: 'rgba(23,173,132,0.5)' },
];

// Baseline isometric tilt applied to the whole scene.
const TILT = 'rotateX(56deg) rotateZ(-30deg)';
// Counter-rotation so labels lifted off a plate face the viewer.
const FACE = 'rotateZ(30deg) rotateX(-56deg)';
const STEP = 58; // vertical gap between plates, in the tilted plane

export default function PipelineStack3D({
  stages,
  total,
}: {
  stages: StageBreakdown[];
  total: number;
}) {
  const counts = new Map(stages.map((s) => [s.stage, s.count]));

  // Cursor-driven parallax tilt.
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const rotateX = useSpring(rx, { stiffness: 120, damping: 18 });
  const rotateY = useSpring(ry, { stiffness: 120, damping: 18 });
  const ref = useRef<HTMLDivElement>(null);
  const [hovering, setHovering] = useState(false);

  function onMove(e: React.MouseEvent) {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    ry.set(((e.clientX - r.left) / r.width - 0.5) * 12);
    rx.set(-((e.clientY - r.top) / r.height - 0.5) * 10);
  }
  function onLeave() {
    setHovering(false);
    rx.set(0);
    ry.set(0);
  }

  const maxCount = Math.max(...STAGES.map((s) => counts.get(s.key) ?? 0), 1);
  const span = (STAGES.length - 1) * STEP;

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={onLeave}
      className="relative mx-auto flex h-[360px] w-full max-w-md items-center justify-center"
      style={{ perspective: '1200px' }}
    >
      {/* parallax layer (mouse tilt) */}
      <motion.div style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }} className="relative">
        {/* static isometric tilt */}
        <div style={{ transform: TILT, transformStyle: 'preserve-3d' }} className="relative">
          {STAGES.map((stage, i) => {
            const count = counts.get(stage.key) ?? 0;
            const fill = count / maxCount;
            const y = i * STEP - span / 2; // cascade down the plane
            return (
              <motion.div
                key={stage.key}
                initial={{ opacity: 0, y: y - 24 }}
                animate={{ opacity: 1, y }}
                transition={{ delay: 0.1 + i * 0.12, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-2xl border"
                style={{
                  transformStyle: 'preserve-3d',
                  background: `linear-gradient(135deg, ${stage.color}26, ${stage.color}08)`,
                  borderColor: `${stage.color}66`,
                  boxShadow: `0 22px 44px -20px ${stage.glow}`,
                }}
              >
                {/* fill puddle: how many columns settled on this stage */}
                <div
                  className="absolute inset-2 rounded-xl transition-transform duration-700"
                  style={{
                    background: `radial-gradient(circle at 32% 32%, ${stage.color}, ${stage.color}55)`,
                    opacity: 0.2 + fill * 0.55,
                    transform: `scale(${0.32 + fill * 0.6})`,
                  }}
                />
                {/* label + count lifted toward viewer and un-tilted to face it */}
                <div
                  className="pointer-events-none absolute left-1/2 top-1/2 flex flex-col items-center"
                  style={{ transform: `translate(-50%,-50%) translateZ(30px) ${FACE}` }}
                >
                  <span
                    className="whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-white shadow"
                    style={{ backgroundColor: stage.color }}
                  >
                    {stage.label}
                  </span>
                  <span className="mt-1 text-xl font-bold tabular-nums text-slate-900 drop-shadow-sm">
                    {count}
                  </span>
                </div>
              </motion.div>
            );
          })}

          {/* flowing packets looping down through the stack */}
          {[0, 1, 2].map((n) => (
            <motion.div
              key={n}
              className="absolute left-1/2 top-1/2 h-3 w-3 rounded-full"
              style={{
                marginLeft: -6,
                marginTop: -6,
                background: 'radial-gradient(circle, #ffffff, #7eb8ef)',
                boxShadow: '0 0 12px 3px rgba(126,184,239,0.85)',
              }}
              animate={{ y: [-span / 2 - 20, span / 2 + 20], opacity: [0, 1, 1, 0] }}
              transition={{ duration: 2.8, delay: n * 0.9, repeat: Infinity, ease: 'easeIn' }}
            />
          ))}
        </div>
      </motion.div>

      {/* flow caption */}
      <div className="pointer-events-none absolute bottom-1 left-0 right-0 flex justify-center">
        <span className="rounded-full bg-white/75 px-3 py-1 text-[11px] font-medium text-slate-500 backdrop-blur">
          {total.toLocaleString()} columns flow top → bottom through {STAGES.length} stages
          {hovering ? ' · move to tilt' : ''}
        </span>
      </div>
    </div>
  );
}
