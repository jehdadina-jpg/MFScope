import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { BarChart2 } from "lucide-react";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* ── Top nav ────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 text-text-primary hover:text-accent transition-colors"
          >
            <BarChart2 size={18} className="text-accent" aria-hidden />
            <span className="font-semibold text-base tracking-tight">MFScope</span>
            <span className="hidden sm:inline text-xs text-text-muted font-normal">
              India MF Intelligence
            </span>
          </Link>

          <nav className="flex items-center gap-4 text-sm text-text-secondary">
            <Link
              to="/"
              className="hover:text-text-primary transition-colors"
              aria-label="All funds"
            >
              Funds
            </Link>
            <span className="text-2xs px-2 py-0.5 rounded-badge bg-accent-dim text-accent border border-accent/30 font-medium">
              Research
            </span>
          </nav>
        </div>
      </header>

      {/* ── Main content ───────────────────────────────────────────────── */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6">
        {children}
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-border py-4 text-center text-xs text-text-muted">
        MFScope · Educational research tool · Data via AMFI &amp; public RSS feeds · Not investment advice
      </footer>
    </div>
  );
}
