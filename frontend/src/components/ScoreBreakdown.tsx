import type { ComponentBreakdown } from "@/lib/api";
import { COMPONENT_LABELS, cn, fmtPctPlain } from "@/lib/utils";

/**
 * Component bars for the composite score, each weighted by the share it was
 * actually given after renormalisation — the numbers on screen always add up
 * to how the score was really built, including what got dropped for lack of
 * data.
 */
export default function ScoreBreakdown({ breakdown }: { breakdown: ComponentBreakdown }) {
  const entries = Object.entries(breakdown.components).sort(
    (a, b) => (breakdown.weights[b[0]] ?? 0) - (breakdown.weights[a[0]] ?? 0)
  );

  return (
    <div className="flex flex-col gap-3">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-3">
          <span className="text-xs text-ink-dim w-32 shrink-0">{COMPONENT_LABELS[key] ?? key}</span>
          <div className="flex-1 h-2 rounded-full bg-surface-raised overflow-hidden">
            <div
              className={cn("h-full rounded-full", barColor(value))}
              style={{ width: `${Math.max(2, value)}%` }}
            />
          </div>
          <span className="num text-xs text-ink-dim w-9 text-right">{value.toFixed(0)}</span>
          <span className="num text-2xs text-ink-faint w-10 text-right">
            {fmtPctPlain((breakdown.weights[key] ?? 0) * 100)}
          </span>
        </div>
      ))}

      {breakdown.missing.length > 0 && (
        <p className="text-2xs text-ink-faint pt-1">
          No data for {breakdown.missing.map((m) => COMPONENT_LABELS[m] ?? m).join(", ")} — excluded, weights
          redistributed across the rest.
        </p>
      )}

      <p className="text-2xs text-ink-faint">
        Ranked against {breakdown.peer_count ?? "—"} peers in {breakdown.peer_group ?? "its category"} ·{" "}
        {fmtPctPlain((breakdown.data_confidence ?? 0) * 100)} data confidence
      </p>
    </div>
  );
}

function barColor(value: number): string {
  if (value >= 70) return "bg-up";
  if (value >= 40) return "bg-warn";
  return "bg-down";
}
