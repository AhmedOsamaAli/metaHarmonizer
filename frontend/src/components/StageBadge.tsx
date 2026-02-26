
interface Props {
  stage: string | null;
}

const STAGE_LABELS: Record<string, { label: string; color: string }> = {
  stage1: { label: 'S1 Dict/Fuzzy', color: 'bg-blue-100 text-blue-800' },
  stage2: { label: 'S2 Value/Ontology', color: 'bg-indigo-100 text-indigo-800' },
  stage3: { label: 'S3 Semantic', color: 'bg-purple-100 text-purple-800' },
  stage4: { label: 'S4 LLM', color: 'bg-orange-100 text-orange-800' },
  invalid: { label: 'Invalid', color: 'bg-red-100 text-red-700' },
  unmapped: { label: 'Unmapped', color: 'bg-gray-100 text-gray-600' },
};

export default function StageBadge({ stage }: Props) {
  const info = STAGE_LABELS[stage ?? 'unmapped'] ?? STAGE_LABELS.unmapped;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${info.color}`}>
      {info.label}
    </span>
  );
}
