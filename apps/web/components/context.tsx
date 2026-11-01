"use client";
import { createContext, useContext } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
export const AppContext = createContext<{
  me: Me;
  notify: (message: string, error?: boolean) => void;
}>({ me: null as unknown as Me, notify: () => {} });
export const useApp = () => useContext(AppContext);
export function useResource<T>(path: string, interval?: number) {
  const { me } = useApp();
  return useQuery<T>({
    queryKey: [me.organization_id, path],
    queryFn: () =>
      api<T>(path, { headers: { "X-Organization-ID": me.organization_id } }),
    refetchInterval: interval,
    retry: false,
  });
}
export function useAction<T = unknown, V = void>(
  action: (value: V) => Promise<T>,
  success?: string,
) {
  const client = useQueryClient();
  const { notify } = useApp();
  return useMutation({
    mutationFn: action,
    onSuccess: () => {
      client.invalidateQueries();
      if (success) notify(success);
    },
    onError: (e: Error) => notify(e.message, true),
  });
}
