import { useQuery } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CategoryTotal, Summary, TransactionPage } from '../api/types';
import { useAuth } from '../auth';
import { State } from '../components/ui';
import { useAccounts, useCategoryGroups } from '../lib/data';
import { money, monthRange, monthTitle, shortDate } from '../lib/format';
import { useLedger } from '../ledger';

export function OverviewPage() {
  const { user } = useAuth();
  const { base, ledger } = useLedger();
  const range = monthRange();
  const { data: accounts, isLoading } = useAccounts();
  const { data: groups = [] } = useCategoryGroups();
  const { data: summary } = useQuery({ queryKey: [base, 'summary', range], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: range }) });
  const { data: categories = [] } = useQuery({ queryKey: [base, 'by-category', range], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: range }) });
  const { data: latest } = useQuery({ queryKey: [base, 'transactions', 'latest'], queryFn: () => api<TransactionPage>(`${base}/transactions`, { query: { limit: 6 } }) });

  if (isLoading) return <State>Загрузка…</State>;

  const rubAccounts = (accounts ?? []).filter((account) => account.currency === 'RUB');
  const balance = rubAccounts.reduce((sum, account) => sum + Number(account.balance), 0);
  const categoryNames = new Map(groups.flatMap((group) => group.categories.map((category) => [category.id, category.name] as const)));
  const maxCategory = Math.max(...categories.map((row) => Number(row.total)), 1);

  return (
    <div className="prototype-page page-stack">
      <div className="heading-row">
        <div>
          <p className="eyebrow">{ledger.name}</p>
          <h1>Здравствуйте, {user?.name}</h1>
          <p className="subtitle">Сводка за {monthTitle()}</p>
        </div>
      </div>
      <section className="balance-card">
        <div className="balance-main"><p>Баланс в рублях</p><h2>{money(balance)}</h2></div>
        <div className="income"><span className="metric-icon mint"><ArrowDownLeft size={20} /></span><div><p>Доходы</p><b>{money(summary?.income ?? 0)}</b></div></div>
        <div className="expense"><span className="metric-icon coral"><ArrowUpRight size={20} /></span><div><p>Расходы</p><b>{money(summary?.expense ?? 0)}</b></div></div>
      </section>
      <div className="dashboard-grid">
        <section className="card plain-card">
          <h3>Расходы по категориям</h3>
          <p>{monthTitle()}</p>
          {categories.length === 0 && <State>В этом месяце расходов пока нет</State>}
          {categories.slice(0, 6).map((row) => (
            <div className="progress-row" key={row.category_id}>
              <div><b>{row.category_name}</b><span>{money(row.total)}</span></div>
              <div className="progress"><span style={{ width: `${(Number(row.total) / maxCategory) * 100}%` }} /></div>
            </div>
          ))}
        </section>
        <section className="card plain-card">
          <h3>Последние операции</h3>
          <p><Link className="text-link" to="/transactions">Все операции →</Link></p>
          {latest?.items.length === 0 && <State>Операций пока нет</State>}
          {latest?.items.map((tx) => (
            <div className="category-line" key={tx.id}>
              <span>
                <b>{tx.description || (tx.type === 'transfer' ? 'Перевод' : categoryNames.get(tx.category_id ?? 0))}</b>
                <br />
                <small style={{ color: 'var(--muted)' }}>{shortDate(tx.tx_date)}</small>
              </span>
              <strong className={tx.type === 'income' ? 'income-text' : ''}>
                {tx.type === 'income' ? '+ ' : tx.type === 'expense' ? '− ' : ''}{money(tx.amount)}
              </strong>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
