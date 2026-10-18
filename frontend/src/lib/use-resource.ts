"use client";
import { useCallback, useEffect, useState } from "react";
import { request, errorMessage } from "./api";
import { useApp } from "@/components/providers";

export function useResource<T>(path: string | null) {
  const { ready, user } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(x => x + 1), []);
  useEffect(() => {
    if (!ready || !path) { setLoading(!ready); return; }
    let active = true;
    setLoading(true); setError("");
    request<T>(path).then(value => { if (active) setData(value); }).catch(e => { if (active) setError(errorMessage(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, ready, user?.id, revision]);
  return { data, loading, error, reload };
}
