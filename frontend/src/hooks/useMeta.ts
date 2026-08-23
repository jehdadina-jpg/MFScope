import { useState, useEffect } from "react";
import { api, type UniverseStats, type FilterOptions } from "@/lib/api";

/** One-shot fetch of universe stats — the dashboard header numbers. */
export function useStats() {
  const [data, setData] = useState<UniverseStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta
      .stats()
      .then((d) => { setData(d); setLoading(false); })
      .catch((err: Error) => { setError(err.message); setLoading(false); });
  }, []);

  return { data, loading, error };
}

/** Categories, AMCs, and enum vocab for every filter control on one screen. */
export function useFilterOptions() {
  const [data, setData] = useState<FilterOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta
      .filters()
      .then((d) => { setData(d); setLoading(false); })
      .catch((err: Error) => { setError(err.message); setLoading(false); });
  }, []);

  return { data, loading, error };
}
