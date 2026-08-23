"use client";

import React, { useMemo } from "react";
import { asText, splitLines } from "@/lib/text";

/**
 * §8.1.3 Table 8-2 — Transcript Side-by-Side Diff Editor
 *
 * Displays original text and refined text side by side.
 * In read-only mode: visual diff highlighting (additions in green, deletions in red).
 * In edit mode: editable textarea for the refined text.
 */

/**
 * WP-40 Task 5 / ledger P1.4r.
 *
 * `originalText` is typed nullable BECAUSE IT IS. The transcript API sends no
 * `original_text` field (schemas/transcript.py:13) and the `transcripts`
 * table has no such column -- the source document is an asset referenced by
 * `original_asset_id`. The page passed `transcript.original_text`, i.e.
 * `undefined`, and `original.split("\n")` threw
 * "Cannot read properties of undefined (reading 'split')" on the project
 * detail chunk. Declaring the prop honestly is what stops that recurring;
 * the guards below are what stop it crashing when it does.
 */
interface TranscriptEditorProps {
  originalText: string | null | undefined;
  refinedText: string | null | undefined;
  onChange?: (text: string) => void;
  readOnly?: boolean;
}

/** Shown in the "Original" pane when the API has no original text to give. */
const ABSENT_ORIGINAL =
  "No original text is stored for this transcript. The uploaded source " +
  "document is kept as an asset; the refined text is on the right.";

interface DiffLine {
  type: "unchanged" | "added" | "removed";
  text: string;
}

/**
 * Simple line-by-line diff algorithm for visual comparison.
 * Not a full Myers diff — sufficient for transcript comparison.
 */
function computeLineDiff(
  original: string | null | undefined,
  refined: string | null | undefined
): { left: DiffLine[]; right: DiffLine[] } {
  const origLines = splitLines(original);
  const refLines = splitLines(refined);
  const left: DiffLine[] = [];
  const right: DiffLine[] = [];

  const maxLen = Math.max(origLines.length, refLines.length);

  for (let i = 0; i < maxLen; i++) {
    const origLine = i < origLines.length ? origLines[i] : undefined;
    const refLine = i < refLines.length ? refLines[i] : undefined;

    if (origLine !== undefined && refLine !== undefined) {
      if (origLine === refLine) {
        left.push({ type: "unchanged", text: origLine });
        right.push({ type: "unchanged", text: refLine });
      } else {
        left.push({ type: "removed", text: origLine });
        right.push({ type: "added", text: refLine });
      }
    } else if (origLine !== undefined) {
      left.push({ type: "removed", text: origLine });
      right.push({ type: "unchanged", text: "" });
    } else if (refLine !== undefined) {
      left.push({ type: "unchanged", text: "" });
      right.push({ type: "added", text: refLine });
    }
  }

  return { left, right };
}

export default function TranscriptEditor({
  originalText,
  refinedText,
  onChange,
  readOnly = true,
}: TranscriptEditorProps): React.ReactElement {
  const hasOriginal = typeof originalText === "string" && originalText.length > 0;

  const diff = useMemo(
    () => computeLineDiff(originalText, refinedText),
    [originalText, refinedText]
  );

  const getDiffBgClass = (type: DiffLine["type"]): string => {
    switch (type) {
      case "added":
        return "bg-green-900/20";
      case "removed":
        return "bg-red-900/20";
      default:
        return "";
    }
  };

  const getDiffTextClass = (type: DiffLine["type"]): string => {
    switch (type) {
      case "added":
        return "text-green-300";
      case "removed":
        return "text-red-300 line-through";
      default:
        return "text-gray-300";
    }
  };

  if (!readOnly && onChange) {
    // Edit mode: original (read-only) | refined (editable textarea)
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
            Original
          </h4>
          <div
            className={`p-4 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-sm whitespace-pre-wrap max-h-[500px] overflow-y-auto ${
              hasOriginal
                ? "text-gray-700 dark:text-gray-300 font-mono"
                : "text-gray-500 dark:text-gray-400 italic"
            }`}
          >
            {hasOriginal ? originalText : ABSENT_ORIGINAL}
          </div>
        </div>
        <div>
          <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
            Refined (editing)
          </h4>
          <textarea
            value={asText(refinedText)}
            onChange={(e) => onChange(e.target.value)}
            className="w-full p-4 bg-white dark:bg-gray-900 border border-blue-600 rounded-lg text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none min-h-[200px] max-h-[500px]"
            rows={Math.max(10, splitLines(refinedText).length)}
          />
        </div>
      </div>
    );
  }

  // Read-only diff view
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
          Original
        </h4>
        <div className="bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden max-h-[500px] overflow-y-auto">
          {!hasOriginal && (
            <p className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 italic">
              {ABSENT_ORIGINAL}
            </p>
          )}
          {diff.left.map((line, idx) => (
            <div
              key={idx}
              className={`flex px-4 py-0.5 text-sm font-mono ${getDiffBgClass(
                line.type
              )}`}
            >
              <span className="w-8 text-right text-gray-600 dark:text-gray-400 text-xs mr-3 select-none">
                {idx + 1}
              </span>
              <span className={getDiffTextClass(line.type)}>
                {line.text || "\u00A0"}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
          Refined
        </h4>
        <div className="bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden max-h-[500px] overflow-y-auto">
          {diff.right.map((line, idx) => (
            <div
              key={idx}
              className={`flex px-4 py-0.5 text-sm font-mono ${getDiffBgClass(
                line.type
              )}`}
            >
              <span className="w-8 text-right text-gray-600 dark:text-gray-400 text-xs mr-3 select-none">
                {idx + 1}
              </span>
              <span className={getDiffTextClass(line.type)}>
                {line.text || "\u00A0"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
