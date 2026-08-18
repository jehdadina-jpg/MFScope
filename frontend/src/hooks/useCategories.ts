import { useState, useEffect } from "react";
import { api, type CategorySummary } from "@/lib/api";

export function useCategories() {
  const [data, setData] = useState<CategorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.categories
      .list()
      .then((d) => { setData(d); setLoading(false); })
      .catch((err: Error) => { setError(err.message); setLoading(false); });
  }, []);

  return { data, loading, error };
}
