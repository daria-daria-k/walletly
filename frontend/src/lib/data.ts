import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Account, CategoryGroup } from '../api/types';
import { useLedger } from '../ledger';

export function useAccounts(includeArchived = false) {
  const { base } = useLedger();
  return useQuery({
    queryKey: [base, 'accounts', includeArchived],
    queryFn: () => api<Account[]>(`${base}/accounts`, { query: { include_archived: includeArchived } }),
  });
}

export function useCategoryGroups() {
  const { base } = useLedger();
  return useQuery({ queryKey: [base, 'category-groups'], queryFn: () => api<CategoryGroup[]>(`${base}/category-groups`) });
}

// Ключи начинаются с префикса пространства: операция меняет и остатки, и аналитику,
// поэтому после записи проще обновить все данные текущего пространства
export function useRefreshLedgerData() {
  const { base } = useLedger();
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: [base] });
}
