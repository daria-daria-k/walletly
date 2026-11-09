import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, MoreHorizontal, Search, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { AdminPayment, AdminStats, AdminUser, AuditEntry, PlanInfo } from '../api/types';
import { useAuth } from '../auth';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, ErrorState, LoadingState, Modal, PageHeading, State, StateCard } from '../components/ui';
import { dateTime, initials, money } from '../lib/format';

const SECTIONS = ['Дашборд', 'Пользователи', 'Тарифы', 'Платежи', 'Аудит'];

const percent = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : '—');
const planLabel = (plan: string) => (plan === 'premium' ? 'Premium' : 'Free');

function Metric({ label, value, delta }: { label: string; value: string; delta: string }) {
  return <section className="card admin-metric"><p>{label}</p><b>{value}</b><span>{delta}</span></section>;
}

function Dashboard() {
  const stats = useQuery({ queryKey: ['admin', 'stats'], queryFn: () => api<AdminStats>('/admin/stats') });
  const health = useQuery({ queryKey: ['admin', 'health'], queryFn: () => api<{ status: string; database: string }>('/health'), retry: false });

  if (stats.isLoading) return <LoadingState />;
  if (stats.isError || !stats.data) return <ErrorState onRetry={() => stats.refetch()} />;

  const data = stats.data;
  const peak = Math.max(...data.registrations.map((week) => week.count), 1);
  const checkedAt = new Date(health.dataUpdatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const services = [
    { name: 'API', ok: health.data?.status === 'ok' },
    { name: 'PostgreSQL', ok: health.data?.database === 'ok' },
  ];

  return (
    <>
      <div className="admin-metrics">
        <Metric label="Пользователи" value={String(data.users_total)} delta={`+${data.users_new_30d} за 30 дней`} />
        <Metric label="Активные" value={String(data.users_active)} delta={percent(data.users_active, data.users_total)} />
        <Metric label="Premium" value={String(data.users_premium)} delta={percent(data.users_premium, data.users_total)} />
        <Metric label="Операции" value={String(data.transactions_total)} delta="Всего в сервисе" />
      </div>
      <div className="admin-grid">
        <section className="card admin-chart">
          <div className="section-head"><div><h3>Рост аудитории</h3><p>Регистрации за последние 8 недель</p></div></div>
          <div className="line-chart-mock">
            {data.registrations.map((week) => <span key={week.week_start} title={`С ${week.week_start}: ${week.count}`} style={{ height: `${(week.count / peak) * 100}%` }} />)}
          </div>
        </section>
        <section className="card system-health">
          <div className="section-head"><div><h3>Состояние системы</h3><p>Последняя проверка в {checkedAt}</p></div></div>
          {services.map((service) => (
            <div className="health-row" key={service.name}>
              <span className={service.ok ? '' : 'warning'} />
              <b>{service.name}</b>
              <em>{service.ok ? 'Работает' : 'Внимание'}</em>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function downloadCsv(users: AdminUser[]) {
  // Точка с запятой и BOM: так русский Excel сразу разбирает колонки и кодировку
  const quote = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const rows = users.map((u) => [u.email, u.name, u.role, u.plan, u.is_active ? 'Активен' : 'Заблокирован', u.created_at.slice(0, 10)].map(quote).join(';'));
  const blob = new Blob([`﻿Email;Имя;Роль;Тариф;Статус;Регистрация\n${rows.join('\n')}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'walletly-users.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function UserModal({ target, onClose }: { target: AdminUser; onClose: () => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const isSelf = target.id === user?.id;

  async function update(body: Partial<AdminUser>) {
    setError(null);
    try {
      await api(`/admin/users/${target.id}`, { method: 'PATCH', body });
      await queryClient.invalidateQueries({ queryKey: ['admin'] });
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function toggleBlock() {
    const question = target.is_active ? `Заблокировать ${target.email}? Все сессии будут завершены.` : `Разблокировать ${target.email}?`;
    if (window.confirm(question)) update({ is_active: !target.is_active });
  }

  return (
    <Modal eyebrow="Пользователь" title={target.name} onClose={onClose}>
      <div className="admin-actions">
        <p>{target.email} · {target.role === 'admin' ? 'Администратор' : 'Пользователь'} · {planLabel(target.plan)}</p>
        <ErrorNote text={error} />
        <button className="secondary-button" onClick={() => update({ plan: target.plan === 'free' ? 'premium' : 'free' })}>Сменить тариф на {planLabel(target.plan === 'free' ? 'premium' : 'free')}</button>
        <button className="secondary-button" disabled={isSelf} onClick={() => update({ role: target.role === 'admin' ? 'user' : 'admin' })}>{target.role === 'admin' ? 'Снять роль администратора' : 'Сделать администратором'}</button>
        <button className="danger-button" disabled={isSelf} onClick={toggleBlock}>{target.is_active ? 'Заблокировать' : 'Разблокировать'}</button>
      </div>
    </Modal>
  );
}

function Users() {
  const [search, setSearch] = useState('');
  const [plan, setPlan] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'users', search, plan],
    queryFn: () => api<{ items: AdminUser[]; total: number }>('/admin/users', { query: { search, plan, limit: 200 } }),
  });
  const selected = data?.items.find((item) => item.id === selectedId);

  return (
    <section className="card admin-users">
      <div className="admin-toolbar">
        <div className="filter-search"><Search size={17} /><input aria-label="Поиск пользователя" placeholder="Имя или email" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <StyledSelect ariaLabel="Тариф" value={plan} onChange={setPlan} options={[{ value: '', label: 'Все тарифы' }, { value: 'free', label: 'Free' }, { value: 'premium', label: 'Premium' }]} />
        <button className="secondary-button" disabled={!data?.items.length} onClick={() => data && downloadCsv(data.items)}><Download size={16} />Экспорт</button>
      </div>
      {isLoading ? <LoadingState /> : isError ? <ErrorState onRetry={() => refetch()} /> : (
        <>
          <div className="admin-user-head"><span>Пользователь</span><span>Тариф</span><span>Статус</span><span>Регистрация</span><span /></div>
          {data?.items.map((item) => (
            <div className="admin-user-row" key={item.id}>
              <div><span>{initials(item.name)}</span><div><b>{item.name}</b><small>{item.email}</small></div></div>
              <em>{planLabel(item.plan)}</em>
              <strong className={item.is_active ? '' : 'blocked'}>{item.is_active ? 'Активен' : 'Заблокирован'}</strong>
              <span>{new Date(item.created_at).toLocaleDateString('ru-RU')}</span>
              <button aria-label={`Действия: ${item.email}`} onClick={() => setSelectedId(item.id)}><MoreHorizontal size={18} /></button>
            </div>
          ))}
          {data?.items.length === 0 && <State>Никого не найдено</State>}
        </>
      )}
      {selected && <UserModal target={selected} onClose={() => setSelectedId(null)} />}
    </section>
  );
}

function Audit() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ['admin', 'audit'], queryFn: () => api<AuditEntry[]>('/admin/audit') });
  if (isLoading) return <LoadingState />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;
  return (
    <section className="card">
      <div className="section-head" style={{ padding: 18 }}><div><h3>Журнал действий</h3><p>Последние 100 записей. Записи нельзя изменить или удалить</p></div></div>
      {data?.length === 0 ? <State>Действий пока не было</State> : data?.map((entry) => (
        <div className="audit-row" key={entry.id}>
          <small>{dateTime(entry.created_at)}</small>
          <div><b>{entry.target_email}</b> <small>· {entry.actor_email}</small></div>
          <em>{entry.detail}</em>
        </div>
      ))}
    </section>
  );
}

function Plans() {
  const { data } = useQuery({ queryKey: ['billing-plan'], queryFn: () => api<PlanInfo>('/billing/plan') });
  return (
    <div className="admin-plans">
      <section className="card"><h3>Free</h3><h2>0 ₽</h2><p>Счета, операции, семья, одна копилка, подсказки на правилах, импорт и экспорт Excel.</p></section>
      <section className="card"><h3>Premium</h3><h2>{data ? money(data.price) : '…'}<small> / {data?.period_days ?? 30} дней</small></h2><p>Копилки без ограничений, умные категории и прогнозы, Telegram-бот, разбор выписок. Цена задаётся в PREMIUM_PRICE_RUB.</p></section>
    </div>
  );
}

const PAYMENT_LABEL: Record<AdminPayment['status'], string> = { pending: 'Ожидает', succeeded: 'Оплачен', canceled: 'Отменён' };

function Payments() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ['admin', 'payments'], queryFn: () => api<AdminPayment[]>('/admin/payments') });
  if (isLoading) return <LoadingState />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;
  if (!data?.length) return <StateCard icon="💳" title="Платежей пока нет" text="Здесь появятся оплаты подписки." />;
  return (
    <section className="card">
      {data.map((item) => <div className="audit-row" key={item.id}><small>{dateTime(item.created_at)}</small><span>{item.email} · {money(item.amount)}</span><em>{PAYMENT_LABEL[item.status]}</em></div>)}
    </section>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [section, setSection] = useState('Дашборд');

  if (user?.role !== 'admin') {
    return (
      <StateCard icon="🔒" title="Нет доступа" text="Для просмотра раздела нужны права администратора.">
        <button className="secondary-button" onClick={() => navigate('/')}>Вернуться назад</button>
      </StateCard>
    );
  }

  return (
    <div className="prototype-page admin-page">
      <div className="admin-banner">
        <ShieldCheck />
        <div><b>Режим администратора</b><span>Действия записываются в журнал аудита</span></div>
        <button onClick={() => navigate('/')}>Выйти из режима</button>
      </div>
      <PageHeading eyebrow="Управление Walletly" title="Административная панель" subtitle="Пользователи, подписки и состояние сервиса." />
      <div className="admin-tabs">
        {SECTIONS.map((item) => <button key={item} className={section === item ? 'active' : ''} onClick={() => setSection(item)}>{item}</button>)}
      </div>
      {section === 'Дашборд' && <Dashboard />}
      {section === 'Пользователи' && <Users />}
      {section === 'Аудит' && <Audit />}
      {section === 'Тарифы' && <Plans />}
      {section === 'Платежи' && <Payments />}
    </div>
  );
}
