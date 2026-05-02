import React, { useCallback, useState } from 'react';
import { Upload } from 'lucide-react';

interface Props {
  onFileSelected: (file: File | null ) => void;
  accept?: string;
  disabled?: boolean;
}

export default function FileUploader({ onFileSelected, accept = '.csv,.tsv,.txt', disabled }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        setFile(file);
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setFile(file);
        onFileSelected(file);
      }
    },
    [onFileSelected],
  );

  return (
    <label
      className={`flex flex-col items-center justify-center w-full h-56 border-2 border-dashed rounded-2xl cursor-pointer transition-all
        ${dragActive ? 'border-primary-500 bg-primary-50 scale-[1.02]' : 'border-gray-300 bg-white hover:bg-gray-50'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      <Upload className="w-10 h-10 text-gray-400 mb-2" />
      {file ? (
  <div className="flex flex-col items-center">
    <p className="text-sm font-medium text-primary-700">
      📄 {file.name}
    </p>
    <p className="text-xs text-gray-500">
      {(file.size / 1024).toFixed(1)} KB
    </p>

    <button
      type="button"
      onClick={() => {
  setFile(null);
  onFileSelected(null); 
}}
      className="mt-2 text-xs px-3 py-1 bg-red-100 text-red-600 rounded"
    >
      Remove
    </button>
  </div>
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
