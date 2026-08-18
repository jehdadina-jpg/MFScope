import { useState, useEffect, useCallback } from "react";
import { api, type FundCard, type Page, type FundsQuery } from "@/lib/api";

interface UseFundsState {
  data: Page<FundCard> | null;
  loading: boolean;
  error: string | null;
}

/**
 * Paginated fund list hook.
 * Re-fetches whenever the query object reference changes.
 * Caller should memoize or stabilise query if needed.
 */
export function useFunds(query: FundsQuery = {}): UseFundsState & { refetch: () => void } {
  const [state, setState] = useState<UseFundsState>({
    data: null,
    loading: true,
    error: null,
  });

  // Serialise query so we can use it as a dependency
  const queryKey = JSON.stringify(query);

  const fetch_ = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api.funds
      .list(query)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: Error) =>
        setState({ data: null, loading: false, error: err.message })
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  useEffect(() => {
    fetch_();
  }, [fetch_]);

  return { ...state, refetch: fetch_ };
}
