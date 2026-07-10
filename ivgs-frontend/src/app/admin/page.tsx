"use client";

import React from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { useUsers } from "@/hooks/useMonitoring";
import ErrorBoundary from "@/components/ErrorBoundary";
import LoadingSpinner from "@/components/LoadingSpinner";

/**
 * Admin Landing / Dashboard Page
 *
 * Overview cards for admin-managed areas:
 * - User Management — user count by role
 * - Backup Management — quick link
 * - Retention Policies — quick link
 *
 * Per §8.0: Admin nav expands into sidebar with admin functions.
 * This page provides an overview with quick-access cards.
 */

interface AdminCard {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  stat?: string;
  statLabel?: string;
}

export default function AdminPage(): React.ReactElement {
  const { user } = useAuth();
  const { users, isLoading: usersLoading } = useUsers();

  const adminCount = users?.filter((u) => u.role === "admin").length ?? 0;
  const operatorCount = users?.filter((u) => u.role === "operator").length ?? 0;
  const viewerCount = users?.filter((u) => u.role === "viewer").length ?? 0;
  const totalUsers = users?.length ?? 0;

  const cards: AdminCard[] = [
    {
      title: "User Management",
      description:
        "Manage user accounts, roles, and access permissions. Create, edit, and delete user accounts.",
      href: "/admin/users",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
        </svg>
      ),
      stat: usersLoading ? "..." : String(totalUsers),
      statLabel: "Total Users",
    },
    {
      title: "Backup Management",
      description:
        "Monitor and trigger automated backups. Verify backup integrity and manage restore points.",
      href: "/admin/backups",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
        </svg>
      ),
      stat: "§14",
      statLabel: "Backup & DR",
    },
    {
      title: "Retention Policies",
      description:
        "Configure storage tier lifecycle rules. Manage Hot → Warm → Cold → Archive transitions.",
      href: "/admin/retention",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      ),
      stat: "§10.4",
      statLabel: "Lifecycle Rules",
    },
    {
      title: "Node Configuration",
      description:
        "View and stage the cluster node IP addresses (NODE_01_IP through NODE_06_IP). Changes are staged and take effect after a stack restart.",
      href: "/admin/nodes",
      icon: (
        <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 0 1-3-3m3 3a3 3 0 1 0 0 6h13.5a3 3 0 1 0 0-6m-16.5-3a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3m-19.5 0a4.5 4.5 0 0 1 .9-2.7L5.737 5.1a3.375 3.375 0 0 1 2.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 0 1 .9 2.7m0 0a3 3 0 0 1-3 3m0 3h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Zm-3 6h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Z" />
        </svg>
      ),
      stat: "§2.3",
      statLabel: "Node IPs",
    },
  ];

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Administration</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            System administration and configuration. Welcome, {user?.username}.
          </p>
        </div>

        {/* Quick stats bar */}
        {!usersLoading && users && (
          <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalUsers}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Total Users</p>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-red-600 dark:text-red-400">{adminCount}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Admins</p>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{operatorCount}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Operators</p>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">{viewerCount}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">Viewers</p>
            </div>
          </div>
        )}

        {/* Admin area cards */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((card) => (
            <Link
              key={card.href}
              href={card.href}
              className="group rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 transition-all hover:border-ivgs-600/50 hover:bg-gray-100 dark:hover:bg-gray-800/50"
            >
              <div className="flex items-start justify-between">
                <div className="text-ivgs-600 dark:text-ivgs-400 transition-colors group-hover:text-ivgs-800 dark:group-hover:text-ivgs-300">
                  {card.icon}
                </div>
                {card.stat && (
                  <div className="text-right">
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">{card.stat}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400">{card.statLabel}</p>
                  </div>
                )}
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white group-hover:text-ivgs-800 dark:group-hover:text-ivgs-300">
                {card.title}
              </h3>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{card.description}</p>
              <div className="mt-4 flex items-center text-sm text-ivgs-600 dark:text-ivgs-400 group-hover:text-ivgs-800 dark:group-hover:text-ivgs-300">
                <span>Open</span>
                <svg className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </ErrorBoundary>
  );
}
