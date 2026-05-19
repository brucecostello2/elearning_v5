/*
 * IVGS v5 — Register Page
 *
 * Per §16.2: Only admins can create user accounts.
 * Form fields: username, email, password, confirm password, role (admin/operator/viewer)
 *
 * Accessible only to authenticated admin users.
 * On success: redirect to admin user management page.
 */

"use client";

import { useState, useCallback, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { apiClient } from "@/lib/api-client";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { UserRole } from "@/types/api";

interface RegisterFormData {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  role: UserRole;
}

export default function RegisterPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [formData, setFormData] = useState<RegisterFormData>({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
    role: "operator",
  });
  const [error, setError] = useState<string>("");
  const [success, setSuccess] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  /* Only admin users can access this page */
  if (user && user.role !== "admin") {
    router.push("/");
    return null;
  }

  const handleChange = (
    field: keyof RegisterFormData,
    value: string,
  ): void => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setError("");
  };

  const handleSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setError("");
      setSuccess("");

      /* Client-side validation */
      if (formData.password !== formData.confirmPassword) {
        setError("Passwords do not match");
        return;
      }

      if (formData.password.length < 8) {
        setError("Password must be at least 8 characters");
        return;
      }

      setIsSubmitting(true);

      try {
        await apiClient.post("/api/v1/users", {
          username: formData.username,
          email: formData.email,
          password: formData.password,
          role: formData.role,
        });

        setSuccess(`User "${formData.username}" created successfully`);
        setFormData({
          username: "",
          email: "",
          password: "",
          confirmPassword: "",
          role: "operator",
        });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to create user";
        setError(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [formData],
  );

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Create User Account</h1>
        <p className="mt-1 text-sm text-gray-400">
          Create a new user account with role-based permissions per §16.2.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-gray-800 bg-gray-900 p-6"
      >
        {/* Error / Success */}
        {error && (
          <div className="mb-4 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-lg border border-green-800/50 bg-green-900/20 px-4 py-3 text-sm text-green-400">
            {success}
          </div>
        )}

        {/* Username */}
        <div className="mb-4">
          <label
            htmlFor="reg-username"
            className="mb-1.5 block text-sm font-medium text-gray-300"
          >
            Username
          </label>
          <input
            id="reg-username"
            type="text"
            required
            value={formData.username}
            onChange={(e) => handleChange("username", e.target.value)}
            disabled={isSubmitting}
            className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
            placeholder="e.g., jsmith"
          />
        </div>

        {/* Email */}
        <div className="mb-4">
          <label
            htmlFor="reg-email"
            className="mb-1.5 block text-sm font-medium text-gray-300"
          >
            Email
          </label>
          <input
            id="reg-email"
            type="email"
            required
            value={formData.email}
            onChange={(e) => handleChange("email", e.target.value)}
            disabled={isSubmitting}
            className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
            placeholder="user@example.com"
          />
        </div>

        {/* Password */}
        <div className="mb-4">
          <label
            htmlFor="reg-password"
            className="mb-1.5 block text-sm font-medium text-gray-300"
          >
            Password
          </label>
          <input
            id="reg-password"
            type="password"
            required
            minLength={8}
            value={formData.password}
            onChange={(e) => handleChange("password", e.target.value)}
            disabled={isSubmitting}
            className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
            placeholder="Minimum 8 characters"
          />
        </div>

        {/* Confirm Password */}
        <div className="mb-4">
          <label
            htmlFor="reg-confirm"
            className="mb-1.5 block text-sm font-medium text-gray-300"
          >
            Confirm Password
          </label>
          <input
            id="reg-confirm"
            type="password"
            required
            value={formData.confirmPassword}
            onChange={(e) => handleChange("confirmPassword", e.target.value)}
            disabled={isSubmitting}
            className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
            placeholder="Repeat password"
          />
        </div>

        {/* Role */}
        <div className="mb-6">
          <label
            htmlFor="reg-role"
            className="mb-1.5 block text-sm font-medium text-gray-300"
          >
            Role
          </label>
          <select
            id="reg-role"
            value={formData.role}
            onChange={(e) =>
              handleChange("role", e.target.value)
            }
            disabled={isSubmitting}
            className="block w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white focus:border-ivgs-500 focus:outline-none focus:ring-1 focus:ring-ivgs-500 disabled:opacity-50"
          >
            <option value="admin">Admin — Full system access</option>
            <option value="operator">
              Operator — Create/manage own projects
            </option>
            <option value="viewer">Viewer — Read-only access</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">
            See §16.2 Table 16-2 for role permission details.
          </p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center rounded-lg bg-ivgs-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-ivgs-700 focus:outline-none focus:ring-2 focus:ring-ivgs-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50"
        >
          {isSubmitting ? (
            <>
              <LoadingSpinner size="sm" className="mr-2" />
              Creating…
            </>
          ) : (
            "Create User"
          )}
        </button>
      </form>
    </div>
  );
}
