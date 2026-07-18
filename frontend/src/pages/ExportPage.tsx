import { useParams, useNavigate } from 'react-router-dom';
import { Download, FileText, Database, FileJson, FolderArchive, Tags } from 'lucide-react';
import { getExportUrl, getLabeledExportUrl } from '../api/client';
import { useStudies } from '../hooks/queries';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardBody } from '../components/ui/Card';
import StudyPicker from '../components/StudyPicker';
import CompleteStudyButton from '../components/CompleteStudyButton';

export default function ExportPage() {
  const { studyId } = useParams<{ studyId: string }>();
  const { data: studies, isLoading } = useStudies();

  if (!studyId) {
    return (
      <StudyPicker
        title="Export harmonized data"
        description="Pick a study to download its harmonized outputs."
        studies={studies}
        loading={isLoading}
        basePath="/export"
      />
    );
  }

  const study = studies?.find((s) => s.id === studyId);

  const exports = [
    {
      icon: FileText,
      title: 'Harmonized CSV',
      desc: 'Data with columns renamed to curated schema fields and ontology IDs added.',
      format: 'harmonized' as const,
      tone: 'bg-emerald-50 text-emerald-600',
    },
    {
      icon: Database,
      title: 'cBioPortal Format',
      desc: 'Tab-separated file with cBioPortal clinical header lines, ready for the importer.',
      format: 'cbioportal' as const,
      tone: 'bg-primary-50 text-primary-600',
    },
    {
      icon: FolderArchive,
      title: 'cBioPortal Study Folder (ZIP)',
      desc: 'Full study folder (meta + clinical data files), ready to run through validateData.py.',
      format: 'cbioportal-study' as const,
      tone: 'bg-indigo-50 text-indigo-600',
    },
    {
      icon: FileJson,
      title: 'Mapping Report (JSON)',
      desc: 'Full audit trail of mapping decisions, curator edits, and metadata.',
      format: 'report' as const,
      tone: 'bg-purple-50 text-purple-600',
    },
  ];

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Export harmonized data"
      >
        {study && (
          <p className="mt-1 text-sm text-slate-500">
            {study.row_count} rows · {study.column_count} columns
          </p>
        )}
      </PageHeader>

      <div className="grid gap-4">
        {exports.map(({ icon: Icon, title, desc, format, tone }) => (
          <Card key={format} className="transition hover:shadow-card">
            <CardBody className="flex items-center justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className={`grid h-12 w-12 place-items-center rounded-2xl ${tone}`}>
                  <Icon className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
                  <p className="mt-1 max-w-md text-xs text-slate-500">{desc}</p>
                </div>
              </div>
              <a href={getExportUrl(studyId, format)} download className="btn-primary btn-sm shrink-0">
                <Download className="h-4 w-4" />
                Download
              </a>
            </CardBody>
          </Card>
        ))}

        {/* Labeled dataset (G9) — confirmed mappings as a training corpus */}
        <Card className="transition hover:shadow-card">
          <CardBody className="flex items-center justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-50 text-amber-600">
                <Tags className="h-6 w-6" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Labeled Dataset</h3>
                <p className="mt-1 max-w-md text-xs text-slate-500">
                  Curator-confirmed mappings only — a labeled corpus for engine training/evaluation.
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <a href={getLabeledExportUrl(studyId, 'csv')} download className="btn-secondary btn-sm">
                <Download className="h-4 w-4" />
                CSV
              </a>
              <a href={getLabeledExportUrl(studyId, 'jsonl')} download className="btn-secondary btn-sm">
                <Download className="h-4 w-4" />
                JSONL
              </a>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Study lifecycle action — completing files the study away */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
        <p className="text-xs text-slate-500">
          Completing files this study away and clears it from your work list.
          Studies left incomplete are auto-removed after a week.
        </p>
        <CompleteStudyButton studyId={studyId} studyName={study?.name} redirectTo="/export" />
      </div>
    </div>
  );
}
