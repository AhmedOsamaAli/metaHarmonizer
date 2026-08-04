import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { completeStudy, deleteStudy, getServerConfig, listStudies } from '../api/client';
import type { ServerConfig } from '../api/client';
import type { Study } from '../api/types';

/** Server feature flags (e.g. whether LLM matching is configured). Fetched once
 *  and cached for the session; on error callers treat features as disabled. */
export function useServerConfig() {
  return useQuery<ServerConfig>({
    queryKey: ['server-config'],
    queryFn: getServerConfig,
    staleTime: Infinity,
    retry: false,
  });
}

/** Shared, cached studies list — used by every review/quality/export page. */
export function useStudies() {
  return useQuery<Study[]>({
    queryKey: ['studies'],
    queryFn: listStudies,
  });
}

/** Permanently delete a study; refreshes the studies list. */
export function useDeleteStudy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStudy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['studies'] });
    },
  });
}

/** Mark a study completed: filed away (drops out of the work-list pickers).
 *  Refreshes the studies list. */
export function useCompleteStudy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => completeStudy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['studies'] });
    },
  });
}
