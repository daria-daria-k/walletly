import { useQuery } from '@tanstack/react-query';
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { api } from './api/client';
import type { Ledger } from './api/types';

interface LedgerState {
  ledgers: Ledger[];
  ledger: Ledger;
  base: string; // префикс API текущего пространства
  canManage: boolean;
  select: (id: number) => void;
}

const LedgerContext = createContext<LedgerState | null>(null);
const STORAGE_KEY = 'walletly-ledger';

function storedId(): number | null {
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

export function LedgerProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<number | null>(storedId);
  const { data: ledgers, isLoading, isError } = useQuery({ queryKey: ['ledgers'], queryFn: () => api<Ledger[]>('/ledgers') });

  const value = useMemo<LedgerState | null>(() => {
    if (!ledgers?.length) return null;
    // Сохранённого пространства может уже не быть: из него вышли или его удалили
    const ledger = ledgers.find((item) => item.id === selected) ?? ledgers[0];
    return {
      ledgers,
      ledger,
      base: `/ledgers/${ledger.id}`,
      canManage: ledger.role !== 'member',
      select: (id) => {
        setSelected(id);
        try {
          localStorage.setItem(STORAGE_KEY, String(id));
        } catch {
          // Без localStorage выбор просто не переживёт перезагрузку
        }
      },
    };
  }, [ledgers, selected]);

  if (isLoading) return <div className="state">Загрузка…</div>;
  if (isError || !value) return <div className="state">Не удалось загрузить данные. Обновите страницу.</div>;
  return <LedgerContext.Provider value={value}>{children}</LedgerContext.Provider>;
}

export function useLedger() {
  const context = useContext(LedgerContext);
  if (!context) throw new Error('useLedger вне LedgerProvider');
  return context;
}
