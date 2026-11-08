import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { AdminStats, AdminUser } from '../api/types';
import { useAuth } from '../auth';
import { ErrorNote, Metric, PageHeading, State } from '../components/ui';

export function AdminPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const isAdmin = user?.role === 'admin';

  const { data: stats } = useQuery({ queryKey: ['admin', 'stats'], queryFn: () => api<AdminStats>('/admin/stats'), enabled: isAdmin });
  const { data: page, isLoading } = useQuery({
    queryKey: ['admin', 'users', search],
    queryFn: () => api<{ items: AdminUser[]; total: number }>('/admin/users', { query: { search, limit: 100 } }),
    enabled: isAdmin,
  });

  if (!isAdmin) return <Navigate to="/" replace />;

  async function update(target: AdminUser, body: Partial<AdminUser>) {
    setError(null);
    try {
      await api(`/admin/users/${target.id}`, { method: 'PATCH', body });
      await queryClient.invalidateQueries({ queryKey: ['admin'] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Администрирование" title="Пользователи" />
      <div className="summary-strip four">
        <Metric label="Всего" value={String(stats?.users_total ?? '—')} />
        <Metric label="Активных" value={String(stats?.users_active ?? '—')} />
        <Metric label="Premium" value={String(stats?.users_premium ?? '—')} />
        <Metric label="Операций" value={String(stats?.transactions_total ?? '—')} />
      </div>
      <ErrorNote text={error} />
      <section className="card data-card">
        <div className="filterbar"><div className="filter-search"><Search size={17} /><input aria-label="Поиск пользователя" placeholder="Email или имя" value={search} onChange={(e) => setSearch(e.target.value)} /></div></div>
        {isLoading ? <State>Загрузка…</State> : (
          <div className="admin-table">
            <div className="table-head"><span>Email</span><span>Имя</span><span>Роль</span><span>Тариф</span><span>Статус</span><span /></div>
            {page?.items.map((item) => (
              <div className="table-row" key={item.id}>
                <span>{item.email}</span>
                <span>{item.name}</span>
                <span>{item.role}</span>
                <span>{item.plan}</span>
                <span>{item.is_active ? 'Активен' : 'Заблокирован'}</span>
                <div className="row-actions">
                  <button className="small-button" disabled={item.id === user?.id} onClick={() => update(item, { is_active: !item.is_active })}>{item.is_active ? 'Блок.' : 'Разблок.'}</button>
                  <button className="small-button" disabled={item.id === user?.id} onClick={() => update(item, { role: item.role === 'admin' ? 'user' : 'admin' })}>Роль</button>
                  <button className="small-button" onClick={() => update(item, { plan: item.plan === 'free' ? 'premium' : 'free' })}>Тариф</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
