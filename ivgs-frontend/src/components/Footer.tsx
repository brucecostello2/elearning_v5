/*
 * IVGS v5 — Footer
 *
 * Displays version information and system identifier.
 * Minimal design — not intended to compete with content.
 */

export function Footer() {
  return (
    <footer className="border-t border-gray-800/50 py-3">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 text-[11px] text-gray-600 sm:px-6 lg:px-8">
        <span>IVGS v5.0 — Intelligent Video Generation System</span>
        <span>Self-Hosted • On-Premises</span>
      </div>
    </footer>
  );
}
