import { Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Account } from '../api/types';
import { ErrorNote, Modal, PageHeading, State } from '../components/ui';
import { useAccounts, useRefreshLedgerData } from '../lib/data';
import { money } from '../lib/format';
import { useLedger } from '../ledger';

function AccountModal({ account, onClose }: { account?: Account; onClose: () => void }) {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const [name, setName] = useState(account?.name ?? '');
  const [currency, setCurrency] = useState(account?.currency ?? 'RUB');
  const [initial, setInitial] = useState(account?.initial_balance ?? '0');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const initial_balance = initial.replace(/\s/g, '').replace(',', '.');
    try {
      if (account) await api(`${base}/accounts/${account.id}`, { method: 'PATCH', body: { name, initial_balance } });
      else await api(`${base}/accounts`, { method: 'POST', body: { name, currency, initial_balance } });
      await refresh();
      onClose();
    } catch (err) {
      setError(errorText(err));
      setSaving(false);
    }
  }

  return (
    <Modal eyebrow="Счёт" title={account ? 'Изменить счёт' : 'Новый счёт'} onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        {!account && (
          <label>Валюта
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="RUB">Рубль (RUB)</option><option value="USD">Доллар (USD)</option><option value="EUR">Евро (EUR)</option>
            </select>
          </label>
        )}
        <label>Начальный остаток<input inputMode="decimal" value={initial} onChange={(e) => setInitial(e.target.value)} required /></label>
        <ErrorNote text={error} />
        <button className="primary-button submit" disabled={saving}>Сохранить</button>
      </form>
    </Modal>
  );
}

export function AccountsPage() {
  const { base, canManage } = useLedger();
  const refresh = useRefreshLedgerData();
  const [showArchived, setShowArchived] = useState(false);
  const { data: accounts, isLoading } = useAccounts(showArchived);
  const [modal, setModal] = useState<Account | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const setActive = (account: Account, is_active: boolean) => run(() => api(`${base}/accounts/${account.id}`, { method: 'PATCH', body: { is_active } }));
  const remove = (account: Account) => window.confirm(`Удалить счёт «${account.name}»?`) && run(() => api(`${base}/accounts/${account.id}`, { method: 'DELETE' }));

  const totals = new Map<string, number>();
  for (const account of accounts ?? []) {
    if (account.is_active) totals.set(account.currency, (totals.get(account.currency) ?? 0) + Number(account.balance));
  }

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Ваши деньги" title="Счета" subtitle="Остаток считается по операциям." action={canManage ? <button className="primary-button" onClick={() => setModal('new')}><Plus size={18} />Добавить счёт</button> : undefined} />
      <div className="accounts-total card">
        <div><p>На всех счетах</p><h2>{[...totals].map(([code, sum]) => money(sum, code)).join(' · ') || money(0)}</h2></div>
        <label style={{ fontSize: 13 }}><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Показать архив</label>
      </div>
      <ErrorNote text={error} />
      {isLoading ? <State>Загрузка…</State> : accounts?.length === 0 ? <State>Счетов пока нет. Добавьте первый.</State> : (
        <div className="account-grid">
          {accounts?.map((account) => (
            <section className="card account-card" key={account.id}>
              <div className="account-head"><span className="bank-logo purple">{account.name[0]}</span></div>
              <p>{account.is_active ? account.currency : 'В архиве'}</p>
              <h3>{account.name}</h3>
              <h2>{money(account.balance, account.currency)}</h2>
              <span>Начальный остаток: {money(account.initial_balance, account.currency)}</span>
              {canManage && (
                <div className="row-actions" style={{ marginTop: 12 }}>
                  <button className="small-button" onClick={() => setModal(account)}>Изменить</button>
                  <button className="small-button" onClick={() => setActive(account, !account.is_active)}>{account.is_active ? 'В архив' : 'Вернуть'}</button>
                  <button className="small-button danger" onClick={() => remove(account)}>Удалить</button>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
      {modal && <AccountModal account={modal === 'new' ? undefined : modal} onClose={() => setModal(null)} />}
    </div>
  );
}
