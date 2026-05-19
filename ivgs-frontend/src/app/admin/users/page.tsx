"use client";

import React, { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useUsers } from "@/hooks/useMonitoring";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { User, UserRole, CreateUserPayload } from "@/types/monitoring";

/**
 * §5.1.9 Users (Admin Only)
 *
 * User management page accessible only to admin role per Table 8-3.
 * Full CRUD operations:
 * - GET /api/v1/users — list all users
 * - POST /api/v1/users — create user {username, password, role}
 * - PATCH /api/v1/users/{id} — update role or password
 * - DELETE /api/v1/users/{id} — delete user account
 *
 * Features:
 * - User table with sortable columns
 * - Create user modal with form validation
 * - Inline role editing via dropdown
 * - Password reset (sets new password)
 * - Delete with confirmation dialog
 * - Search/filter by username or role
 *
 * RBAC per Table 8-3:
 *   - admin: full CRUD
 *   - operator: no access (redirected)
 *   - viewer: no access (redirected)
 */

/** Available user roles per §16 Authentication and Authorization */
const USER_ROLES: { value: UserRole; label: string; description: string }[] = [
  {
    value: "admin",
    label: "Admin",
    description: "Full access to all features including user management",
  },
  {
    value: "operator",
    label: "Operator",
    description: "Can create projects and manage own content",
  },
  {
    value: "viewer",
    label: "Viewer",
    description: "Read-only access to video gallery",
  },
];

export default function UserManagementPage(): React.ReactElement {
  // ── Auth Guard ──────────────────────────────────────────────────────
  const { user: currentUser } = useAuth();
  const router = useRouter();

  /** Only admin can access this page per Table 8-3 */
  useEffect(() => {
    if (currentUser && currentUser.role !== "admin") {
      router.push("/");
    }
  }, [currentUser, router]);

  // ── State ───────────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("ALL");
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<UserRole>("viewer");
  const [resetPasswordUserId, setResetPasswordUserId] = useState<string | null>(
    null
  );
  const [newPassword, setNewPassword] = useState<string>("");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  /** Create user form state */
  const [createForm, setCreateForm] = useState<CreateUserPayload>({
    username: "",
    password: "",
    role: "viewer",
  });
  const [createErrors, setCreateErrors] = useState<Record<string, string>>({});

  // ── Data Fetching ───────────────────────────────────────────────────
  const {
    users,
    isLoading,
    error,
    mutate: mutateUsers,
  } = useUsers();

  // ── Handlers ────────────────────────────────────────────────────────

  /**
   * handleCreateUser — POST /api/v1/users
   *
   * Creates a new user account with the specified role.
   * Validates required fields and password strength.
   */
  const handleCreateUser = useCallback(async () => {
    /** Validate form */
    const errors: Record<string, string> = {};
    if (!createForm.username.trim()) {
      errors.username = "Username is required";
    } else if (createForm.username.length < 3) {
      errors.username = "Username must be at least 3 characters";
    }
    if (!createForm.password) {
      errors.password = "Password is required";
    } else if (createForm.password.length < 8) {
      errors.password = "Password must be at least 8 characters";
    }
    if (Object.keys(errors).length > 0) {
      setCreateErrors(errors);
      return;
    }

    setActionInProgress("create");
    setActionError(null);
    setCreateErrors({});

    try {
      const response = await fetch("/api/v1/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify(createForm),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        if (response.status === 409) {
          setCreateErrors({ username: "Username already exists" });
          return;
        }
        throw new Error(
          errorData?.detail || `Create failed: ${response.status}`
        );
      }

      setActionSuccess(`User "${createForm.username}" created successfully.`);
      setShowCreateModal(false);
      setCreateForm({ username: "", password: "", role: "viewer" });
      await mutateUsers();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to create user";
      setActionError(message);
    } finally {
      setActionInProgress(null);
    }
  }, [createForm, mutateUsers]);

  /**
   * handleUpdateRole — PATCH /api/v1/users/{id}
   *
   * Updates a user's role. Cannot change own role to prevent lockout.
   */
  const handleUpdateRole = useCallback(
    async (userId: string, newRole: UserRole) => {
      if (userId === currentUser?.id) {
        setActionError("Cannot change your own role.");
        return;
      }

      setActionInProgress(userId);
      setActionError(null);

      try {
        const response = await fetch(`/api/v1/users/${userId}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ role: newRole }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Update failed: ${response.status}`
          );
        }

        setActionSuccess("User role updated.");
        setEditingUserId(null);
        await mutateUsers();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to update role";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [currentUser, mutateUsers]
  );

  /**
   * handleResetPassword — PATCH /api/v1/users/{id}
   *
   * Sets a new password for a user account.
   */
  const handleResetPassword = useCallback(
    async (userId: string) => {
      if (!newPassword || newPassword.length < 8) {
        setActionError("New password must be at least 8 characters.");
        return;
      }

      setActionInProgress(userId);
      setActionError(null);

      try {
        const response = await fetch(`/api/v1/users/${userId}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ password: newPassword }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Password reset failed: ${response.status}`
          );
        }

        setActionSuccess("Password reset successfully.");
        setResetPasswordUserId(null);
        setNewPassword("");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Password reset failed";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [newPassword]
  );

  /**
   * handleDeleteUser — DELETE /api/v1/users/{id}
   *
   * Deletes a user account. Cannot delete own account.
   */
  const handleDeleteUser = useCallback(
    async (userId: string, username: string) => {
      if (userId === currentUser?.id) {
        setActionError("Cannot delete your own account.");
        return;
      }

      if (
        !window.confirm(
          `Delete user "${username}"? This action cannot be undone.`
        )
      ) {
        return;
      }

      setActionInProgress(userId);
      setActionError(null);

      try {
        const response = await fetch(`/api/v1/users/${userId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null);
          throw new Error(
            errorData?.detail || `Delete failed: ${response.status}`
          );
        }

        setActionSuccess(`User "${username}" deleted.`);
        await mutateUsers();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to delete user";
        setActionError(message);
      } finally {
        setActionInProgress(null);
      }
    },
    [currentUser, mutateUsers]
  );

  // ── Filtered Users ──────────────────────────────────────────────────

  const filteredUsers = React.useMemo(() => {
    if (!users) return [];
    return users.filter((u: User) => {
      const matchesSearch =
        !searchQuery ||
        u.username.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesRole =
        roleFilter === "ALL" || u.role === roleFilter;
      return matchesSearch && matchesRole;
    });
  }, [users, searchQuery, roleFilter]);

  // ── Render ──────────────────────────────────────────────────────────

  if (currentUser && currentUser.role !== "admin") return null;

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h3 className="text-lg font-semibold text-red-600">
            User Management Error
          </h3>
          <p className="mt-2 text-sm text-gray-600">
            An error occurred loading user management. Please refresh.
          </p>
        </div>
      }
    >
      <div className="min-h-screen bg-gray-50">
        {/* ── Page Header ─────────────────────────────────────────── */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                User Management
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                §5.1.9 — Admin-only user CRUD (Table 8-3: admin access only)
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm
                font-medium text-white bg-blue-600 hover:bg-blue-700
                rounded-md shadow-sm transition-colors"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0ZM3 19.235v-.11a6.375 6.375 0 0 1 12.75 0v.109A12.318 12.318 0 0 1 9.374 21c-2.331 0-4.512-.645-6.374-1.766Z" />
              </svg>
              Create User
            </button>
          </div>
        </header>

        <div className="px-6 py-6">
          {/* ── Alerts ──────────────────────────────────────────── */}
          {actionSuccess && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-green-700">{actionSuccess}</p>
                <button
                  type="button"
                  onClick={() => setActionSuccess(null)}
                  className="text-green-500 hover:text-green-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {actionError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <div className="flex items-center justify-between">
                <p className="text-sm text-red-700">{actionError}</p>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-red-500 hover:text-red-700"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* ── Filters ─────────────────────────────────────────── */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex-1 min-w-[200px]">
                <label
                  htmlFor="user-search"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  Search
                </label>
                <input
                  id="user-search"
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by username…"
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                />
              </div>
              <div className="min-w-[150px]">
                <label
                  htmlFor="role-filter"
                  className="block text-xs font-medium text-gray-700 mb-1"
                >
                  Role
                </label>
                <select
                  id="role-filter"
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                  className="w-full rounded-md border-gray-300 text-sm shadow-sm
                    focus:border-blue-500 focus:ring-blue-500"
                >
                  <option value="ALL">All Roles</option>
                  {USER_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* ── User Table ───────────────────────────────────────── */}
          {isLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-sm text-red-700">
                Failed to load users. Please try again.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Username
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Role
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Created
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Last Login
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredUsers.length === 0 ? (
                      <tr>
                        <td
                          colSpan={5}
                          className="px-4 py-8 text-center text-sm text-gray-500"
                        >
                          No users found.
                        </td>
                      </tr>
                    ) : (
                      filteredUsers.map((u: User) => (
                        <tr key={u.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center">
                                <span className="text-sm font-medium text-gray-600">
                                  {u.username.charAt(0).toUpperCase()}
                                </span>
                              </div>
                              <div>
                                <p className="text-sm font-medium text-gray-900">
                                  {u.username}
                                </p>
                                {u.id === currentUser?.id && (
                                  <span className="text-xs text-blue-600">
                                    (you)
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {editingUserId === u.id ? (
                              <div className="flex items-center gap-2">
                                <select
                                  value={editRole}
                                  onChange={(e) =>
                                    setEditRole(e.target.value as UserRole)
                                  }
                                  className="rounded-md border-gray-300 text-sm shadow-sm
                                    focus:border-blue-500 focus:ring-blue-500"
                                >
                                  {USER_ROLES.map((r) => (
                                    <option key={r.value} value={r.value}>
                                      {r.label}
                                    </option>
                                  ))}
                                </select>
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleUpdateRole(u.id, editRole)
                                  }
                                  disabled={actionInProgress === u.id}
                                  className="px-2 py-1 text-xs font-medium text-white
                                    bg-blue-600 rounded hover:bg-blue-700
                                    disabled:opacity-50"
                                >
                                  Save
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setEditingUserId(null)}
                                  className="px-2 py-1 text-xs text-gray-600
                                    hover:text-gray-900"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <span
                                className={`inline-flex items-center px-2.5 py-0.5
                                  rounded-full text-xs font-medium ${
                                    u.role === "admin"
                                      ? "bg-purple-100 text-purple-800"
                                      : u.role === "operator"
                                      ? "bg-blue-100 text-blue-800"
                                      : "bg-gray-100 text-gray-700"
                                  }`}
                              >
                                {u.role}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {new Date(u.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {u.last_login
                              ? new Date(u.last_login).toLocaleString()
                              : "Never"}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {/* Edit Role */}
                              {u.id !== currentUser?.id && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditingUserId(u.id);
                                    setEditRole(u.role as UserRole);
                                  }}
                                  className="text-xs text-blue-600 hover:text-blue-800"
                                >
                                  Edit Role
                                </button>
                              )}
                              {/* Reset Password */}
                              <button
                                type="button"
                                onClick={() => {
                                  setResetPasswordUserId(
                                    resetPasswordUserId === u.id
                                      ? null
                                      : u.id
                                  );
                                  setNewPassword("");
                                }}
                                className="text-xs text-amber-600 hover:text-amber-800"
                              >
                                Reset PW
                              </button>
                              {/* Delete */}
                              {u.id !== currentUser?.id && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleDeleteUser(u.id, u.username)
                                  }
                                  disabled={actionInProgress === u.id}
                                  className="text-xs text-red-600 hover:text-red-800
                                    disabled:opacity-50"
                                >
                                  Delete
                                </button>
                              )}
                            </div>
                            {/* Inline Password Reset */}
                            {resetPasswordUserId === u.id && (
                              <div className="mt-2 flex items-center gap-2 justify-end">
                                <input
                                  type="password"
                                  value={newPassword}
                                  onChange={(e) =>
                                    setNewPassword(e.target.value)
                                  }
                                  placeholder="New password (min 8 chars)"
                                  className="rounded-md border-gray-300 text-xs shadow-sm
                                    focus:border-blue-500 focus:ring-blue-500 w-48"
                                />
                                <button
                                  type="button"
                                  onClick={() => handleResetPassword(u.id)}
                                  disabled={actionInProgress === u.id}
                                  className="px-2 py-1 text-xs font-medium text-white
                                    bg-amber-600 rounded hover:bg-amber-700
                                    disabled:opacity-50"
                                >
                                  Set
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* ── Create User Modal ────────────────────────────────────── */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">
                  Create New User
                </h2>
              </div>
              <div className="px-6 py-4 space-y-4">
                {/* Username */}
                <div>
                  <label
                    htmlFor="create-username"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Username
                  </label>
                  <input
                    id="create-username"
                    type="text"
                    value={createForm.username}
                    onChange={(e) =>
                      setCreateForm((f) => ({
                        ...f,
                        username: e.target.value,
                      }))
                    }
                    className={`w-full rounded-md text-sm shadow-sm
                      focus:border-blue-500 focus:ring-blue-500 ${
                        createErrors.username
                          ? "border-red-300"
                          : "border-gray-300"
                      }`}
                  />
                  {createErrors.username && (
                    <p className="mt-1 text-xs text-red-600">
                      {createErrors.username}
                    </p>
                  )}
                </div>

                {/* Password */}
                <div>
                  <label
                    htmlFor="create-password"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Password
                  </label>
                  <input
                    id="create-password"
                    type="password"
                    value={createForm.password}
                    onChange={(e) =>
                      setCreateForm((f) => ({
                        ...f,
                        password: e.target.value,
                      }))
                    }
                    className={`w-full rounded-md text-sm shadow-sm
                      focus:border-blue-500 focus:ring-blue-500 ${
                        createErrors.password
                          ? "border-red-300"
                          : "border-gray-300"
                      }`}
                  />
                  {createErrors.password && (
                    <p className="mt-1 text-xs text-red-600">
                      {createErrors.password}
                    </p>
                  )}
                </div>

                {/* Role */}
                <div>
                  <label
                    htmlFor="create-role"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Role
                  </label>
                  <select
                    id="create-role"
                    value={createForm.role}
                    onChange={(e) =>
                      setCreateForm((f) => ({
                        ...f,
                        role: e.target.value as UserRole,
                      }))
                    }
                    className="w-full rounded-md border-gray-300 text-sm shadow-sm
                      focus:border-blue-500 focus:ring-blue-500"
                  >
                    {USER_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label} — {r.description}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end gap-3 rounded-b-lg">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    setCreateForm({
                      username: "",
                      password: "",
                      role: "viewer",
                    });
                    setCreateErrors({});
                  }}
                  className="px-4 py-2 text-sm font-medium text-gray-700
                    bg-white border border-gray-300 rounded-md hover:bg-gray-50
                    transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleCreateUser}
                  disabled={actionInProgress === "create"}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-sm
                    font-medium text-white bg-blue-600 hover:bg-blue-700
                    rounded-md shadow-sm disabled:opacity-50
                    disabled:cursor-not-allowed transition-colors"
                >
                  {actionInProgress === "create" ? (
                    <>
                      <LoadingSpinner size="sm" />
                      Creating…
                    </>
                  ) : (
                    "Create User"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
