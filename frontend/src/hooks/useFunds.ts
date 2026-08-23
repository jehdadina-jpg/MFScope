import { useState, useEffect, useCallback, useRef } from "react";
import { api, type FundCard, type Page, type FundsQuery } from "@/lib/api";

interface UseFundsState {
  data: Page<FundCard> | null;
  loading: boolean;
  error: string | null;
}

/**
 * Paginated fund list. Re-fetches when the query changes; a request that
 * resolves after a newer one has already landed is discarded, so fast
 * filter/sort clicks never flash stale results back onto the screen.
 */
export function useFunds(query: FundsQuery = {}): UseFundsState & { refetch: () => void } {
  const [state, setState] = useState<UseFundsState>({ data: null, loading: true, error: null });
  const queryKey = JSON.stringify(query);
  const requestId = useRef(0);

  const fetch_ = useCallback(() => {
    const id = ++requestId.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.funds
      .list(query)
      .then((data) => {
        if (id === requestId.current) setState({ data, loading: false, error: null });
      })
      .catch((err: Error) => {
        if (id === requestId.current) setState({ data: null, loading: false, error: err.message });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  useEffect(() => {
    fetch_();
  }, [fetch_]);

  return { ...state, refetch: fetch_ };
}
