import { useQuery } from '@tanstack/react-query';
import { ArrowLeftRight, Search, Trash2, TrendingDown, TrendingUp, Upload } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { Transaction, TransactionPage, TxType } from '../api/types';
import { useAuth } from '../auth';
import { TransactionModal } from '../components/TransactionModal';
import { ErrorNote, PageHeading, State } from '../components/ui';
import { useAccounts, useCategoryGroups, useRefreshLedgerData } from '../lib/data';
import { money, shortDate } from '../lib/format';
import { useLedger } from '../ledger';

const PAGE_SIZE = 30;
const ICON = { income: TrendingUp, expense: TrendingDown, transfer: ArrowLeftRight };

export function TransactionsPage() {
  const { user } = useAuth();
  const { base, canManage } = useLedger();
  const refresh = useRefreshLedgerData();
  const { data: accounts = [] } = useAccounts(true);
  const { data: groups = [] } = useCategoryGroups();
  const [filters, setFilters] = useState({ search: '', type: '', account_id: '', category_id: '', date_from: '', date_to: '' });
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const query = { ...filters, limit: PAGE_SIZE, offset };
  const { data, isLoading, error } = useQuery({
    queryKey: [base, 'transactions', query],
    queryFn: () => api<TransactionPage>(`${base}/transactions`, { query }),
  });

  const accountById = new Map(accounts.map((account) => [account.id, account]));
  const categoryName = new Map(groups.flatMap((group) => group.categories.map((category) => [category.id, category.name] as const)));

  function setFilter(name: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
    setOffset(0); // на новой выборке старой страницы может не быть
  }

  async function remove(tx: Transaction) {
    if (!window.confirm('Удалить операцию?')) return;
    setActionError(null);
    try {
      await api(`${base}/transactions/${tx.id}`, { method: 'DELETE' });
      await refresh();
    } catch (err) {
      setActionError(errorText(err));
    }
  }

  const canEdit = (tx: Transaction) => canManage || tx.user_id === user?.id;

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Деньги под контролем" title="Операции" subtitle="Все доходы, расходы и переводы." action={<Link className="secondary-button" to="/import"><Upload size={16} /> Импорт</Link>} />
      <section className="card data-card">
        <div className="filterbar">
          <div className="filter-search"><Search size={17} /><input aria-label="Поиск по описанию" placeholder="Описание" value={filters.search} onChange={(e) => setFilter('search', e.target.value)} /></div>
          <select aria-label="Тип" value={filters.type} onChange={(e) => setFilter('type', e.target.value as TxType | '')}>
            <option value="">Все типы</option><option value="expense">Расходы</option><option value="income">Доходы</option><option value="transfer">Переводы</option>
          </select>
          <select aria-label="Счёт" value={filters.account_id} onChange={(e) => setFilter('account_id', e.target.value)}>
            <option value="">Все счета</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <select aria-label="Категория" value={filters.category_id} onChange={(e) => setFilter('category_id', e.target.value)}>
            <option value="">Все категории</option>
            {groups.map((group) => <optgroup key={group.id} label={group.name}>{group.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</optgroup>)}
          </select>
          <input aria-label="С даты" type="date" value={filters.date_from} onChange={(e) => setFilter('date_from', e.target.value)} />
          <input aria-label="По дату" type="date" value={filters.date_to} onChange={(e) => setFilter('date_to', e.target.value)} />
        </div>
        <ErrorNote text={actionError ?? (error ? errorText(error) : null)} />
        {isLoading ? <State>Загрузка…</State> : data?.items.length === 0 ? <State>Операций не найдено</State> : (
          <div className="transaction-table">
            <div className="table-head"><span>Дата</span><span>Операция</span><span>Категория</span><span>Счёт</span><span>Сумма</span><span /></div>
            {data?.items.map((tx) => {
              const Icon = ICON[tx.type];
              const account = accountById.get(tx.account_id);
              const title = tx.description || (tx.type === 'transfer' ? 'Перевод' : categoryName.get(tx.category_id ?? 0)) || '—';
              return (
                <div className="table-row" key={tx.id}>
                  <span>{shortDate(tx.tx_date)}</span>
                  <span className="operation-name">
                    <i><Icon size={16} /></i>
                    {canEdit(tx) ? <button className="link-button" onClick={() => setEditing(tx)}>{title}</button> : <b>{title}</b>}
                  </span>
                  <span>{tx.type === 'transfer' ? <em>Перевод</em> : <em>{categoryName.get(tx.category_id ?? 0)}</em>}</span>
                  <span>{account?.name}{tx.to_account_id ? ` → ${accountById.get(tx.to_account_id)?.name}` : ''}</span>
                  <strong className={tx.type === 'income' ? 'income-text' : ''}>
                    {tx.type === 'income' ? '+ ' : tx.type === 'expense' ? '− ' : ''}{money(tx.amount, account?.currency)}
                  </strong>
                  {canEdit(tx) ? <button aria-label="Удалить" title="Удалить" onClick={() => remove(tx)}><Trash2 size={16} /></button> : <span />}
                </div>
              );
            })}
          </div>
        )}
        {data && data.total > 0 && (
          <div className="table-footer">
            <span>Показано {data.offset + 1}–{data.offset + data.items.length} из {data.total}</span>
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
