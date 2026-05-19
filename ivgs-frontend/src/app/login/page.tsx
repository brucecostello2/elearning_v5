/*
 * IVGS v5 — Login Page
 *
 * Per §16.1: Local PostgreSQL-based authentication.
 * JWT stored in httpOnly cookies (not localStorage).
 * Rate limit: 5 attempts/minute, lockout after 10 consecutive failures.
 *
 * Form fields: username, password
 * On success: redirect to dashboard (/)
 * On failure: display error message with remaining attempts
 */

"use client";

import { useState, useCallback, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { LoadingSpinner } from "@/components/LoadingSpinner";

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading: authLoading } = useAuth();

  const [username, setUsername] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [remainingAttempts, setRemainingAttempts] = useState<number | null>(
    null,
  );

  const handleSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setError("");
      setIsSubmitting(true);

      try {
        const result = await login(username, password);

        if (result.success) {
          router.push("/");
          router.refresh();
        } else {
          setError(result.error ?? "Authentication failed");
          if (result.remainingAttempts !== undefined) {
            setRemainingAttempts(result.remainingAttempts);
          }
        }
      } catch {
        setError("An unexpected error occurred. Please try again.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [login, username, password, router],
  );

  const isDisabled = isSubmitting || authLoading;

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo / Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-ivgs-600">
            <span className="text-2xl font-bold text-white">V5</span>
          </div>
          <h1 className="mt-4 text-2xl font-bold text-white">
            Sign in to IVGS
          </h1>
          <p className="mt-1 text-sm text-gray-400">
            Intelligent Video Generation System
          </p>
        </div>

        {/* Login Form */}
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-gray-800 bg-gray-900 p-6 shadow-xl"
        >
          {/* Error Alert */}
          {error && (
            <div className="mb-4 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-400">
              <p>{error}</p>
              {remainingAttempts !== null && remainingAttempts <= 3 && (
                <p className="mt-1 font-medium">
                  {remainingAttempts} attempt
                  {remainingAttempts !== 1 ? "s" : ""} remaining before lockout
                </p>
              )}
            </div>
          )}

          {/* Username */}
          <div className="mb-4">
            <label
              htmlFor="username"
              className="mb-1.5 block text-sm font-medium text-gray-300"
            >
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              required
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isDisabled}
              className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
              placeholder="Enter your username"
            />
          </div>

          {/* Password */}
          <div className="mb-6">
            <label
              htmlFor="password"
              className="mb-1.5 block text-sm font-medium text-gray-300"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isDisabled}
              className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
              placeholder="Enter your password"
            />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={isDisabled || !username || !password}
            className="flex w-full items-center justify-center rounded-lg bg-ivgs-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-ivgs-700 focus:outline-none focus:ring-2 focus:ring-ivgs-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <LoadingSpinner size="sm" className="mr-2" />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </form>

        {/* Footer note */}
        <p className="mt-4 text-center text-xs text-gray-500">
          Contact your administrator for account access.
        </p>
      </div>
    </div>
  );
}
