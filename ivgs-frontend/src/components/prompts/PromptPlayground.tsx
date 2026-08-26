"use client";

import React, {
  useState,
  useCallback,
  useRef,
  useMemo,
  useEffect,
} from "react";
import { usePrompts } from "@/hooks/usePrompts";
import type {
  PlaygroundModel,
  PlaygroundRequest,
  PlaygroundResponse,
  PlaygroundParameters,
  PlaygroundHistoryEntry,
} from "@/types/prompts";

/**
 * §8.1.6 Prompt Playground
 *
 * Replaces Open WebUI. Accessible from the Prompts tab and from Settings.
 *
 * Features:
 * - Self-hosted model selector (lists ONLY vLLM models and Ollama models)
 * - No cloud options per §7.2 Explicit Prohibitions
 * - Parameter tuning: temperature, max_tokens, top_p
 * - Prompt input with Jinja2 syntax highlighting
 * - Response display with token count and latency
 * - Conversation history within session
 * - Comparison view: test same prompt against two models side by side
 * - Save results as new prompt versions directly from Playground
 *
 * Available Models (§7.1):
 * vLLM:
 *   - Llama 3.3 70B (node-02 + node-03)
 *   - Qwen2.5 72B (node-02 + node-03)
 *   - Mistral 24B (node-04)
 *   - Qwen3.8 27B FP8 (node-05)   [WP-61: the one entry here that is measured]
 *
 * WP-61 Task 2. THE THREE OLLAMA ENTRIES ON node-05 ARE GONE, and they were
 * not a typo: Llama 3.2 8B, Phi-3 Medium and Gemma 2 9B were listed as
 * running on node-05 with 8 GB of VRAM each. node-05 has never run Ollama,
 * has never held any of those three, and its card is a 48 GB RTX PRO 5000
 * Blackwell, not an 8 GB anything. Selecting one of them sent a completion to
 * `OLLAMA_URL` (node-05:11434), where nothing has ever listened. AD-02
 * Draft 4 §1.2 records the same three services being asserted of this node in
 * the specification, and says the same thing: "None of that has ever run on
 * node-05."
 *
 * WHAT IS STILL DECLARED RATHER THAN MEASURED, and is deliberately left
 * alone: `qwen2.5-72b` on node-02+node-03 is not in the Model Store and this
 * package did not verify it, and the tensor-parallel pairing claimed for both
 * node-02 entries is a §7.1 declaration. This list should be READ from
 * `/api/v1/models` rather than transcribed from a spec section, which is a
 * package of its own and is ledgered as such. Correcting only the node-05 rows
 * is the scope of this task; rewriting the others silently would be a claim
 * this package cannot support.
 *
 * @param onBack - Navigation callback to return to parent view
 */

/** Available models per §7.1.1 and §7.1.2 */
const AVAILABLE_MODELS: PlaygroundModel[] = [
  {
    id: "llama-3.3-70b",
    name: "Llama 3.3 70B",
    provider: "vLLM",
    node: "node-02 + node-03",
    vram: "96 GB × 2",
    context: "128K tokens",
    description: "Primary LLM: transcript refinement, storyboard generation",
  },
  {
    id: "qwen2.5-72b",
    name: "Qwen2.5 72B",
    provider: "vLLM",
    node: "node-02 + node-03",
    vram: "96 GB × 2",
    context: "128K tokens",
    description: "Alternative LLM (CJK languages, code-heavy content)",
  },
  {
    id: "mistral-24b",
    name: "Mistral 24B",
    provider: "vLLM",
    node: "node-04",
    vram: "48 GB",
    context: "32K tokens",
    description: "Mid-size LLM: image prompt generation, scene analysis",
  },
  {
    // WP-61. The served-model-name node-05's vLLM actually answers to
    // (`--served-model-name qwen38-27b`), so a playground call reaches a real
    // model rather than a 404 from a server that has never heard of it.
    id: "qwen38-27b",
    name: "Qwen3.8 27B FP8",
    provider: "vLLM",
    node: "node-05",
    vram: "48 GB card",
    context: "128K tokens",
    description:
      "Translation. FP8 only - the BF16 base is ~56 GB and does not fit.",
  },
];

/** Default playground parameters */
const DEFAULT_PARAMS: PlaygroundParameters = {
  temperature: 0.7,
  max_tokens: 2048,
  top_p: 0.9,
};

interface PromptPlaygroundProps {
  /** Navigation callback to return to parent view */
  onBack: () => void;
}

export default function PromptPlayground({
  onBack,
}: PromptPlaygroundProps): React.ReactElement {
  // ── Hooks ────────────────────────────────────────────────────────────
  const { executePlayground, savePlaygroundResult } = usePrompts({});

  // ── State ────────────────────────────────────────────────────────────
  const [promptText, setPromptText] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [selectedModelId, setSelectedModelId] = useState<string>(
    AVAILABLE_MODELS[0]?.id ?? "llama-3.3-70b"
  );
  const [params, setParams] = useState<PlaygroundParameters>({
    ...DEFAULT_PARAMS,
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [response, setResponse] = useState<PlaygroundResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Comparison Mode ──────────────────────────────────────────────────
  const [comparisonMode, setComparisonMode] = useState<boolean>(false);
  const [comparisonModelId, setComparisonModelId] = useState<string>(
    AVAILABLE_MODELS[1]?.id ?? "mistral-7b"
  );
  const [comparisonResponse, setComparisonResponse] =
    useState<PlaygroundResponse | null>(null);
  const [isComparisonLoading, setIsComparisonLoading] =
    useState<boolean>(false);

  // ── History ──────────────────────────────────────────────────────────
  const [history, setHistory] = useState<PlaygroundHistoryEntry[]>([]);
  const [showHistory, setShowHistory] = useState<boolean>(false);

  // ── Refs ─────────────────────────────────────────────────────────────
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const responseRef = useRef<HTMLDivElement>(null);

  /** Get selected model object */
  const selectedModel = useMemo<PlaygroundModel | undefined>(
    () => AVAILABLE_MODELS.find((m) => m.id === selectedModelId),
    [selectedModelId]
  );

  /** Get comparison model object */
  const comparisonModel = useMemo<PlaygroundModel | undefined>(
    () => AVAILABLE_MODELS.find((m) => m.id === comparisonModelId),
    [comparisonModelId]
  );

  /**
   * Execute prompt against selected model(s).
   */
  const handleExecute = useCallback(async (): Promise<void> => {
    if (!promptText.trim() || isLoading) return;

    setError(null);
    setResponse(null);
    setComparisonResponse(null);
    setIsLoading(true);

    const request: PlaygroundRequest = {
      prompt: promptText,
      system_prompt: systemPrompt || undefined,
      model_id: selectedModelId,
      parameters: params,
    };

    try {
      // Execute primary model
      const result = await executePlayground(request);
      setResponse(result);

      // Add to history
      const historyEntry: PlaygroundHistoryEntry = {
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        prompt: promptText,
        system_prompt: systemPrompt || undefined,
        model_id: selectedModelId,
        model_name: selectedModel?.name ?? selectedModelId,
        parameters: { ...params },
        response: result,
      };
      setHistory((prev) => [historyEntry, ...prev]);

      // Execute comparison model if in comparison mode
      if (comparisonMode && comparisonModelId !== selectedModelId) {
        setIsComparisonLoading(true);
        try {
          const compRequest: PlaygroundRequest = {
            ...request,
            model_id: comparisonModelId,
          };
          const compResult = await executePlayground(compRequest);
          setComparisonResponse(compResult);

          // Add comparison to history
          const compHistoryEntry: PlaygroundHistoryEntry = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            prompt: promptText,
            system_prompt: systemPrompt || undefined,
            model_id: comparisonModelId,
            model_name: comparisonModel?.name ?? comparisonModelId,
            parameters: { ...params },
            response: compResult,
          };
          setHistory((prev) => [compHistoryEntry, ...prev]);
        } catch (compErr: unknown) {
          console.error("[Playground] Comparison model error:", compErr);
        } finally {
          setIsComparisonLoading(false);
        }
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to execute prompt";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [
    promptText,
    systemPrompt,
    selectedModelId,
    params,
    isLoading,
    executePlayground,
    comparisonMode,
    comparisonModelId,
    selectedModel,
    comparisonModel,
  ]);

  /**
   * Save current response as a new prompt version.
   */
  const handleSaveAsVersion = useCallback(async (): Promise<void> => {
    if (!response || !promptText.trim()) return;
    try {
      await savePlaygroundResult({
        prompt: promptText,
        system_prompt: systemPrompt || undefined,
        model_id: selectedModelId,
        response: response,
      });
      alert("Saved as new prompt version successfully.");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to save as version";
      alert(message);
    }
  }, [response, promptText, systemPrompt, selectedModelId, savePlaygroundResult]);

  /**
   * Load a history entry back into the playground.
   */
  const handleLoadHistory = useCallback(
    (entry: PlaygroundHistoryEntry): void => {
      setPromptText(entry.prompt);
      setSystemPrompt(entry.system_prompt ?? "");
      setSelectedModelId(entry.model_id);
      setParams(entry.parameters);
      setShowHistory(false);
    },
    []
  );

  /** Clear conversation */
  const handleClear = useCallback((): void => {
    setPromptText("");
    setSystemPrompt("");
    setResponse(null);
    setComparisonResponse(null);
    setError(null);
    promptRef.current?.focus();
  }, []);

  /** Reset parameters to defaults */
  const handleResetParams = useCallback((): void => {
    setParams({ ...DEFAULT_PARAMS });
  }, []);

  /** Handle Ctrl+Enter to execute */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleExecute();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleExecute]);

  return (
    <div className="space-y-6">
      {/* ── Model Selection & Parameters ──────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Primary Model Selector */}
        <div className="p-4 bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700">
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
            Model {comparisonMode ? "(A)" : ""}
          </label>
          <select
            value={selectedModelId}
            onChange={(e) => setSelectedModelId(e.target.value)}
            className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {AVAILABLE_MODELS.map((model) => (
              <option key={model.id} value={model.id}>
                [{model.provider}] {model.name} — {model.node}
              </option>
            ))}
          </select>
          {selectedModel && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {selectedModel.description} · {selectedModel.vram} ·{" "}
              {selectedModel.context}
            </p>
          )}

          {/* Comparison mode toggle */}
          <div className="mt-3 flex items-center gap-2">
            <input
              type="checkbox"
              id="comparison-mode"
              checked={comparisonMode}
              onChange={(e) => setComparisonMode(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-blue-500 dark:text-blue-400"
            />
            <label
              htmlFor="comparison-mode"
              className="text-xs text-gray-500 dark:text-gray-400"
            >
              Enable comparison mode
            </label>
          </div>

          {/* Comparison model selector */}
          {comparisonMode && (
            <div className="mt-3">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Model (B)
              </label>
              <select
                value={comparisonModelId}
                onChange={(e) => setComparisonModelId(e.target.value)}
                className="w-full px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {AVAILABLE_MODELS.filter(
                  (m) => m.id !== selectedModelId
                ).map((model) => (
                  <option key={model.id} value={model.id}>
                    [{model.provider}] {model.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Parameters */}
        <div className="p-4 bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Parameters
            </label>
            <button
              onClick={handleResetParams}
              className="text-[10px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              Reset defaults
            </button>
          </div>

          {/* Temperature */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-500 dark:text-gray-400">Temperature</span>
              <span className="text-xs text-gray-700 dark:text-gray-300 font-mono">
                {params.temperature.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={params.temperature}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  temperature: parseFloat(e.target.value),
                }))
              }
              className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Max Tokens */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-500 dark:text-gray-400">Max Tokens</span>
              <span className="text-xs text-gray-700 dark:text-gray-300 font-mono">
                {params.max_tokens}
              </span>
            </div>
            <input
              type="range"
              min={64}
              max={8192}
              step={64}
              value={params.max_tokens}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  max_tokens: parseInt(e.target.value, 10),
                }))
              }
              className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Top P */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-500 dark:text-gray-400">Top P</span>
              <span className="text-xs text-gray-700 dark:text-gray-300 font-mono">
                {params.top_p.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={params.top_p}
              onChange={(e) =>
                setParams((p) => ({
                  ...p,
                  top_p: parseFloat(e.target.value),
                }))
              }
              className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </div>

        {/* Actions & History */}
        <div className="p-4 bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700 flex flex-col gap-3">
          <button
            onClick={handleExecute}
            disabled={isLoading || !promptText.trim()}
            className="w-full px-4 py-3 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg
                  className="w-4 h-4 animate-spin"
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
                Executing…
              </span>
            ) : (
              "▶ Execute"
            )}
          </button>
          <button
            onClick={handleClear}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
          >
            Clear
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
          >
            📜 History ({history.length})
          </button>
          {response && (
            <button
              onClick={handleSaveAsVersion}
              className="w-full px-4 py-2 text-sm font-medium text-purple-800 dark:text-purple-300 bg-purple-100 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
            >
              💾 Save as Prompt Version
            </button>
          )}
          <p className="text-[10px] text-gray-500 dark:text-gray-400 text-center mt-auto">
            <kbd className="px-1 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-gray-700 dark:text-gray-300">
              Ctrl+Enter
            </kbd>{" "}
            to execute
          </p>
        </div>
      </div>

      {/* ── System Prompt ────────────────────────────────────────── */}
      <div>
        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          System Prompt (optional)
        </label>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={3}
          placeholder="Optional system instructions for the model…"
          className="w-full px-4 py-3 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        />
      </div>

      {/* ── Prompt Input ─────────────────────────────────────────── */}
      <div>
        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          Prompt
        </label>
        <textarea
          ref={promptRef}
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          rows={8}
          placeholder="Enter your prompt here… Supports Jinja2 {{ variables }}"
          className="w-full px-4 py-3 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white text-sm font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        />
      </div>

      {/* ── Error ────────────────────────────────────────────────── */}
      {error && (
        <div className="p-3 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* ── Response Area ────────────────────────────────────────── */}
      {(response || comparisonResponse || isLoading || isComparisonLoading) && (
        <div
          className={`grid gap-4 ${
            comparisonMode ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"
          }`}
        >
          {/* Primary Response */}
          <div
            ref={responseRef}
            className="bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-gray-900/50 border-b border-gray-300 dark:border-gray-700">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Response {comparisonMode ? "(A)" : ""} —{" "}
                {selectedModel?.name ?? selectedModelId}
              </span>
              {response && (
                <div className="flex items-center gap-3 text-[10px] text-gray-500 dark:text-gray-400">
                  <span>
                    {response.usage?.total_tokens ?? "?"} tokens
                  </span>
                  <span>
                    {response.latency_ms
                      ? `${response.latency_ms}ms`
                      : "—"}
                  </span>
                </div>
              )}
            </div>
            <div className="p-4 max-h-96 overflow-y-auto">
              {isLoading ? (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <svg
                    className="w-4 h-4 animate-spin"
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
                  <span className="text-sm">Generating response…</span>
                </div>
              ) : response ? (
                <pre className="text-sm text-gray-800 dark:text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
                  {response.content}
                </pre>
              ) : null}
            </div>
          </div>

          {/* Comparison Response */}
          {comparisonMode && (
            <div className="bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-gray-900/50 border-b border-gray-300 dark:border-gray-700">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  Response (B) — {comparisonModel?.name ?? comparisonModelId}
                </span>
                {comparisonResponse && (
                  <div className="flex items-center gap-3 text-[10px] text-gray-500 dark:text-gray-400">
                    <span>
                      {comparisonResponse.usage?.total_tokens ?? "?"}{" "}
                      tokens
                    </span>
                    <span>
                      {comparisonResponse.latency_ms
                        ? `${comparisonResponse.latency_ms}ms`
                        : "—"}
                    </span>
                  </div>
                )}
              </div>
              <div className="p-4 max-h-96 overflow-y-auto">
                {isComparisonLoading ? (
                  <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                    <svg
                      className="w-4 h-4 animate-spin"
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
                    <span className="text-sm">Generating response…</span>
                  </div>
                ) : comparisonResponse ? (
                  <pre className="text-sm text-gray-800 dark:text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
                    {comparisonResponse.content}
                  </pre>
                ) : (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Waiting for comparison result…
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── History Panel ────────────────────────────────────────── */}
      {showHistory && (
        <div className="bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-300 dark:border-gray-700">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-300 dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white">
              Session History
            </h3>
            <button
              onClick={() => setHistory([])}
              className="text-xs text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
            >
              Clear History
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-gray-300 dark:divide-gray-700">
            {history.length === 0 ? (
              <div className="px-4 py-6 text-center text-gray-500 dark:text-gray-400 text-sm">
                No history yet. Execute a prompt to see results here.
              </div>
            ) : (
              history.map((entry) => (
                <div
                  key={entry.id}
                  className="px-4 py-3 hover:bg-gray-750 transition-colors cursor-pointer"
                  onClick={() => handleLoadHistory(entry)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                      {entry.model_name}
                    </span>
                    <span className="text-[10px] text-gray-500 dark:text-gray-400">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {entry.prompt.slice(0, 100)}
                    {entry.prompt.length > 100 ? "…" : ""}
                  </p>
                  {entry.response && (
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500 dark:text-gray-400">
                      <span>
                        {entry.response.usage?.total_tokens ?? "?"} tokens
                      </span>
                      <span>
                        {entry.response.latency_ms
                          ? `${entry.response.latency_ms}ms`
                          : ""}
                      </span>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Cloud Prohibition Notice ─────────────────────────────── */}
      <div className="p-3 bg-gray-100 dark:bg-gray-800/50 rounded-lg border border-gray-300 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          §7.2 — Only self-hosted models (vLLM + Ollama) are available.
          Cloud AI services (OpenAI, Anthropic, Google, etc.) are permanently
          prohibited per the v5 mandate.
        </p>
      </div>
    </div>
  );
}
