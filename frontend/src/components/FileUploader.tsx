import React, { useCallback, useState } from 'react';
import { Upload } from 'lucide-react';

interface Props {
  onFileSelected: (file: File) => void;
  accept?: string;
  disabled?: boolean;
}

export default function FileUploader({ onFileSelected, accept = '.csv,.tsv,.txt', disabled }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        setFileName(file.name);
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setFileName(file.name);
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  return (
    <label
      className={`flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl cursor-pointer transition-colors
        ${dragActive ? 'border-primary-500 bg-primary-50' : 'border-gray-300 bg-white hover:bg-gray-50'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      <Upload className="w-10 h-10 text-gray-400 mb-2" />
      {fileName ? (
        <p className="text-sm font-medium text-primary-700">{fileName}</p>
      ) : (
        <>
          <p className="text-sm text-gray-500">
            <span className="font-semibold text-primary-600">Click to upload</span> or drag
            and drop
          </p>
          <p className="text-xs text-gray-400 mt-1">CSV, TSV, or TXT</p>
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
