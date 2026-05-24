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
 * Ollama:
 *   - Llama 3.2 8B (node-05)
 *   - Phi-3 Medium (node-05)
 *   - Gemma 2 9B (node-05)
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
    id: "llama-3.2-8b",
    name: "Llama 3.2 8B",
    provider: "Ollama",
    node: "node-05",
    vram: "8 GB",
    context: "8K tokens",
    description: "LLM fallback for development, low-priority tasks",
  },
  {
    id: "phi-3-medium",
    name: "Phi-3 Medium",
    provider: "Ollama",
    node: "node-05",
    vram: "8 GB",
    context: "8K tokens",
    description: "Fast inference for utility tasks",
  },
  {
    id: "gemma-2-9b",
    name: "Gemma 2 9B",
    provider: "Ollama",
    node: "node-05",
    vram: "8 GB",
    context: "8K tokens",
    description: "Fallback option",
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
        <div className="p-4 bg-gray-800 rounded-xl border border-gray-700">
          <label className="block text-xs font-medium text-gray-400 mb-2">
            Model {comparisonMode ? "(A)" : ""}
          </label>
          <select
            value={selectedModelId}
            onChange={(e) => setSelectedModelId(e.target.value)}
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {AVAILABLE_MODELS.map((model) => (
              <option key={model.id} value={model.id}>
                [{model.provider}] {model.name} — {model.node}
              </option>
            ))}
          </select>
          {selectedModel && (
            <p className="mt-2 text-xs text-gray-500">
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
              className="w-4 h-4 rounded border-gray-600 bg-gray-900 text-blue-500"
            />
            <label
              htmlFor="comparison-mode"
              className="text-xs text-gray-400"
            >
              Enable comparison mode
            </label>
          </div>

          {/* Comparison model selector */}
          {comparisonMode && (
            <div className="mt-3">
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Model (B)
              </label>
              <select
                value={comparisonModelId}
                onChange={(e) => setComparisonModelId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
        <div className="p-4 bg-gray-800 rounded-xl border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-400">
              Parameters
            </label>
            <button
              onClick={handleResetParams}
              className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
            >
              Reset defaults
            </button>
          </div>

          {/* Temperature */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-400">Temperature</span>
              <span className="text-xs text-gray-300 font-mono">
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
              className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Max Tokens */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-400">Max Tokens</span>
              <span className="text-xs text-gray-300 font-mono">
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
              className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Top P */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-gray-400">Top P</span>
              <span className="text-xs text-gray-300 font-mono">
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
              className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
          </div>
        </div>

        {/* Actions & History */}
        <div className="p-4 bg-gray-800 rounded-xl border border-gray-700 flex flex-col gap-3">
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
            className="w-full px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
          >
            Clear
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
          >
            📜 History ({history.length})
          </button>
          {response && (
            <button
              onClick={handleSaveAsVersion}
              className="w-full px-4 py-2 text-sm font-medium text-purple-300 bg-purple-900/30 border border-purple-700 rounded-lg hover:bg-purple-900/50 transition-colors"
            >
              💾 Save as Prompt Version
            </button>
          )}
          <p className="text-[10px] text-gray-500 text-center mt-auto">
            <kbd className="px-1 py-0.5 bg-gray-700 rounded text-gray-300">
              Ctrl+Enter
            </kbd>{" "}
            to execute
          </p>
        </div>
      </div>

      {/* ── System Prompt ────────────────────────────────────────── */}
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          System Prompt (optional)
        </label>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={3}
          placeholder="Optional system instructions for the model…"
          className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        />
      </div>

      {/* ── Prompt Input ─────────────────────────────────────────── */}
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Prompt
        </label>
        <textarea
          ref={promptRef}
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          rows={8}
          placeholder="Enter your prompt here… Supports Jinja2 {{ variables }}"
          className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        />
      </div>

      {/* ── Error ────────────────────────────────────────────────── */}
      {error && (
        <div className="p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <p className="text-sm text-red-400">{error}</p>
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
            className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-2 bg-gray-900/50 border-b border-gray-700">
              <span className="text-xs font-medium text-gray-400">
                Response {comparisonMode ? "(A)" : ""} —{" "}
                {selectedModel?.name ?? selectedModelId}
              </span>
              {response && (
                <div className="flex items-center gap-3 text-[10px] text-gray-500">
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
                <div className="flex items-center gap-2 text-gray-400">
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
                <pre className="text-sm text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
                  {response.content}
                </pre>
              ) : null}
            </div>
          </div>

          {/* Comparison Response */}
          {comparisonMode && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 bg-gray-900/50 border-b border-gray-700">
                <span className="text-xs font-medium text-gray-400">
                  Response (B) — {comparisonModel?.name ?? comparisonModelId}
                </span>
                {comparisonResponse && (
                  <div className="flex items-center gap-3 text-[10px] text-gray-500">
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
                  <div className="flex items-center gap-2 text-gray-400">
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
                  <pre className="text-sm text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
                    {comparisonResponse.content}
                  </pre>
                ) : (
                  <p className="text-sm text-gray-500">
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
        <div className="bg-gray-800 rounded-xl border border-gray-700">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-medium text-white">
              Session History
            </h3>
            <button
              onClick={() => setHistory([])}
              className="text-xs text-gray-400 hover:text-red-400 transition-colors"
            >
              Clear History
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-gray-700">
            {history.length === 0 ? (
              <div className="px-4 py-6 text-center text-gray-500 text-sm">
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
                    <span className="text-xs font-medium text-gray-300">
                      {entry.model_name}
                    </span>
                    <span className="text-[10px] text-gray-500">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 truncate">
                    {entry.prompt.slice(0, 100)}
                    {entry.prompt.length > 100 ? "…" : ""}
                  </p>
                  {entry.response && (
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
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
      <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
        <p className="text-xs text-gray-500">
          §7.2 — Only self-hosted models (vLLM + Ollama) are available.
          Cloud AI services (OpenAI, Anthropic, Google, etc.) are permanently
          prohibited per the v5 mandate.
        </p>
      </div>
    </div>
  );
}
