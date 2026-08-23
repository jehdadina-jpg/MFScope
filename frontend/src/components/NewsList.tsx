import { ExternalLink } from "lucide-react";
import type { NewsSnippet } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "bg-up",
  negative: "bg-down",
  neutral: "bg-ink-faint",
};

export default function NewsList({ items }: { items: NewsSnippet[] }) {
  if (items.length === 0) {
    return <p className="text-xs text-ink-faint">No recent news linked to this fund or its category.</p>;
  }

  return (
    <ul className="flex flex-col divide-y divide-stroke">
      {items.map((n, i) => (
        <li key={i} className="py-2.5">
          <a
            href={n.url ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="group flex items-start gap-2.5"
          >
            <span
              className={cn("mt-1.5 w-1.5 h-1.5 rounded-full shrink-0", SENTIMENT_COLOR[n.sentiment_label ?? ""] ?? "bg-ink-faint")}
            />
            <div className="min-w-0 flex-1">
              <p className="text-[13px] text-ink group-hover:text-brand-bright transition-colors duration-150 leading-snug">
                {n.title}
              </p>
              <p className="text-2xs text-ink-faint mt-0.5">
                {n.source} · {timeAgo(n.published_at)}
              </p>
            </div>
            {n.url && <ExternalLink size={12} className="text-ink-faint shrink-0 mt-1" />}
          </a>
        </li>
      ))}
    </ul>
  );
}
