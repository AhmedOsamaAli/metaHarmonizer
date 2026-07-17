import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { Upload } from 'lucide-react';
import type { Study } from '../api/types';
import Button from './ui/Button';
import { EmptyState, LoadingBlock } from './ui/Feedback';
import PageHeader from './ui/PageHeader';
import StudyListCard from './StudyListCard';

/** Landing list shown by review/quality/export pages when no study is selected. */
export default function StudyPicker({
  title,
  description,
  studies,
  loading,
  basePath,
}: {
  title: string;
  description?: string;
  studies: Study[] | undefined;
  loading: boolean;
  /** e.g. '/review' — navigates to `${basePath}/${study.id}`. */
  basePath: string;
}) {
  const navigate = useNavigate();

  // Cancelled studies are hidden from the pick list — you can't review/export
  // them, and they auto-delete after a week anyway.
  const visible = (studies ?? []).filter((s) => s.status !== 'cancelled');

  return (
    <div>
      <PageHeader title={title} description={description} />
      {loading ? (
        <LoadingBlock label="Loading studies…" />
      ) : !visible.length ? (
        <EmptyState
          icon={<Upload className="h-6 w-6" />}
          title="No studies yet"
          description="Upload a metadata file to start harmonizing."
          action={
            <Button icon={<Upload className="h-4 w-4" />} onClick={() => navigate('/upload')}>
              Upload a file
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <AnimatePresence>
            {visible.map((s) => (
              <StudyListCard key={s.id} study={s} basePath={basePath} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
