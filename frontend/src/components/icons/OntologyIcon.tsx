import type { SVGProps } from 'react';

/**
 * Ontology knowledge-graph mark — a 6-node network (pentagon of nodes + a
 * central hub) used for the Ontology tab. Filled nodes + faded edges, all in
 * `currentColor`, so it adopts the nav's active / inactive colours like the
 * other lucide icons.
 */
export default function OntologyIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
      {...props}
    >
      <g stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.55">
        <path d="M12 3.2 L3.8 9.1" />
        <path d="M12 3.2 L20.2 9.1" />
        <path d="M12 3.2 L12 10.9" />
        <path d="M3.8 9.1 L6.6 20.2" />
        <path d="M20.2 9.1 L17.4 20.2" />
        <path d="M12 10.9 L6.6 20.2" />
        <path d="M12 10.9 L17.4 20.2" />
        <path d="M6.6 20.2 L17.4 20.2" />
      </g>
      <g fill="currentColor">
        <circle cx="12" cy="3.2" r="2.9" />
        <circle cx="3.8" cy="9.1" r="2.5" />
        <circle cx="20.2" cy="9.1" r="2.5" />
        <circle cx="12" cy="10.9" r="2" />
        <circle cx="6.6" cy="20.2" r="2.9" />
        <circle cx="17.4" cy="20.2" r="2.9" />
      </g>
    </svg>
  );
}
