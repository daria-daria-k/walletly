import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Transaction, TxType } from '../api/types';
import { useAccounts, useCategoryGroups, useRefreshLedgerData } from '../lib/data';
import { isoDate } from '../lib/format';
import { useLedger } from '../ledger';
import { StyledSelect } from './StyledSelect';
import { ErrorNote, Modal } from './ui';

const TYPES: { value: TxType; label: string }[] = [
  { value: 'expense', label: 'Расход' },
  { value: 'income', label: 'Доход' },
  { value: 'transfer', label: 'Перевод' },
];

const SUBMIT_LABEL = { expense: 'Добавить расход', income: 'Добавить доход', transfer: 'Добавить перевод' };

export function TransactionModal({ transaction, preset, onClose }: { transaction?: Transaction; preset?: { type?: TxType; account_id?: number }; onClose: () => void }) {
  const { base } = useLedger();
  const { data: accounts = [] } = useAccounts();
  const { data: groups = [] } = useCategoryGroups();
  const refresh = useRefreshLedgerData();

  const [type, setType] = useState<TxType>(transaction?.type ?? preset?.type ?? 'expense');
  const [amount, setAmount] = useState(transaction?.amount ?? '');
  const [accountId, setAccountId] = useState(String(transaction?.account_id ?? preset?.account_id ?? ''));
  const [toAccountId, setToAccountId] = useState(String(transaction?.to_account_id ?? ''));
  const [categoryId, setCategoryId] = useState(String(transaction?.category_id ?? ''));
  const [description, setDescription] = useState(transaction?.description ?? '');
  const [txDate, setTxDate] = useState(transaction?.tx_date ?? isoDate(new Date()));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const visibleGroups = groups.filter((group) => group.type === type);
  const effectiveAccount = accountId || String(accounts[0]?.id ?? '');
  const currency = accounts.find((a) => String(a.id) === effectiveAccount)?.currency ?? 'RUB';

  function changeType(next: TxType) {
    setType(next);
    setCategoryId(''); // категории доходов и расходов разные, старый выбор недействителен
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (type === 'transfer' ? !toAccountId : !categoryId) {
      setError(type === 'transfer' ? 'Выберите счёт зачисления' : 'Выберите категорию');
      return;
    }
    setSaving(true); // блокирует кнопку: двойной клик не создаст вторую операцию
    setError(null);
    const body = {
      type,
      amount: amount.replace(/\s/g, '').replace(',', '.'),
      account_id: Number(effectiveAccount),
      to_account_id: type === 'transfer' && toAccountId ? Number(toAccountId) : null,
      category_id: type !== 'transfer' && categoryId ? Number(categoryId) : null,
      description: description.trim() || null,
      tx_date: txDate,
    };
    try {
      if (transaction) await api(`${base}/transactions/${transaction.id}`, { method: 'PATCH', body });
      else await api(`${base}/transactions`, { method: 'POST', body });
      await refresh();
      setSaved(true);
      window.setTimeout(onClose, 900); // успех должен быть заметен, прежде чем окно закроется
    } catch (err) {
      setError(errorText(err));
      setSaving(false);
    }
  }

  async function remove() {
    if (!transaction || !window.confirm('Удалить операцию?')) return;
    try {
      await api(`${base}/transactions/${transaction.id}`, { method: 'DELETE' });
      await refresh();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Modal eyebrow={transaction ? 'Редактирование' : 'Новая запись'} title={transaction ? 'Изменить операцию' : 'Добавить операцию'} onClose={onClose}>
      <div className="type-switch three">
        {TYPES.map((item) => (
          <button key={item.value} type="button" className={type === item.value ? 'selected' : ''} onClick={() => changeType(item.value)}>
            {item.label}
          </button>
        ))}
      </div>
      <form onSubmit={submit}>
        <label>
          Сумма
          <div className="amount-input">
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0" required autoFocus />
            <span>{currency === 'RUB' ? '₽' : currency}</span>
          </div>
        </label>
        <div className="form-grid">
          <label>
            {type === 'transfer' ? 'Со счёта' : 'Счёт'}
            <StyledSelect ariaLabel={type === 'transfer' ? 'Со счёта' : 'Счёт'} value={effectiveAccount} onChange={setAccountId} options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} />
          </label>
          {type === 'transfer' ? (
            <label>
              На счёт
              <StyledSelect ariaLabel="На счёт" value={toAccountId} onChange={setToAccountId} options={accounts.filter((a) => String(a.id) !== effectiveAccount).map((a) => ({ value: String(a.id), label: a.name }))} />
            </label>
          ) : (
            <label>
              Категория
              <StyledSelect ariaLabel="Категория" value={categoryId} onChange={setCategoryId} groups={visibleGroups.map((group) => ({ label: group.name, options: group.categories.filter((c) => c.is_active || String(c.id) === categoryId).map((c) => ({ value: String(c.id), label: c.name })) }))} />
            </label>
          )}
        </div>
        <label>
          Описание
          <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} placeholder="Например, продукты на неделю" />
        </label>
        <label>
          Дата
          <input type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} required />
        </label>
        <ErrorNote text={accounts.length === 0 ? 'Сначала добавьте счёт на странице «Счета»' : error} />
        <button className="primary-button submit" type="submit" disabled={saving || accounts.length === 0}>
          {saved ? 'Сохранено ✓' : saving ? 'Сохраняем…' : transaction ? 'Сохранить' : SUBMIT_LABEL[type]}
        </button>
        {transaction && <button type="button" className="danger-button" onClick={remove}>Удалить операцию</button>}
      </form>
    </Modal>
  );
}
