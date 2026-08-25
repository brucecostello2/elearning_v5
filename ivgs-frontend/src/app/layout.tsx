/*
 * IVGS v5 — Root Layout
 *
 * Per §8: Unified Next.js 14 application served on node-01 via Nginx.
 * Provides AuthProvider context, Header navigation, and global styling.
 *
 * Layout hierarchy:
 *   <html> → <body> → <AuthProvider> → <Header> → <main>{children}</main> → <Footer>
 */

import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ToastProvider } from "@/components/Toast";
import "@/app/globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "IVGS v5 Dashboard",
    template: "%s | IVGS v5",
  },
  description:
    "Intelligent Video Generation System — Content creation and operational monitoring dashboard",
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Apply the stored/system theme before hydration (no flash). */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('ivgs-theme');if(t!=='light'&&t!=='dark'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}document.documentElement.classList.toggle('dark',t==='dark');}catch(e){document.documentElement.classList.add('dark');}",
          }}
        />
      </head>
      {/*
        WP-43 Task 4. This className used to carry each dark utility TWICE,
        with contradictory values:

          ... dark:bg-gray-950 ... dark:bg-gray-50 dark:bg-gray-950
          ... dark:text-gray-100 ... dark:text-gray-900 dark:text-gray-100

        Attribute order does not decide a Tailwind conflict -- sheet order
        does, and Tailwind emits colour utilities by ascending shade. In the
        deployed bundle (/app/.next/static/css/23624bb2737bd75a.css) that put
        `dark:text-gray-900` at byte 55113, after `dark:text-gray-100` at
        54618, and `dark:bg-gray-950` at 52808, after `dark:bg-gray-50` at
        51982. So in dark mode the body painted rgb(17 24 39) text on
        rgb(3 7 18) -- near-black on near-black.

        Every normal page sets its own text colours on inner elements, which
        is why the only thing that ever looked blank was the one surface that
        INHERITS from body: Next's built-in 404, served for the Prompts tab,
        which had no page component. Both halves are fixed -- there is now a
        real not-found.tsx and a real Prompts page -- and the body no longer
        contradicts itself either way.
      */}
      <body className="min-h-screen bg-gray-50 dark:bg-gray-950 font-sans text-gray-900 dark:text-gray-100 antialiased">
        <ThemeProvider>
        <AuthProvider>
          <ToastProvider>
            <div className="flex min-h-screen flex-col">
              <Header />
              <main className="flex-1">{children}</main>
              <Footer />
            </div>
          </ToastProvider>
        </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
