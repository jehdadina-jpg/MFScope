import { useMemo, useState } from "react";
import { useFunds } from "@/hooks/useFunds";
import { useFilterOptions, useStats } from "@/hooks/useMeta";
import { useDebounce } from "@/hooks/useDebounce";
import StatBar from "@/components/StatBar";
import FilterBar, { DEFAULT_FILTERS, type Filters } from "@/components/FilterBar";
import FundCard from "@/components/FundCard";
import FundRow from "@/components/FundRow";
import { FundCardSkeleton } from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import Pagination from "@/components/Pagination";
import TopFundsSection from "@/components/TopFundsSection";

const PAGE_SIZE = 24;

export default function HomePage() {
  const { data: stats } = useStats();
  const { data: filterOptions } = useFilterOptions();

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [view, setView] = useState<"grid" | "table">("grid");

  const debouncedSearch = useDebounce(filters.search, 300);

  const query = useMemo(
    () => ({
      category: filters.category || undefined,
      asset_class: filters.assetClass || undefined,
      conviction: filters.conviction || undefined,
      risk_level: filters.riskLevel || undefined,
      plan_type: filters.planType || undefined,
      search: debouncedSearch || undefined,
      sort_by: filters.sortBy,
      sort_dir: filters.sortDir,
      page,
      page_size: PAGE_SIZE,
    }),
    [filters, debouncedSearch, page]
  );

  const { data, loading, error } = useFunds(query);

  function handleFiltersChange(next: Filters) {
    setFilters(next);
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-1.5 pt-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Indian mutual funds, ranked honestly</h1>
        <p className="text-sm text-ink-dim max-w-2xl">
          Every score is a percentile against real peers — same category, same plan type — with the exact math shown on
          each fund's page. No fund is scored on data it doesn't have.
        </p>
      </section>

      <StatBar stats={stats} />

      <TopFundsSection />

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Browse all funds</h2>
        </div>

        <FilterBar
          options={filterOptions}
          value={filters}
          onChange={handleFiltersChange}
          view={view}
          onViewChange={setView}
          resultCount={data?.total}
        />

        {error && <ErrorMessage message={error} />}

        {!error && view === "grid" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {loading && !data
              ? Array.from({ length: PAGE_SIZE }).map((_, i) => <FundCardSkeleton key={i} />)
              : data?.items.map((f) => <FundCard key={f.id} fund={f} />)}
          </div>
        )}

        {!error && view === "table" && data && (
          <div className="surface-card overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-2xs text-ink-faint border-b border-stroke">
                  <th className="py-2.5 pl-4 pr-3 font-medium">Fund</th>
                  <th className="py-2.5 px-3 font-medium hidden lg:table-cell">Trend</th>
                  <th className="py-2.5 px-3 font-medium text-right">1Y</th>
                  <th className="py-2.5 px-3 font-medium text-right hidden sm:table-cell">3Y CAGR</th>
                  <th className="py-2.5 px-3 font-medium text-right hidden md:table-cell">Sharpe</th>
                  <th className="py-2.5 px-3 font-medium text-right hidden md:table-cell">Expense</th>
                  <th className="py-2.5 px-3 font-medium text-right hidden lg:table-cell">AUM</th>
                  <th className="py-2.5 px-3 font-medium hidden sm:table-cell">Risk</th>
                  <th className="py-2.5 pl-3 pr-4 font-medium">Score</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((f) => (
                  <FundRow key={f.id} fund={f} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!error && data && !loading && data.items.length === 0 && (
          <div className="surface-card p-10 text-center text-sm text-ink-faint">
            No funds match these filters. Try widening the category or clearing a filter.
          </div>
        )}

        {data && <Pagination page={page} totalPages={data.total_pages} onChange={setPage} />}
      </section>
    </div>
  );
}
