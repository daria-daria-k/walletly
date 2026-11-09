import { useQuery } from '@tanstack/react-query';
import { Filter, MoreHorizontal, Plus, Search, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Summary, Transaction, TransactionPage } from '../api/types';
import { useAuth } from '../auth';
import { useAddOperation } from '../components/Layout';
import { TransactionModal } from '../components/TransactionModal';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorState, LoadingState, Metric, PageHeading, StateCard } from '../components/ui';
import { useAccounts, useCategoryGroups } from '../lib/data';
import { categoryEmoji, money, monthRange, monthTitle, shortDate, signedMoney } from '../lib/format';
import { useLedger } from '../ledger';

const PAGE_SIZE = 30;

export function TransactionsPage() {
  const { user } = useAuth();
  const { base, canManage } = useLedger();
  const openAdd = useAddOperation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data: accounts = [] } = useAccounts(true);
  const { data: groups = [] } = useCategoryGroups();
  const urlSearch = params.get('search') ?? '';
  const [filters, setFilters] = useState({ search: urlSearch, type: '', account_id: params.get('account_id') ?? '', category_id: '', date_from: '', date_to: '' });
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [showFilters, setShowFilters] = useState(Boolean(params.get('account_id')));

  useEffect(() => {
    // Поиск из верхней панели приходит в адресе, когда страница уже открыта
    setFilters((current) => ({ ...current, search: urlSearch }));
    setOffset(0);
  }, [urlSearch]);

  const month = monthRange();
  const { data: summary } = useQuery({ queryKey: [base, 'summary', month], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: month }) });
  const query = { ...filters, limit: PAGE_SIZE, offset };
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [base, 'transactions', query],
    queryFn: () => api<TransactionPage>(`${base}/transactions`, { query }),
  });

  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryName = new Map(groups.flatMap((group) => group.categories.map((category) => [category.id, category.name] as const)));
  const activeFilters = [filters.account_id, filters.category_id, filters.date_from, filters.date_to].filter(Boolean).length;
  const monthName = monthTitle().split(' ')[0];
  const net = Number(summary?.net ?? 0);
  const hasFilters = activeFilters > 0 || Boolean(filters.search || filters.type);

  function setFilter(name: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
    setOffset(0); // на новой выборке старой страницы может не быть
  }

  const canEdit = (tx: Transaction) => canManage || tx.user_id === user?.id;

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Деньги под контролем" title="Транзакции" subtitle="Все доходы и расходы в одном месте." action={<button className="primary-button" onClick={() => openAdd()}><Plus size={18} />Добавить операцию</button>} />
      <div className="summary-strip">
        <Metric label={`Доходы, ${monthName}`} value={money(summary?.income ?? 0)} tone="good" />
        <Metric label={`Расходы, ${monthName}`} value={money(summary?.expense ?? 0)} tone="bad" />
        <Metric label="Сальдо" value={signedMoney(net)} tone={net >= 0 ? 'good' : 'bad'} />
      </div>
      <section className="card data-card">
        <div className="filterbar">
          <div className="filter-search"><Search size={17} /><input aria-label="Поиск по описанию" placeholder="Название или описание" value={filters.search} onChange={(e) => setFilter('search', e.target.value)} /></div>
          <StyledSelect ariaLabel="Тип" value={filters.type} onChange={(value) => setFilter('type', value)} options={[{ value: '', label: 'Все операции' }, { value: 'expense', label: 'Расходы' }, { value: 'income', label: 'Доходы' }, { value: 'transfer', label: 'Переводы' }]} />
          <button onClick={() => setShowFilters(!showFilters)} aria-expanded={showFilters}><Filter size={16} />Фильтры {activeFilters > 0 && <span className="filter-count">{activeFilters}</span>}</button>
          <button onClick={() => navigate('/import')}><Upload size={16} />Импорт</button>
        </div>
        {showFilters && (
          <div className="filter-panel">
            <StyledSelect ariaLabel="Счёт" value={filters.account_id} onChange={(value) => setFilter('account_id', value)} options={[{ value: '', label: 'Все счета' }, ...accounts.map((a) => ({ value: String(a.id), label: a.name }))]} />
            <StyledSelect ariaLabel="Категория" value={filters.category_id} onChange={(value) => setFilter('category_id', value)} options={[{ value: '', label: 'Все категории' }]} groups={groups.map((group) => ({ label: group.name, options: group.categories.map((c) => ({ value: String(c.id), label: c.name })) }))} />
            <input aria-label="С даты" type="date" value={filters.date_from} onChange={(e) => setFilter('date_from', e.target.value)} />
            <input aria-label="По дату" type="date" value={filters.date_to} onChange={(e) => setFilter('date_to', e.target.value)} />
          </div>
        )}
        {isLoading ? <LoadingState /> : isError ? <ErrorState onRetry={() => refetch()} /> : data?.items.length === 0 ? (
          hasFilters ? <StateCard icon="🔎" title="Операций не найдено" text="Измените условия поиска или сбросьте фильтры." /> : (
            <StateCard icon="📭" title="Пока нет операций" text="Добавьте первую операцию или импортируйте выписку.">
              <button className="secondary-button" onClick={() => openAdd()}>Добавить операцию</button>
            </StateCard>
          )
        ) : (
          <div className="transaction-table">
            <div className="table-head"><span>Дата</span><span>Операция</span><span>Категория</span><span>Счёт</span><span>Сумма</span><span /></div>
            {data?.items.map((tx) => {
              const account = accountById.get(tx.account_id);
              const category = categoryName.get(tx.category_id ?? 0);
              const sign = tx.type === 'income' ? '+ ' : tx.type === 'expense' ? '− ' : '';
              return (
                <div className="table-row" key={tx.id}>
                  <span>{shortDate(tx.tx_date)}</span>
                  <span className="operation-name"><i>{categoryEmoji(category, tx.type)}</i><b>{tx.description || category || 'Перевод'}</b></span>
                  <span><em>{tx.type === 'transfer' ? 'Перевод' : category}</em></span>
                  <span>{account?.name}{tx.to_account_id ? ` → ${accountById.get(tx.to_account_id)?.name}` : ''}</span>
                  <strong className={tx.type === 'income' ? 'income-text' : ''}>{sign}{money(tx.amount, account?.currency)}</strong>
                  {canEdit(tx) ? <button aria-label="Действия" title="Изменить" onClick={() => setEditing(tx)}><MoreHorizontal size={18} /></button> : <span />}
                </div>
              );
            })}
          </div>
        )}
        {data && data.total > 0 && (
          <div className="table-footer">
            <span>Показано {data.offset + 1}–{data.offset + data.items.length} из {data.total} операций</span>
            <div>
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Назад</button>
              <button disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Далее</button>
            </div>
          </div>
        )}
      </section>
      {editing && <TransactionModal transaction={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
