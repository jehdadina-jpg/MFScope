import { useState, useMemo } from "react";
import { Search, SlidersHorizontal, RefreshCw, Sparkles, Filter } from "lucide-react";
import { useFunds } from "@/hooks/useFunds";
import { useCategories } from "@/hooks/useCategories";
import { api } from "@/lib/api";
import CategoryFilter, { type CategoryOption } from "@/components/CategoryFilter";
import FundCard from "@/components/FundCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import TopFundsSection from "@/components/TopFundsSection";
import { cn } from "@/lib/utils";

const CONVICTION_OPTIONS = [
  { value: "",            label: "All" },
  { value: "Strong Buy",  label: "Strong Buy" },
  { value: "Buy",         label: "Buy" },
  { value: "Hold",        label: "Hold" },
  { value: "Sell",        label: "Sell" },
  { value: "Strong Sell", label: "Strong Sell" },
];

const SORT_OPTIONS = [
  { value: "composite_score", label: "Score" },
  { value: "return_1y",       label: "1Y Return" },
  { value: "return_3y",       label: "3Y Return" },
  { value: "aum_crore",       label: "AUM" },
  { value: "expense_ratio",   label: "Expense Ratio" },
];

export default function HomePage() {
  // ── Filter state ──────────────────────────────────────────────────────────
  const [category,   setCategory]   = useState<string | null>(null);
  const [conviction, setConviction] = useState<string>("");
  const [search,     setSearch]     = useState<string>("");
  const [sortBy,     setSortBy]     = useState("composite_score");
  const [sortDir,    setSortDir]    = useState<"asc" | "desc">("desc");
  const [page,       setPage]       = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // ── Data ──────────────────────────────────────────────────────────────────
  const { data: categories } = useCategories();

  const query = useMemo(() => ({
    category:   category ?? undefined,
    conviction: conviction || undefined,
    search:     search || undefined,
    sort_by:    sortBy,
    sort_dir:   sortDir,
    page,
    page_size:  24,
  }), [category, conviction, search, sortBy, sortDir, page]);

  const { data, loading, error, refetch } = useFunds(query);

  // ── Category chip options ─────────────────────────────────────────────────
  const categoryOptions: CategoryOption[] = useMemo(
    () =>
      categories.map((c) => ({
        value: c.category,
        label: c.category,
        count: c.fund_count,
      })),
    [categories]
  );

  // ── Handlers ──────────────────────────────────────────────────────────────
  function handleCategoryChange(val: string | null) {
    setCategory(val);
    setPage(1);
  }

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSearch(e.target.value);
    setPage(1);
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await api.admin.refresh();
      setTimeout(() => { refetch(); setRefreshing(false); }, 1500);
    } catch {
      setRefreshing(false);
    }
  }

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;
  const hasActiveFilters = category || conviction || search;

  return (
    <div className="flex flex-col gap-8 animate-fade-in">

      {/* ── Hero Section ──────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-2xl">
        {/* Gradient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-accent/10 via-accent-bright/5 to-gradient-via/5" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-transparent" />
        
        {/* Animated glow orbs */}
        <div className="absolute top-0 left-1/4 w-64 h-64 bg-accent/20 rounded-full blur-3xl opacity-30 animate-pulse-soft" />
        <div className="absolute bottom-0 right-1/4 w-64 h-64 bg-gradient-via/20 rounded-full blur-3xl opacity-30 animate-pulse-soft" style={{ animationDelay: "1.5s" }} />

        <div className="relative backdrop-blur-sm border border-border-accent/30 rounded-2xl p-8">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-text-primary via-text-accent to-accent bg-clip-text text-transparent">
                  MFScope
                </h1>
                <div className="px-3 py-1 rounded-full bg-accent/10 border border-accent/30 backdrop-blur-sm">
                  <span className="text-xs font-semibold text-accent flex items-center gap-1">
                    <Sparkles className="w-3 h-3" />
                    AI-Powered
                  </span>
                </div>
              </div>
              <p className="text-text-secondary max-w-2xl">
                {data ? (
                  <>
                    Discover and compare <span className="font-semibold text-text-primary">{data.total.toLocaleString()}</span> mutual funds
                    {" "}with ML-powered scoring, risk assessment, and real-time insights
                  </>
                ) : (
                  "Discover and compare mutual funds with ML-powered scoring"
                )}
              </p>
            </div>
            
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-sm",
                "bg-background-elevated/50 backdrop-blur-sm border border-border",
                "hover:border-accent/50 hover:bg-accent/10 transition-all duration-300",
                "disabled:opacity-50 disabled:cursor-not-allowed group"
              )}
              aria-label="Trigger data refresh"
            >
              <RefreshCw 
                className={cn(
                  "w-4 h-4 text-text-secondary group-hover:text-accent transition-colors",
                  refreshing && "animate-spin"
                )} 
              />
              <span className="text-text-secondary group-hover:text-accent transition-colors">
                {refreshing ? "Refreshing…" : "Refresh"}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* ── Top 10 Funds Section ───────────────────────────────────────────── */}
      <TopFundsSection />

      {/* ── Filters Section ────────────────────────────────────────────────── */}
      <div className="space-y-4">
        {/* Search + Filter Toggle */}
        <div className="flex gap-3">
          <div className="relative flex-1 max-w-2xl">
            <Search
              className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted w-5 h-5"
              aria-hidden
            />
            <input
              type="search"
              placeholder="Search by fund name or AMC..."
              value={search}
              onChange={handleSearchChange}
              className="w-full pl-12 pr-4 py-3.5 text-sm rounded-xl
                         bg-background-subtle/80 backdrop-blur-md border border-border
                         text-text-primary placeholder:text-text-muted
                         focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20
                         transition-all duration-300"
              aria-label="Search funds"
            />
          </div>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={cn(
              "flex items-center gap-2 px-5 py-3.5 rounded-xl text-sm font-medium",
              "bg-background-subtle/80 backdrop-blur-md border transition-all duration-300",
              showFilters 
                ? "border-accent text-accent shadow-glow" 
                : "border-border text-text-secondary hover:border-accent/50 hover:text-text-primary"
            )}
            aria-expanded={showFilters}
            aria-label="Toggle filters"
          >
            <Filter className="w-4 h-4" aria-hidden />
            Filters
            {hasActiveFilters && (
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            )}
          </button>
        </div>

        {/* Expanded filters */}
        {showFilters && (
          <div className="space-y-4 p-5 rounded-xl bg-background-subtle/60 backdrop-blur-md 
                          border border-border animate-slide-down">
            {/* Sort options */}
            <div>
              <label className="section-label mb-3 block">Sort By</label>
              <div className="flex flex-wrap gap-2">
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      if (sortBy === opt.value) {
                        setSortDir((d) => d === "desc" ? "asc" : "desc");
                      } else {
                        setSortBy(opt.value);
                        setSortDir("desc");
                      }
                      setPage(1);
                    }}
                    className={cn(
                      "chip",
                      sortBy === opt.value && "chip-active"
                    )}
                  >
                    {opt.label}
                    {sortBy === opt.value && (
                      <span className="text-xs opacity-70">{sortDir === "desc" ? "↓" : "↑"}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Conviction filter */}
            <div>
              <label className="section-label mb-3 block">Conviction</label>
              <div className="flex flex-wrap gap-2">
                {CONVICTION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { 
                      setConviction(conviction === opt.value ? "" : opt.value); 
                      setPage(1); 
                    }}
                    className={cn(
                      "chip",
                      (conviction === opt.value || (!conviction && opt.value === "")) && "chip-active"
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Category chips */}
        <div>
          <label className="section-label mb-3 block">Category</label>
          <CategoryFilter
            options={categoryOptions}
            selected={category}
            onChange={handleCategoryChange}
          />
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner label="Loading funds…" />
        </div>
      )}
      
      {error && <ErrorMessage message={error} />}

      {!loading && !error && data && (
        <>
          {data.items.length === 0 ? (
            <div className="text-center py-20">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full 
                              bg-background-elevated/50 border border-border mb-4">
                <Search className="w-8 h-8 text-text-muted" />
              </div>
              <p className="text-text-muted text-sm">
                No funds match your filters. Try adjusting your search criteria.
              </p>
            </div>
          ) : (
            <>
              {/* Results header */}
              <div className="flex items-center justify-between">
                <p className="text-sm text-text-secondary">
                  Showing <span className="font-semibold text-text-primary">{data.items.length}</span> of{" "}
                  <span className="font-semibold text-text-primary">{data.total.toLocaleString()}</span> funds
                </p>
              </div>

              {/* Fund grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                {data.items.map((fund) => (
                  <FundCard key={fund.scheme_code} fund={fund} />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-3 pt-6">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    className={cn(
                      "px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-300",
                      "bg-background-subtle/80 backdrop-blur-md border",
                      page <= 1
                        ? "border-border text-text-muted cursor-not-allowed opacity-50"
                        : "border-border text-text-secondary hover:border-accent hover:text-accent hover:shadow-md"
                    )}
                    aria-label="Previous page"
                  >
                    ← Previous
                  </button>
                  
                  <div className="px-4 py-2.5 rounded-xl bg-accent/10 border border-accent/30 backdrop-blur-sm">
                    <span className="text-sm font-semibold text-accent">
                      {page} / {totalPages}
                    </span>
                  </div>
                  
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                    className={cn(
                      "px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-300",
                      "bg-background-subtle/80 backdrop-blur-md border",
                      page >= totalPages
                        ? "border-border text-text-muted cursor-not-allowed opacity-50"
                        : "border-border text-text-secondary hover:border-accent hover:text-accent hover:shadow-md"
                    )}
                    aria-label="Next page"
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
