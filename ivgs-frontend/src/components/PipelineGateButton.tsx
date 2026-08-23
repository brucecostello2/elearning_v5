"use client";

import React, { useCallback, useState } from "react";

/**
 * A pipeline gate action: tier selector, confirmation dialog, server reason.
 *
 * WP-40 Task 3. Two gates in this system are irreversible-ish, cost GPU time
 * and were reachable only by pasting a curl block:
 *
 *   - Approve storyboard -> POST /projects/{id}/scenes/approve?tier=
 *   - Trigger pipeline    -> POST /projects/{id}/trigger?tier=
 *
 * Both take the same AD-01 tier parameter (prototype | production) and both
 * answer 409 with a specific, useful reason when the project is in the wrong
 * state. This component is that shared shape, so the two gates cannot drift
 * apart in how they confirm or how they report a refusal.
 *
 * Design decisions worth stating, because they are what the operator feels:
 *
 *   - The confirmation names the tier and the consequence. Starting a
 *     production run by mis-clicking a button is the failure mode this
 *     exists to prevent.
 *   - A 409's message is rendered VERBATIM. The server knows why it refused
 *     ("no transcripts uploaded", "media generation already started or
 *     past"); paraphrasing it would only lose information.
 *   - RBAC is the caller's job (`require_operator_or_admin` on both routes).
 *     This component never renders for a viewer because the caller does not
 *     mount it -- see the `canApprove`/`canTrigger` guards at both sites.
 */

export type RenderTier = "prototype" | "production";

interface PipelineGateButtonProps {
  /** Button text, e.g. "Approve storyboard". */
  label: string;
  /** Title of the confirmation dialog. */
  confirmTitle: string;
  /** What will happen, in the operator's terms. Shown above the tier picker. */
  confirmBody: string;
  /** Text on the confirming button. */
  confirmLabel: string;
  /** The call. Rejects with an Error whose message is the server's reason. */
  onConfirm: (tier: RenderTier) => Promise<unknown>;
  /** Message shown on success. */
  successMessage: string;
  /** Tailwind classes for the trigger button. */
  className?: string;
  disabled?: boolean;
}

const TIERS: { id: RenderTier; label: string; note: string }[] = [
  {
    id: "prototype",
    label: "Prototype",
    note: "Faster and cheaper models. Use this for review passes.",
  },
  {
    id: "production",
    label: "Production",
    note: "Full-quality models. Slower and materially more GPU time.",
  },
];

export default function PipelineGateButton({
  label,
  confirmTitle,
  confirmBody,
  confirmLabel,
  onConfirm,
  successMessage,
  className,
  disabled = false,
}: PipelineGateButtonProps): React.ReactElement {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [tier, setTier] = useState<RenderTier>("prototype");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const close = useCallback((): void => {
    if (isSubmitting) return;
    setIsOpen(false);
    setError(null);
  }, [isSubmitting]);

  const handleConfirm = useCallback(async (): Promise<void> => {
    setIsSubmitting(true);
    setError(null);
    try {
      await onConfirm(tier);
      setSuccess(successMessage);
      setIsOpen(false);
      window.setTimeout(() => setSuccess(null), 8_000);
    } catch (err: unknown) {
      /* The server's own reason, unedited. A 409 from either gate carries
         the precise state or precondition that failed. */
      setError(
        err instanceof Error && err.message
          ? err.message
          : "The request was refused and the server gave no reason.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [onConfirm, tier, successMessage]);

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setIsOpen(true);
        }}
        disabled={disabled}
        className={
          className ??
          "px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
        }
      >
        {label}
      </button>

      {success && (
        <span className="ml-3 text-sm text-green-600 dark:text-green-400">
          {success}
        </span>
      )}

      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
          role="dialog"
          aria-modal="true"
          aria-label={confirmTitle}
          onClick={close}
        >
          <div
            className="w-full max-w-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {confirmTitle}
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {confirmBody}
            </p>

            <fieldset className="mt-5">
              <legend className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Model tier
              </legend>
              <div className="mt-2 space-y-2">
                {TIERS.map((t) => (
                  <label
                    key={t.id}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      tier === t.id
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30"
                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                    }`}
                  >
                    <input
                      type="radio"
                      name="render-tier"
                      value={t.id}
                      checked={tier === t.id}
                      onChange={() => setTier(t.id)}
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium text-gray-900 dark:text-white">
                        {t.label}
                      </span>
                      <span className="block text-xs text-gray-500 dark:text-gray-400">
                        {t.note}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {error && (
              <div className="mt-4 p-3 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg">
                <p className="text-xs font-medium uppercase tracking-wide text-red-700 dark:text-red-300">
                  The server refused this
                </p>
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {error}
                </p>
              </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={close}
                disabled={isSubmitting}
                className="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={isSubmitting}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
              >
                {isSubmitting ? "Working…" : `${confirmLabel} (${tier})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
