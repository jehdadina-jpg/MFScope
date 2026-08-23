import { Link, useLocation } from "react-router-dom";
import { LineChart } from "lucide-react";
import { useStats } from "@/hooks/useMeta";
import { fmtDateShort } from "@/lib/utils";

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { data: stats } = useStats();
  const isHome = location.pathname === "/";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b border-stroke bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto max-w-[1400px] px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2 shrink-0 group">
            <span className="grid place-items-center w-7 h-7 rounded-md bg-brand text-white transition-transform duration-150 ease-out group-active:scale-90">
              <LineChart size={15} strokeWidth={2.5} />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">MFScope</span>
          </Link>

          <div className="hidden md:flex items-center gap-1 text-2xs text-ink-faint">
            {stats && (
              <>
                <span className="num text-ink-dim">{stats.investable_schemes.toLocaleString("en-IN")}</span>
                <span>funds scored</span>
                <span className="mx-2 text-stroke-strong">·</span>
                <span>NAV as of</span>
                <span className="num text-ink-dim">{fmtDateShort(stats.latest_nav_date)}</span>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-ink-faint hover:text-ink-dim transition-colors duration-150 hidden sm:block"
            >
              API
            </a>
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 sm:px-6 py-6">{children}</main>

      {isHome && (
        <footer className="border-t border-stroke mt-12">
          <div className="mx-auto max-w-[1400px] px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-2xs text-ink-faint">
            <span>MFScope — independent research tooling. Not investment advice.</span>
            <span>Data: AMFI · mfapi.in</span>
          </div>
        </footer>
      )}
    </div>
  );
}
