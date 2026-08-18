import { cn } from "@/lib/utils";

export interface CategoryOption {
  value: string;
  label: string;
  count?: number;
}

interface CategoryFilterProps {
  options: CategoryOption[];
  selected: string | null;
  onChange: (value: string | null) => void;
  className?: string;
}

/** Horizontal scrollable row of pill-style filter chips. */
export default function CategoryFilter({
  options,
  selected,
  onChange,
  className,
}: CategoryFilterProps) {
  return (
    <div
      className={cn(
        "flex gap-2 overflow-x-auto pb-1 scrollbar-thin",
        className
      )}
      role="group"
      aria-label="Filter by category"
    >
      {/* "All" chip */}
      <button
        onClick={() => onChange(null)}
        className={cn("chip", selected === null && "chip-active")}
        aria-pressed={selected === null}
      >
        All
      </button>

      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value === selected ? null : opt.value)}
          className={cn("chip whitespace-nowrap", selected === opt.value && "chip-active")}
          aria-pressed={selected === opt.value}
        >
          {opt.label}
          {opt.count != null && (
            <span className="text-2xs opacity-60">({opt.count})</span>
          )}
        </button>
      ))}
    </div>
  );
}
