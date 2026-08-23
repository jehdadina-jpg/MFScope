import { useState, useEffect } from "react";
import { api, type FundDetail } from "@/lib/api";

interface UseFundDetailState {
  data: FundDetail | null;
  loading: boolean;
  error: string | null;
}

export function useFundDetail(schemeCode: string | undefined, days = 1095): UseFundDetailState {
  const [state, setState] = useState<UseFundDetailState>({ data: null, loading: true, error: null });

  useEffect(() => {
    if (!schemeCode) {
      setState({ data: null, loading: false, error: "No scheme code provided." });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.funds
      .detail(schemeCode, days)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((err: Error) => { if (!cancelled) setState({ data: null, loading: false, error: err.message }); });
    return () => { cancelled = true; };
  }, [schemeCode, days]);

  return state;
}
