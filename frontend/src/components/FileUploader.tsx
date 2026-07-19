import React, { useCallback, useState } from 'react';
import { Upload } from 'lucide-react';

interface Props {
  onFileSelected: (file: File) => void;
  accept?: string;
  disabled?: boolean;
  /** Name of the currently-selected file, shown in the dropzone. The parent
   *  clears it (e.g. after "Run harmonization") to reset the dropzone. */
  selectedName?: string | null;
}

export default function FileUploader({ onFileSelected, accept = '.csv,.tsv,.txt', disabled, selectedName }: Props) {
  const [dragActive, setDragActive] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  return (
    <label
      className={`flex w-full cursor-pointer rounded-2xl border-2 border-dashed transition
        ${selectedName ? 'items-center gap-3 px-4 py-3' : 'h-36 flex-col items-center justify-center'}
        ${dragActive ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/10' : 'border-slate-300 bg-white hover:border-primary-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-primary-500 dark:hover:bg-slate-800'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      {selectedName ? (
        <>
          <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg transition ${dragActive ? 'bg-primary-100 text-primary-600 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-primary-50 text-primary-500 dark:bg-primary-500/15 dark:text-primary-300'}`}>
            <Upload className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-primary-700 dark:text-primary-300">{selectedName}</span>
            <span className="block text-xs text-slate-400 dark:text-slate-500">Click or drop to replace</span>
          </span>
        </>
      ) : (
        <>
          <span className={`grid h-11 w-11 place-items-center rounded-xl transition ${dragActive ? 'bg-primary-100 text-primary-600 dark:bg-primary-500/20 dark:text-primary-300' : 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'}`}>
            <Upload className="h-5 w-5" />
          </span>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            <span className="font-semibold text-primary-600 dark:text-primary-400">Click to upload</span> or drag and drop
          </p>
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">CSV, TSV, or TXT · up to 50&nbsp;MB</p>
        </>
      )}
      <input
        type="file"
        className="hidden"
        accept={accept}
        onChange={handleChange}
        disabled={disabled}
      />
    </label>
  );
}
