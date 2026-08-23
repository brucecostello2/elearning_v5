"use client";

import React, { useState, useCallback, useRef } from "react";
import { splitOn } from "@/lib/text";

/**
 * Reusable drag-and-drop file upload component.
 * Supports single and multi-file uploads with progress tracking.
 */

interface AssetUploaderProps {
  accept?: string;
  maxSize?: number;
  multiple?: boolean;
  onFileSelect: (files: FileList | File[]) => void;
  selectedFile?: File | null;
  onRemove?: () => void;
  error?: string;
  isUploading?: boolean;
}

export default function AssetUploader({
  accept,
  maxSize,
  multiple = false,
  onFileSelect,
  selectedFile,
  onRemove,
  error,
  isUploading = false,
}: AssetUploaderProps): React.ReactElement {
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string>("");
  const inputRef = useRef<HTMLInputElement>(null);

  /**
   * Validate file against accept types and max size.
   */
  const validateFile = useCallback(
    (file: File): boolean => {
      setValidationError("");

      if (maxSize && file.size > maxSize) {
        const maxMB = (maxSize / (1024 * 1024)).toFixed(0);
        setValidationError(
          `File "${file.name}" exceeds maximum size of ${maxMB} MB.`
        );
        return false;
      }

      // WP-40 Task 5: `accept` is an optional prop and `file.name` can be
      // extensionless. `splitOn` returns [] rather than throwing, and an
      // empty accepted-type list means "accept anything" -- the same
      // behaviour as omitting the prop.
      const acceptedTypes = splitOn(accept, ",").map((t) => t.trim()).filter(Boolean);
      if (acceptedTypes.length > 0) {
        const nameParts = splitOn(file?.name, ".");
        const fileExt =
          nameParts.length > 1 ? `.${String(nameParts.pop()).toLowerCase()}` : "";
        const fileMime = file?.type ?? "";

        const isAccepted = acceptedTypes.some((type) => {
          if (type.startsWith(".")) {
            return fileExt === type.toLowerCase();
          }
          if (type.endsWith("/*")) {
            return fileMime.startsWith(type.replace("/*", ""));
          }
          return fileMime === type;
        });

        if (!isAccepted) {
          setValidationError(
            `File type "${fileExt}" is not accepted. Allowed: ${accept}`
          );
          return false;
        }
      }

      return true;
    },
    [accept, maxSize]
  );

  /**
   * Handle file selection from input or drop.
   */
  const handleFiles = useCallback(
    (files: FileList | null): void => {
      if (!files || files.length === 0) return;

      const validFiles: File[] = [];
      for (const file of Array.from(files)) {
        if (validateFile(file)) {
          validFiles.push(file);
        }
      }

      if (validFiles.length > 0) {
        onFileSelect(validFiles);
      }
    },
    [validateFile, onFileSelect]
  );

  const handleDragEnter = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(true);
    },
    []
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
    },
    []
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
      e.stopPropagation();
    },
    []
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>): void => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // If a file is selected (single file mode), show the file info
  if (selectedFile && !multiple) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg">
        <svg
          className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900 dark:text-white truncate">{selectedFile.name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {formatFileSize(selectedFile.size)}
          </p>
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>
    );
  }

  return (
    <div>
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-col items-center justify-center px-6 py-8 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
          isDragging
            ? "border-blue-500 bg-blue-100 dark:bg-blue-900/10"
            : "border-gray-300 dark:border-gray-600 hover:border-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800/50"
        }`}
      >
        {isUploading ? (
          <div className="flex flex-col items-center gap-2">
            <svg
              className="w-8 h-8 text-blue-600 dark:text-blue-400 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-sm text-blue-600 dark:text-blue-400">Uploading…</span>
          </div>
        ) : (
          <>
            <svg
              className="w-10 h-10 text-gray-500 dark:text-gray-400 mb-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              <span className="text-blue-600 dark:text-blue-400 font-medium">Click to upload</span>
              {" "}or drag and drop
            </p>
            {accept && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Accepted: {accept}
              </p>
            )}
            {maxSize && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Max size: {formatFileSize(maxSize)}
              </p>
            )}
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(e) => handleFiles(e.target.files)}
        className="hidden"
      />

      {(error || validationError) && (
        <p className="text-red-600 dark:text-red-400 text-xs mt-1">
          {error || validationError}
        </p>
      )}
    </div>
  );
}
