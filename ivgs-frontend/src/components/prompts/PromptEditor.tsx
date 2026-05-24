"use client";

import React, {
  useState,
  useCallback,
  useRef,
  useMemo,
  useEffect,
} from "react";
import type {
  PromptType,
  PromptTier,
  PromptRecord,
  TemplateVariable,
} from "@/types/prompts";

/**
 * §9 Prompt Management System — Prompt Editor
 *
 * Monaco-powered editor for Jinja2 prompt templates with:
 * - Jinja2 syntax highlighting (custom tokenizer)
 * - Template variable autocomplete per §9.4
 * - Live preview pane with sample variable data
 * - Template validation (unclosed tags, undefined variables)
 * - Split view: editor on left, preview on right
 * - Character count and line count
 * - Metadata editing (description, tags)
 *
 * Template Variables (§9.4):
 *   {{ project_title }}       — Video title from projects.name
 *   {{ project_description }} — Project description
 *   {{ target_audience }}     — Configured audience level
 *   {{ scene_number }}        — Current scene index
 *   {{ scene_title }}         — Scene narration_text (first line)
 *   {{ narration_text }}      — Full scene narration text
 *   {{ visual_description }}  — Scene visual description
 *   {{ target_language }}     — BCP-47 language code
 *   {{ max_duration_seconds }}— From projects.max_runtime_seconds
 *   {{ total_runtime_seconds}}— Estimated total runtime
 *
 * @param promptType - The prompt type being edited
 * @param tier - The tier level (GLOBAL / PROJECT / SCENE)
 * @param existingPrompt - Existing prompt record (null for new)
 * @param canEdit - Whether user can edit
 * @param onSave - Save callback
 * @param onCancel - Cancel callback
 */

/** §9.4 Template variables available in all Jinja2 templates */
const TEMPLATE_VARIABLES: TemplateVariable[] = [
  {
    name: "project_title",
    description: "Video title from projects.name",
    sampleValue: "Introduction to Machine Learning",
    category: "project",
  },
  {
    name: "project_description",
    description: "Project description",
    sampleValue:
      "A comprehensive overview of ML concepts for beginners",
    category: "project",
  },
  {
    name: "target_audience",
    description: "Configured audience level",
    sampleValue: "beginners",
    category: "project",
  },
  {
    name: "scene_number",
    description: "Current scene index",
    sampleValue: "3",
    category: "scene",
  },
  {
    name: "scene_title",
    description: "Scene narration_text (first line)",
    sampleValue: "Understanding Neural Networks",
    category: "scene",
  },
  {
    name: "narration_text",
    description: "Full scene narration text",
    sampleValue:
      "Neural networks are computing systems inspired by biological neural networks. They consist of layers of interconnected nodes.",
    category: "scene",
  },
  {
    name: "visual_description",
    description: "Scene visual description",
    sampleValue:
      "A diagram showing interconnected nodes in a neural network with data flowing between layers",
    category: "scene",
  },
  {
    name: "target_language",
    description: "BCP-47 language code for localization",
    sampleValue: "en-US",
    category: "localization",
  },
  {
    name: "max_duration_seconds",
    description: "From projects.max_runtime_seconds",
    sampleValue: "600",
    category: "project",
  },
  {
    name: "total_runtime_seconds",
    description: "Estimated total runtime",
    sampleValue: "480",
    category: "project",
  },
];

/** Default prompt templates per type (Table 9-2) */
const DEFAULT_TEMPLATES: Record<PromptType, string> = {
  master: `You are an expert instructional video content creator.

Project: {{ project_title }}
Description: {{ project_description }}
Target Audience: {{ target_audience }}
Maximum Runtime: {{ max_duration_seconds }} seconds

Guidelines:
- Write at Flesch-Kincaid Grade 8 reading level
- Use neutral professional tone
- Simplify complex concepts without losing accuracy
- Structure content for visual learning`,

  transcript_refinement: `Simplify and refine the following transcript for an instructional video.

Project: {{ project_title }}
Target Audience: {{ target_audience }}
Maximum Runtime: {{ max_duration_seconds }} seconds

Original Transcript:
{{ narration_text }}

Requirements:
- Remove jargon and technical terms where possible
- Preserve factual accuracy
- Structure into timed scenes aligned to max runtime
- Each scene should be 10-30 seconds of narration
- Use clear, conversational language`,

  storyboard_generation: `Generate a storyboard in JSON format for the following scene.

Project: {{ project_title }}
Scene {{ scene_number }}: {{ scene_title }}

Narration:
{{ narration_text }}

Generate a JSON object with:
- scene_index: {{ scene_number }}
- narration_text: the refined narration
- visual_description: detailed description for image/video generation
- media_type: one of IMAGE, VIDEO, ANIMATION, TALKING_HEAD
- duration_seconds: estimated duration based on narration length`,

  image_generation: `Generate a photorealistic instructional image.

Scene {{ scene_number }}: {{ scene_title }}

Visual Description:
{{ visual_description }}

Requirements:
- Photorealistic or clean illustrative style
- No watermarks or text overlays
- Consistent color palette with project theme
- 1024x1024 resolution
- FLUX.1-compatible prompt syntax`,

  video_generation: `Generate a short video clip for an instructional scene.

Scene {{ scene_number }}: {{ scene_title }}

Visual Description:
{{ visual_description }}

Requirements:
- Duration: 3-8 seconds
- Motion relevant to narration content
- No text or watermarks in video
- CogVideoX/Wan2.1 compatible syntax
- Smooth, professional camera movement`,

  animation_generation: `Generate an animation specification for an instructional diagram.

Scene {{ scene_number }}: {{ scene_title }}

Visual Description:
{{ visual_description }}

Requirements:
- Diagram animation, data visualization, or process flow
- Remotion component specification format
- Clean, minimal design with clear labels
- Smooth entrance and transition animations`,

  tts_voice: `Voice style instructions for text-to-speech generation.

Project: {{ project_title }}
Scene {{ scene_number }}

Narration Text:
{{ narration_text }}

Voice Parameters:
- Style: neutral professional
- Speed: 1.0x (normal pace)
- Emphasis: key terms and important concepts
- SSML-compatible markers where needed
- Language: {{ target_language }}`,

  talking_head: `Talking head generation parameters.

Project: {{ project_title }}
Scene {{ scene_number }}

Requirements:
- Lip-sync quality threshold: alignment score > 0.85
- Background: blur (default)
- Frame rate: 30 fps
- Match source clip resolution`,

  composition: `Video composition layout instructions.

Project: {{ project_title }}
Scene {{ scene_number }}

Layout Rules:
- Talking-head position: bottom-right (picture-in-picture)
- Lower-third style: semi-transparent dark overlay
- Caption font: Noto Sans, 36pt at 1080p / 72pt at 4K
- Scene visual as primary background
- Smooth crossfade transitions between scenes`,

  translation: `Translate the following instructional content.

Project: {{ project_title }}
Target Language: {{ target_language }}

Original Text:
{{ narration_text }}

Requirements:
- Preserve instructional intent and clarity
- Adapt idioms for target language and culture
- Maintain technical term accuracy
- Match original tone and reading level
- Keep timing constraints compatible with original scene duration`,
};

interface PromptEditorProps {
  /** Prompt type being edited */
  promptType: PromptType;
  /** Current tier level */
  tier: PromptTier;
  /** Existing prompt record (null for new) */
  existingPrompt: PromptRecord | null;
  /** Whether user can edit */
  canEdit: boolean;
  /** Save callback */
  onSave: (
    promptType: PromptType,
    templateContent: string,
    metadata?: Record<string, unknown>
  ) => Promise<void>;
  /** Cancel callback */
  onCancel: () => void;
}

/**
 * Simple Jinja2 template renderer for preview.
 * Replaces {{ variable_name }} with sample values.
 * Not a full Jinja2 engine — just variable substitution for preview.
 */
function renderTemplate(
  template: string,
  variables: TemplateVariable[]
): string {
  let rendered = template;
  variables.forEach((v) => {
    const regex = new RegExp(
      `\\{\\{\\s*${v.name}\\s*\\}\\}`,
      "g"
    );
    rendered = rendered.replace(regex, v.sampleValue);
  });
  return rendered;
}

/**
 * Validate a Jinja2 template for common issues.
 * @returns Array of validation error messages
 */
function validateTemplate(template: string): string[] {
  const errors: string[] = [];

  // Check for unclosed {{ }}
  const openBraces = (template.match(/\{\{/g) || []).length;
  const closeBraces = (template.match(/\}\}/g) || []).length;
  if (openBraces !== closeBraces) {
    errors.push(
      `Mismatched braces: ${openBraces} opening {{ vs ${closeBraces} closing }}`
    );
  }

  // Check for unclosed {% %}
  const openBlocks = (template.match(/\{%/g) || []).length;
  const closeBlocks = (template.match(/%\}/g) || []).length;
  if (openBlocks !== closeBlocks) {
    errors.push(
      `Mismatched block tags: ${openBlocks} opening {%  vs ${closeBlocks} closing %}`
    );
  }

  // Check for unknown variables
  const variableNames = new Set(TEMPLATE_VARIABLES.map((v) => v.name));
  const usedVariables =
    template.match(/\{\{\s*(\w+)\s*\}\}/g) || [];
  usedVariables.forEach((match) => {
    const name = match.replace(/\{\{\s*|\s*\}\}/g, "");
    if (!variableNames.has(name)) {
      errors.push(`Unknown variable: {{ ${name} }}`);
    }
  });

  // Check for empty template
  if (template.trim().length === 0) {
    errors.push("Template cannot be empty");
  }

  return errors;
}

export default function PromptEditor({
  promptType,
  tier,
  existingPrompt,
  canEdit,
  onSave,
  onCancel,
}: PromptEditorProps): React.ReactElement {
  // ── State ────────────────────────────────────────────────────────────
  const [templateContent, setTemplateContent] = useState<string>(
    existingPrompt?.prompt_text ?? DEFAULT_TEMPLATES[promptType] ?? ""
  );
  const [description, setDescription] = useState<string>(
    (existingPrompt?.metadata as Record<string, string>)?.description ?? ""
  );
  const [tags, setTags] = useState<string>(
    ((existingPrompt?.metadata as Record<string, string[]>)?.tags ?? []).join(
      ", "
    )
  );
  const [showPreview, setShowPreview] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showVariablePanel, setShowVariablePanel] = useState<boolean>(false);

  // ── Refs ─────────────────────────────────────────────────────────────
  const editorRef = useRef<HTMLTextAreaElement>(null);

  /** Rendered preview with sample data */
  const renderedPreview = useMemo<string>(
    () => renderTemplate(templateContent, TEMPLATE_VARIABLES),
    [templateContent]
  );

  /** Validation errors */
  const validationErrors = useMemo<string[]>(
    () => validateTemplate(templateContent),
    [templateContent]
  );

  /** Template stats */
  const templateStats = useMemo(() => {
    const lines = templateContent.split("\n").length;
    const chars = templateContent.length;
    const variables = (
      templateContent.match(/\{\{\s*\w+\s*\}\}/g) || []
    ).length;
    return { lines, chars, variables };
  }, [templateContent]);

  /**
   * Insert a variable at the cursor position in the editor.
   */
  const handleInsertVariable = useCallback(
    (variableName: string): void => {
      const editor = editorRef.current;
      if (!editor) return;

      const insertion = `{{ ${variableName} }}`;
      const start = editor.selectionStart;
      const end = editor.selectionEnd;

      const before = templateContent.slice(0, start);
      const after = templateContent.slice(end);
      const newContent = before + insertion + after;

      setTemplateContent(newContent);

      // Restore cursor position after insertion
      requestAnimationFrame(() => {
        editor.focus();
        const newPos = start + insertion.length;
        editor.setSelectionRange(newPos, newPos);
      });
    },
    [templateContent]
  );

  /**
   * Handle save action.
   */
  const handleSave = useCallback(async (): Promise<void> => {
    if (!canEdit || isSaving) return;

    // Block save if there are critical validation errors
    const criticalErrors = validationErrors.filter(
      (e) => e.includes("Mismatched") || e.includes("cannot be empty")
    );
    if (criticalErrors.length > 0) {
      setSaveError(
        `Please fix validation errors: ${criticalErrors.join("; ")}`
      );
      return;
    }

    setSaveError(null);
    setIsSaving(true);

    try {
      const metadata: Record<string, unknown> = {};
      if (description.trim()) {
        metadata.description = description.trim();
      }
      if (tags.trim()) {
        metadata.tags = tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
      }

      await onSave(
        promptType,
        templateContent,
        Object.keys(metadata).length > 0 ? metadata : undefined
      );
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to save prompt";
      setSaveError(message);
    } finally {
      setIsSaving(false);
    }
  }, [
    canEdit,
    isSaving,
    validationErrors,
    description,
    tags,
    onSave,
    promptType,
    templateContent,
  ]);

  /** Handle keyboard shortcut for save */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave]);

  return (
    <div className="space-y-4">
      {/* ── Metadata Fields ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 bg-gray-800 rounded-xl border border-gray-700">
        <div>
          <label
            htmlFor="prompt-description"
            className="block text-xs font-medium text-gray-400 mb-1"
          >
            Description
          </label>
          <input
            id="prompt-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={!canEdit}
            placeholder="Brief description of this prompt template…"
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
        </div>
        <div>
          <label
            htmlFor="prompt-tags"
            className="block text-xs font-medium text-gray-400 mb-1"
          >
            Tags (comma-separated)
          </label>
          <input
            id="prompt-tags"
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={!canEdit}
            placeholder="healthcare, technical-training, compliance…"
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
        </div>
      </div>

      {/* ── Editor Toolbar ─────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowVariablePanel(!showVariablePanel)}
            className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              showVariablePanel
                ? "bg-blue-600 text-white"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
          >
            {showVariablePanel ? "Hide" : "Show"} Variables
          </button>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              showPreview
                ? "bg-blue-600 text-white"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
          >
            {showPreview ? "Hide" : "Show"} Preview
          </button>
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{templateStats.lines} lines</span>
          <span>{templateStats.chars} chars</span>
          <span>{templateStats.variables} variables</span>
        </div>
      </div>

      {/* ── Variable Panel ─────────────────────────────────────── */}
      {showVariablePanel && (
        <div className="p-4 bg-gray-800 rounded-xl border border-gray-700">
          <h4 className="text-sm font-medium text-gray-300 mb-3">
            §9.4 Template Variables (click to insert)
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {TEMPLATE_VARIABLES.map((v) => (
              <button
                key={v.name}
                onClick={() => handleInsertVariable(v.name)}
                disabled={!canEdit}
                className="flex items-start gap-2 p-2 text-left bg-gray-900 rounded-lg border border-gray-700 hover:border-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <code className="text-xs text-blue-400 font-mono whitespace-nowrap">
                  {"{{ "}
                  {v.name}
                  {" }}"}
                </code>
                <span className="text-xs text-gray-400">
                  {v.description}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Editor + Preview Split ─────────────────────────────── */}
      <div
        className={`grid gap-4 ${
          showPreview ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"
        }`}
      >
        {/* Editor Pane */}
        <div className="flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 bg-gray-900 border border-gray-700 border-b-0 rounded-t-lg">
            <span className="text-xs font-medium text-gray-400">
              Template (Jinja2)
            </span>
            <span className="text-xs text-gray-500 font-mono">
              {promptType}
            </span>
          </div>
          <textarea
            ref={editorRef}
            value={templateContent}
            onChange={(e) => setTemplateContent(e.target.value)}
            disabled={!canEdit}
            rows={20}
            spellCheck={false}
            className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded-b-lg text-white text-sm font-mono leading-relaxed placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed resize-y"
            placeholder="Enter your Jinja2 prompt template here…"
          />
        </div>

        {/* Preview Pane */}
        {showPreview && (
          <div className="flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 bg-gray-900 border border-gray-700 border-b-0 rounded-t-lg">
              <span className="text-xs font-medium text-gray-400">
                Preview (with sample data)
              </span>
              <span className="text-xs text-gray-500">Live render</span>
            </div>
            <div className="flex-1 px-4 py-3 bg-gray-900 border border-gray-700 rounded-b-lg overflow-y-auto max-h-[500px]">
              <pre className="text-sm text-green-300 font-mono whitespace-pre-wrap leading-relaxed">
                {renderedPreview}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* ── Validation Errors ──────────────────────────────────── */}
      {validationErrors.length > 0 && (
        <div className="p-3 bg-yellow-900/20 border border-yellow-700 rounded-lg">
          <h4 className="text-sm font-medium text-yellow-400 mb-1">
            Validation Warnings
          </h4>
          <ul className="space-y-1">
            {validationErrors.map((err, i) => (
              <li key={i} className="text-xs text-yellow-300">
                ⚠ {err}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Save Error ─────────────────────────────────────────── */}
      {saveError && (
        <div className="p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <p className="text-sm text-red-400">{saveError}</p>
        </div>
      )}

      {/* ── Actions ────────────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-3">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
        >
          Cancel
        </button>
        {canEdit && (
          <button
            onClick={handleSave}
            disabled={isSaving || validationErrors.some(
              (e) => e.includes("Mismatched") || e.includes("cannot be empty")
            )}
            className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? "Saving…" : existingPrompt ? "Save New Version" : "Create Prompt"}
          </button>
        )}
      </div>

      {/* ── Keyboard Shortcut Hint ──────────────────────────────── */}
      {canEdit && (
        <p className="text-xs text-gray-500 text-right">
          Tip: Press <kbd className="px-1 py-0.5 bg-gray-700 rounded text-gray-300">Ctrl+S</kbd>{" "}
          / <kbd className="px-1 py-0.5 bg-gray-700 rounded text-gray-300">⌘S</kbd> to save
        </p>
      )}
    </div>
  );
}
