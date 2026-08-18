import { useState, useEffect } from "react";
import { api, type FundDetail } from "@/lib/api";

interface UseFundDetailState {
  data: FundDetail | null;
  loading: boolean;
  error: string | null;
}

/**
 * Fetch full fund detail for a single scheme code.
 */
export function useFundDetail(schemeCode: string | undefined): UseFundDetailState {
  const [state, setState] = useState<UseFundDetailState>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!schemeCode) {
      setState({ data: null, loading: false, error: "No scheme code provided." });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    api.funds
      .detail(schemeCode)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: Error) =>
        setState({ data: null, loading: false, error: err.message })
      );
  }, [schemeCode]);

  return state;
}
