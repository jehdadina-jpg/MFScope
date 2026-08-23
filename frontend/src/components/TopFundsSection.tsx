import { useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { api, type FundCard as FundCardType } from "@/lib/api";
import FundCard from "./FundCard";
import { FundCardSkeleton } from "./LoadingSpinner";

export default function TopFundsSection() {
  const [funds, setFunds] = useState<FundCardType[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.scores
      .top({ limit: 6 })
      .then(setFunds)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return null;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Trophy size={15} className="text-warn" />
        <h2 className="text-sm font-semibold text-ink">Top-ranked funds</h2>
        <span className="text-2xs text-ink-faint">highest score among peers with 20+ competitors</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {funds
          ? funds.map((f, i) => (
              <FundCard key={f.id} fund={f} className="animate-fade-up" style={{ animationDelay: `${i * 40}ms` }} />
            ))
          : Array.from({ length: 6 }).map((_, i) => <FundCardSkeleton key={i} />)}
      </div>
    </section>
  );
}
