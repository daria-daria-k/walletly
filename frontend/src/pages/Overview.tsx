import { useQuery } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowDownRight, ArrowUpRight, Plus, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { CategoryTotal, Summary, TransactionPage } from '../api/types';
import { useAuth } from '../auth';
import { useAddOperation } from '../components/Layout';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorState, LoadingState, State } from '../components/ui';
import { useAccounts, useCategoryGroups } from '../lib/data';
import { capitalize, changePercent, money, monthDative, monthRange, monthTitle, samePeriodRange, shortDate, signedPercent } from '../lib/format';
import { CategoryIcon } from '../components/CategoryIcon';
import { useLedger } from '../ledger';

const DONUT = ['var(--coral)', 'var(--purple)', 'var(--yellow)', 'var(--mint)'];
const DONUT_CLASS = ['coral-bg', 'purple-bg', 'yellow-bg', 'mint-bg'];

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return 'Доброй ночи';
  if (hour < 12) return 'Доброе утро';
  if (hour < 18) return 'Добрый день';
  return 'Добрый вечер';
}

function todayCaption() {
  const now = new Date();
  const date = now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  return `${date}, ${now.toLocaleDateString('ru-RU', { weekday: 'long' })}`;
}

function useHint(current: CategoryTotal[], previous: CategoryTotal[]) {
  const before = new Map(previous.map((row) => [row.category_id, Number(row.total)]));
  const changes = current
    .filter((row) => (before.get(row.category_id) ?? 0) > 0)
    .map((row) => {
      const was = before.get(row.category_id)!;
      return { name: row.category_name, diff: Number(row.total) - was, percent: Math.round(((Number(row.total) - was) / was) * 100) };
    })
    .filter((item) => item.percent !== 0);
  // Сначала хорошая новость: самая большая экономия, иначе самый заметный рост
  const saved = changes.filter((item) => item.diff < 0).sort((a, b) => a.diff - b.diff)[0];
  return saved ?? changes.sort((a, b) => b.diff - a.diff)[0] ?? null;
}

export function OverviewPage() {
  const { user } = useAuth();
  const { base, ledger } = useLedger();
  const openAdd = useAddOperation();
  const navigate = useNavigate();
  const [spendingOffset, setSpendingOffset] = useState(0);
  const range = monthRange();
  const previous = samePeriodRange();
  const spendingRange = monthRange(spendingOffset);

  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const { data: groups = [] } = useCategoryGroups();
  const summaryQuery = (key: string, query: object) => ({ queryKey: [base, 'summary', key, query], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: query as Record<string, string> }) });
  const categoriesQuery = (query: object) => ({ queryKey: [base, 'by-category', query], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: query as Record<string, string> }) });
  const { data: summary } = useQuery(summaryQuery('current', range));
  const { data: lastSummary } = useQuery(summaryQuery('previous', previous));
  const { data: monthCategories = [] } = useQuery(categoriesQuery(range));
  const { data: previousCategories = [] } = useQuery(categoriesQuery(previous));
  const { data: spending = [] } = useQuery(categoriesQuery(spendingRange));
  const { data: latest } = useQuery({ queryKey: [base, 'transactions', 'latest'], queryFn: () => api<TransactionPage>(`${base}/transactions`, { query: { limit: 4 } }) });
  const hint = useHint(monthCategories, previousCategories);

  if (isLoading) return <LoadingState />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  const rubAccounts = (accounts ?? []).filter((account) => account.currency === 'RUB');
  const balance = rubAccounts.reduce((sum, account) => sum + Number(account.balance), 0);
  const monthChange = rubAccounts.reduce((sum, account) => sum + Number(account.month_change), 0);
  const balanceGrowth = changePercent(balance, balance - monthChange);
  const categoryById = new Map(groups.flatMap((group) => group.categories.map((category) => [category.id, category] as const)));

  const income = Number(summary?.income ?? 0);
  const expense = Number(summary?.expense ?? 0);
  const incomeChange = changePercent(income, Number(lastSummary?.income ?? 0));
  const expenseChange = changePercent(expense, Number(lastSummary?.expense ?? 0));

  const spendingTotal = spending.reduce((sum, row) => sum + Number(row.total), 0);
  const top = spending.slice(0, 3).map((row) => ({ name: row.category_name, value: Number(row.total) }));
  const rest = spendingTotal - top.reduce((sum, row) => sum + row.value, 0);
  const slices = rest > 0 ? [...top, { name: 'Другое', value: rest }] : top;
  let cursor = 0;
  const donut = slices.map((slice, index) => {
    const start = cursor;
    cursor += (slice.value / spendingTotal) * 100;
    return `${DONUT[index]} ${start}% ${cursor}%`;
  });

  const spentById = new Map(monthCategories.map((row) => [row.category_id, Number(row.total)]));
  const budgets = groups
    .filter((group) => group.type === 'expense')
    .flatMap((group) => group.categories)
    .filter((category) => category.monthly_limit && category.is_active)
    .map((category) => ({ ...category, spent: spentById.get(category.id) ?? 0, limit: Number(category.monthly_limit) }))
    .sort((a, b) => b.spent / b.limit - a.spent / a.limit)
    .slice(0, 3);

  return (
    <>
      <div className="heading-row">
        <div>
          <p className="eyebrow">{todayCaption()}</p>
          <h1>{greeting()}, {user?.name.split(' ')[0]}</h1>
          <p className="subtitle">Вот как идут ваши финансы в этом месяце.</p>
        </div>
        <button className="primary-button" onClick={() => openAdd()}><Plus size={18} />Добавить операцию</button>
      </div>

      <section className="balance-card">
        <div className="balance-main">
          <p>Общий баланс{ledger.type === 'shared' ? ` · ${ledger.name}` : ''}</p>
          <h2>{money(balance)}</h2>
          {balanceGrowth !== null && <span className="positive-pill">{balanceGrowth < 0 ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />} {signedPercent(balanceGrowth)} за месяц</span>}
        </div>
        <div className="income"><span className="metric-icon mint"><ArrowDownLeft size={20} /></span><div><p>Доходы</p><b>{money(income)}</b>{incomeChange !== null && <small>{signedPercent(incomeChange)} к {monthDative(-1)}</small>}</div></div>
        <div className="expense"><span className="metric-icon coral"><ArrowUpRight size={20} /></span><div><p>Расходы</p><b>{money(expense)}</b>{expenseChange !== null && <small>{signedPercent(expenseChange)} к {monthDative(-1)}</small>}</div></div>
        <div className="balance-art" aria-hidden="true">{Array.from({ length: 7 }).map((_, i) => <span key={i} />)}</div>
      </section>

      <div className="dashboard-grid">
        <section className="card spending-card">
          <div className="card-title">
            <div><h3>Расходы по категориям</h3><p>{capitalize(monthTitle(spendingOffset))}</p></div>
            <StyledSelect ariaLabel="Период расходов" value={String(spendingOffset)} onChange={(value) => setSpendingOffset(Number(value))} options={[{ value: '0', label: 'За месяц' }, { value: '-1', label: 'Прошлый месяц' }]} />
          </div>
          {spending.length === 0 ? <State>Расходов за этот период нет</State> : (
            <div className="spending-body">
              <div className="donut" style={{ background: `conic-gradient(${donut.join(',')})` }}><div><b>{money(spendingTotal)}</b><span>всего</span></div></div>
              <div className="legend">
                {slices.map((slice, index) => <p key={slice.name}><i className={DONUT_CLASS[index]} />{slice.name} <b>{Math.round((slice.value / spendingTotal) * 100)}%</b></p>)}
              </div>
            </div>
          )}
        </section>

        <section className="card smart-card">
          <div className="spark"><Sparkles size={21} /></div>
          <p className="smart-label">ПОДСКАЗКА</p>
          {hint ? (
            <>
              <h3>{hint.name}: расходы {hint.diff < 0 ? 'снизились' : 'выросли'} на {Math.abs(hint.percent)}%</h3>
              <p>Это на {money(Math.abs(hint.diff))} {hint.diff < 0 ? 'меньше' : 'больше'}, чем за те же дни прошлого месяца.</p>
            </>
          ) : (
            <>
              <h3>Подсказки появятся позже</h3>
              <p>Нужны операции за этот и прошлый месяц, чтобы было с чем сравнивать.</p>
            </>
          )}
          <Link to="/analytics">Посмотреть аналитику <ArrowUpRight size={16} /></Link>
        </section>

        <section className="card categories-card">
          <div className="card-title">
            <div><h3>Бюджет категорий</h3><p>Лимиты на {monthTitle().split(' ')[0]}</p></div>
            <button className="text-button" onClick={() => navigate('/categories')}>Настроить</button>
          </div>
          {budgets.length === 0 ? <State>Лимиты пока не заданы</State> : (
            <div className="category-list">
              {budgets.map((item, index) => (
                <div key={item.id} className="category-row">
                  <div><span className="category-row-label"><CategoryIcon name={item.name} iconKey={item.icon_key} size="small" /><span>{item.name}</span></span><b>{money(item.spent)} <small>/ {money(item.limit)}</small></b></div>
                  <div className="progress"><span style={{ width: `${Math.min(100, (item.spent / item.limit) * 100)}%`, background: item.spent > item.limit ? 'var(--coral)' : DONUT[(index + 1) % 4] }} /></div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card transactions-card">
          <div className="card-title">
            <div><h3>Последние операции</h3><p>Новые сверху</p></div>
            <button className="text-button" onClick={() => navigate('/transactions')}>Все операции</button>
          </div>
          {latest?.items.length === 0 ? <State>Операций пока нет</State> : (
            <div className="transaction-list">
              {latest?.items.map((tx) => {
                const category = categoryById.get(tx.category_id ?? 0);
                const sign = tx.type === 'income' ? '+ ' : tx.type === 'expense' ? '− ' : '';
                return (
                  <div className="transaction" key={tx.id}>
                    <span className="transaction-icon"><CategoryIcon name={category?.name} iconKey={category?.icon_key} type={tx.type} size="small" /></span>
                    <div><b>{tx.description || category?.name || 'Перевод'}</b><small>{tx.type === 'transfer' ? 'Перевод' : category?.name} · {shortDate(tx.tx_date)}</small></div>
                    <strong className={tx.type}>{sign}{money(tx.amount)}</strong>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
