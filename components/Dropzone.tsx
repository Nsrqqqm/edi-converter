"use client";

import { useCallback, useState } from "react";

type Props = {
  onFiles: (files: File[]) => void;
  multiple?: boolean;
  disabled?: boolean;
};

export function Dropzone({ onFiles, multiple = false, disabled = false }: Props) {
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLLabelElement>) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.name.toLowerCase().endsWith(".pdf"),
      );
      if (files.length) onFiles(files);
    },
    [disabled, onFiles],
  );

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={[
        "flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        dragging
          ? "border-blue-500 bg-blue-50 dark:border-blue-400 dark:bg-blue-950/40"
          : "border-gray-300 hover:border-gray-400 dark:border-gray-700 dark:hover:border-gray-600",
      ].join(" ")}
    >
      <svg
        className="mb-4 h-10 w-10 text-gray-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
        aria-hidden
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"
        />
      </svg>
      <p className="text-sm font-medium">
        {multiple ? "Drop PDF files here" : "Drop a PDF file here"}
      </p>
      <p className="mt-1 text-xs text-gray-500">or click to browse</p>
      <input
        type="file"
        accept="application/pdf"
        multiple={multiple}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          // allow re-selecting the same file
          e.target.value = "";
        }}
      />
    </label>
  );
}
