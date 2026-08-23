import { cn } from "@/lib/utils";

export default function LoadingSpinner({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 py-16 text-ink-faint", className)}>
      <div className="w-5 h-5 rounded-full border-2 border-stroke border-t-brand animate-spin" />
      {label && <span className="text-xs">{label}</span>}
    </div>
  );
}

/** Skeleton placeholder matching FundCard's shape, for grid loading states. */
export function FundCardSkeleton() {
  return (
    <div className="surface-card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 space-y-1.5">
          <div className="skeleton h-3.5 w-4/5" />
          <div className="skeleton h-2.5 w-2/5" />
        </div>
        <div className="skeleton h-7 w-16 shrink-0" />
      </div>
      <div className="skeleton h-4 w-20" />
      <div className="grid grid-cols-3 gap-2 pt-1">
        <div className="skeleton h-8" />
        <div className="skeleton h-8" />
        <div className="skeleton h-8" />
      </div>
      <div className="skeleton h-6 w-full mt-1" />
    </div>
  );
}
