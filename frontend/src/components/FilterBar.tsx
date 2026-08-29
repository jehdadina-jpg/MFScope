import { useState } from "react";
import { Search, SlidersHorizontal, X, LayoutGrid, List } from "lucide-react";
import type { FilterOptions } from "@/lib/api";
import { cn, CONVICTION_ORDER, RISK_ORDER } from "@/lib/utils";

export interface Filters {
  category: string;
  assetClass: string;
  amc: string;
  conviction: string;
  riskLevel: string;
  planType: string;
  search: string;
  minScore: number;
  maxExpenseRatio: number | null;
  sortBy: string;
  sortDir: "asc" | "desc";
}

export const DEFAULT_FILTERS: Filters = {
  category: "",
  assetClass: "",
  amc: "",
  conviction: "",
  riskLevel: "",
  planType: "Direct",
  search: "",
  minScore: 0,
  maxExpenseRatio: null,
  sortBy: "composite_score",
  sortDir: "desc",
};

const SORT_OPTIONS = [
  { value: "composite_score", label: "Score" },
  { value: "return_1y", label: "1Y Return" },
  { value: "return_3y", label: "3Y Return" },
  { value: "sharpe_1y", label: "Sharpe" },
  { value: "risk_score", label: "Risk" },
  { value: "expense_ratio", label: "Expense Ratio" },
  { value: "aum_crore", label: "AUM" },
];

interface Props {
  options: FilterOptions | null;
  value: Filters;
  onChange: (next: Filters) => void;
  view: "grid" | "table";
  onViewChange: (v: "grid" | "table") => void;
  resultCount?: number;
}

export default function FilterBar({ options, value, onChange, view, onViewChange, resultCount }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) => onChange({ ...value, [key]: v });

  const activeCount = [
    value.assetClass,
    value.amc,
    value.conviction,
    value.riskLevel,
    value.minScore > 0 ? "score" : "",
    value.maxExpenseRatio != null ? "expense" : "",
  ].filter(Boolean).length;
  const topCategories = (options?.categories ?? []).slice(0, 9);
  const sortedAmcs = [...(options?.amcs ?? [])].sort((a, b) => a.localeCompare(b));

  return (
    <div className="flex flex-col gap-3">
      {/* Search + sort + view toggle */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input
            type="text"
            value={value.search}
            onChange={(e) => set("search", e.target.value)}
            placeholder="Search fund or AMC…"
            className="field w-full pl-9 pr-3 py-2 text-sm"
          />
          {value.search && (
            <button
              onClick={() => set("search", "")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink transition-colors"
              aria-label="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <select
          value={value.sortBy}
          onChange={(e) => set("sortBy", e.target.value)}
          className="field px-3 py-2 text-sm cursor-pointer"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>Sort: {o.label}</option>
          ))}
        </select>

        <button
          onClick={() => set("sortDir", value.sortDir === "desc" ? "asc" : "desc")}
          className="btn-ghost px-2.5 py-2"
          aria-label="Toggle sort direction"
          title={value.sortDir === "desc" ? "Descending" : "Ascending"}
        >
          {value.sortDir === "desc" ? "↓" : "↑"}
        </button>

        <button
          onClick={() => setShowAdvanced((s) => !s)}
          className={showAdvanced || activeCount > 0 ? "btn-ghost-active px-2.5 py-2" : "btn-ghost px-2.5 py-2"}
          aria-expanded={showAdvanced}
        >
          <SlidersHorizontal size={14} />
          {activeCount > 0 && <span className="num text-2xs">{activeCount}</span>}
        </button>

        <div className="flex rounded-lg border border-stroke overflow-hidden shrink-0">
          <button
            onClick={() => onViewChange("grid")}
            className={cn("px-2.5 py-2 transition-colors duration-150", view === "grid" ? "bg-brand-soft text-brand-bright" : "text-ink-faint hover:text-ink hover:bg-surface-raised")}
            aria-label="Grid view"
          >
            <LayoutGrid size={14} />
          </button>
          <button
            onClick={() => onViewChange("table")}
            className={cn("px-2.5 py-2 transition-colors duration-150", view === "table" ? "bg-brand-soft text-brand-bright" : "text-ink-faint hover:text-ink hover:bg-surface-raised")}
            aria-label="Table view"
          >
            <List size={14} />
          </button>
        </div>
      </div>

      {/* Category pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          onClick={() => set("category", "")}
          className="chip"
          data-active={value.category === ""}
        >
          All categories
        </button>
        {topCategories.map((c) => (
          <button
            key={c.category}
            onClick={() => set("category", value.category === c.category ? "" : c.category)}
            className="chip"
            data-active={value.category === c.category}
          >
            {c.category}
            <span className="num text-ink-faint">{c.fund_count}</span>
          </button>
        ))}
      </div>

      {/* Advanced filters */}
      {showAdvanced && (
        <div className="surface-card p-3 flex flex-col gap-3 animate-fade-up">
          <div className="flex flex-wrap items-center gap-2">
            <FilterSelect
              label="Asset class"
              value={value.assetClass}
              onChange={(v) => set("assetClass", v)}
              options={options?.asset_classes ?? []}
            />
            <FilterSelect
              label="AMC"
              value={value.amc}
              onChange={(v) => set("amc", v)}
              options={sortedAmcs}
            />
            <FilterSelect
              label="Conviction"
              value={value.conviction}
              onChange={(v) => set("conviction", v)}
              options={[...CONVICTION_ORDER]}
            />
            <FilterSelect
              label="Risk"
              value={value.riskLevel}
              onChange={(v) => set("riskLevel", v)}
              options={[...RISK_ORDER]}
            />
            <FilterSelect
              label="Plan"
              value={value.planType}
              onChange={(v) => set("planType", v)}
              options={options?.plan_types ?? ["Direct", "Regular"]}
            />
            {activeCount > 0 && (
              <button
                onClick={() =>
                  onChange({
                    ...value,
                    assetClass: "",
                    amc: "",
                    conviction: "",
                    riskLevel: "",
                    minScore: 0,
                    maxExpenseRatio: null,
                  })
                }
                className="text-2xs text-ink-faint hover:text-ink transition-colors ml-auto"
              >
                Clear filters
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-5 pt-2.5 border-t border-stroke">
            <label className="flex items-center gap-2.5 text-xs text-ink-dim">
              <span className="shrink-0">
                Min score <span className="num text-ink">{value.minScore}</span>
              </span>
              <input
                type="range"
                min={0}
                max={90}
                step={5}
                value={value.minScore}
                onChange={(e) => set("minScore", Number(e.target.value))}
                className="slider w-32"
              />
            </label>

            <label className="flex items-center gap-2.5 text-xs text-ink-dim">
              <span className="shrink-0">
                Max expense{" "}
                <span className="num text-ink">
                  {value.maxExpenseRatio != null ? `${value.maxExpenseRatio.toFixed(1)}%` : "any"}
                </span>
              </span>
              <input
                type="range"
                min={0.1}
                max={3}
                step={0.1}
                value={value.maxExpenseRatio ?? 3}
                onChange={(e) => set("maxExpenseRatio", Number(e.target.value))}
                className="slider w-32"
              />
              {value.maxExpenseRatio != null && (
                <button
                  onClick={() => set("maxExpenseRatio", null)}
                  className="text-ink-faint hover:text-ink transition-colors"
                  aria-label="Clear expense ratio cap"
                >
                  <X size={12} />
                </button>
              )}
            </label>
          </div>
        </div>
      )}

      {resultCount !== undefined && (
        <div className="text-2xs text-ink-faint">
          <span className="num">{resultCount.toLocaleString("en-IN")}</span> funds match
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="field px-2.5 py-1.5 text-xs cursor-pointer"
    >
      <option value="">{label}: All</option>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}
