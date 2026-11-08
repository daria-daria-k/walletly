import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, refreshSession, setAccessToken, setSessionLostHandler } from './api/client';
import type { User } from './api/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  const reload = useCallback(async () => setUser(await api<User>('/auth/me')), []);

  useEffect(() => {
    setSessionLostHandler(() => {
      setUser(null);
      queryClient.clear();
    });
    // При открытии страницы токена в памяти нет — пробуем восстановить сессию по cookie
    refreshSession()
      .then((ok) => (ok ? reload() : undefined))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, [queryClient, reload]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api<{ access_token: string }>('/auth/login', {
        method: 'POST',
        body: { email, password },
        noRefresh: true,
      });
      setAccessToken(tokens.access_token);
      await reload();
    },
    [reload],
  );

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      await api('/auth/register', { method: 'POST', body: { email, password, name }, noRefresh: true });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    await api('/auth/logout', { method: 'POST', noRefresh: true }).catch(() => undefined);
    setAccessToken(null);
    setUser(null);
    // Иначе следующий пользователь этого браузера на миг увидел бы чужие данные из кэша
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(() => ({ user, loading, login, register, logout, reload }), [user, loading, login, register, logout, reload]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth вне AuthProvider');
  return context;
}
