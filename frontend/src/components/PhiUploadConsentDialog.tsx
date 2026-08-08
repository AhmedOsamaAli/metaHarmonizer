import * as Dialog from '@radix-ui/react-dialog';
import { ShieldAlert, X } from 'lucide-react';
import Button from './ui/Button';

interface Props {
  open: boolean;
  remember: boolean;
  onRememberChange: (remember: boolean) => void;
  onAccept: () => void;
  onCancel: () => void;
}

export default function PhiUploadConsentDialog({
  open,
  remember,
  onRememberChange,
  onAccept,
  onCancel,
}: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/55 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-slate-200 bg-white p-6 shadow-2xl focus:outline-none dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-start gap-4">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
              <ShieldAlert className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-lg font-semibold text-slate-950 dark:text-white">
                Confirm de-identified data
              </Dialog.Title>
              <Dialog.Description className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Upload only de-identified study metadata. Do not include protected health information (PHI), names, contact details, medical record numbers, or other directly identifiable patient data.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Cancel upload" className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => onRememberChange(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-primary-600"
            />
            <span>Don’t show this confirmation again on this browser.</span>
          </label>

          <div className="mt-6 flex justify-end gap-3">
            <Button variant="secondary" onClick={onCancel}>Cancel</Button>
            <Button onClick={onAccept}>I understand, continue</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}