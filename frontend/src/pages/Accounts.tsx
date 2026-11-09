import { ArrowUpRight, Download, MoreHorizontal, Plus, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { Account, AccountKind } from '../api/types';
import { useAddOperation } from '../components/Layout';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, ErrorState, LoadingState, Modal, PageHeading, StateCard } from '../components/ui';
import { useAccounts, useRefreshLedgerData } from '../lib/data';
import { KIND_LABEL, KIND_OPTIONS, money, signedMoney } from '../lib/format';
import { useLedger } from '../ledger';

const COLORS = ['green', 'blue', 'purple', 'orange'];

function parseAmount(text: string) {
  return text.replace(/\s/g, '').replace(',', '.');
}

function AccountModal({ account, onClose }: { account?: Account; onClose: () => void }) {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const [name, setName] = useState(account?.name ?? '');
  const [currency, setCurrency] = useState(account?.currency ?? 'RUB');
  const [kind, setKind] = useState<AccountKind>(account?.kind ?? 'card');
  const [initial, setInitial] = useState(account?.initial_balance ?? '0');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function act(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      await refresh();
      onClose();
    } catch (err) {
      setError(errorText(err));
      setSaving(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const initial_balance = parseAmount(initial);
    act(() => (account ? api(`${base}/accounts/${account.id}`, { method: 'PATCH', body: { name, kind, initial_balance } }) : api(`${base}/accounts`, { method: 'POST', body: { name, kind, currency, initial_balance } })));
  }

  return (
    <Modal eyebrow="Счёт" title={account ? 'Изменить счёт' : 'Новый счёт'} onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        {!account && (
          <label>Валюта<StyledSelect ariaLabel="Валюта" value={currency} onChange={setCurrency} options={[{ value: 'RUB', label: 'Рубль (RUB)' }, { value: 'USD', label: 'Доллар (USD)' }, { value: 'EUR', label: 'Евро (EUR)' }]} /></label>
        )}
        <label>Тип<StyledSelect ariaLabel="Тип счёта" value={kind} onChange={(value) => setKind(value as AccountKind)} options={KIND_OPTIONS} /></label>
        <label>Начальный остаток<input inputMode="decimal" value={initial} onChange={(e) => setInitial(e.target.value)} required /></label>
        <ErrorNote text={error} />
        <button className="primary-button submit" disabled={saving}>Сохранить</button>
        {account && (
          <>
            <button type="button" className="secondary-button" disabled={saving} onClick={() => act(() => api(`${base}/accounts/${account.id}`, { method: 'PATCH', body: { is_active: !account.is_active } }))}>
              {account.is_active ? 'Отправить в архив' : 'Вернуть из архива'}
            </button>
            <button type="button" className="danger-button" disabled={saving} onClick={() => window.confirm(`Удалить счёт «${account.name}»?`) && act(() => api(`${base}/accounts/${account.id}`, { method: 'DELETE' }))}>Удалить счёт</button>
          </>
        )}
      </form>
    </Modal>
  );
}

function ReconcileModal({ accounts, canManage, onClose }: { accounts: Account[]; canManage: boolean; onClose: () => void }) {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const [actual, setActual] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function fix(account: Account, diff: number) {
    setError(null);
    try {
      // Расхождение относим к начальному остатку: история операций остаётся как есть
      const initial_balance = (Number(account.initial_balance) + diff).toFixed(2);
      await api(`${base}/accounts/${account.id}`, { method: 'PATCH', body: { initial_balance } });
      await refresh();
      setActual((current) => ({ ...current, [account.id]: '' }));
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Modal eyebrow="Проверка" title="Сверка остатков" onClose={onClose}>
      <div style={{ marginTop: 14 }}>
        {accounts.map((account) => {
          const raw = actual[account.id] ?? '';
          const value = raw ? Number(parseAmount(raw)) : null;
          const diff = value !== null && !Number.isNaN(value) ? Number((value - Number(account.balance)).toFixed(2)) : null;
          return (
            <div className="reconcile-line" key={account.id}>
              <div><b>{account.name}</b><small>В Walletly: {money(account.balance, account.currency)}</small></div>
              <input inputMode="decimal" aria-label={`Остаток в банке: ${account.name}`} placeholder="В банке" value={raw} onChange={(e) => setActual((current) => ({ ...current, [account.id]: e.target.value }))} />
              {diff !== null && (
                <div className="diff">
                  <span>{diff === 0 ? 'Совпадает ✓' : `Расхождение: ${signedMoney(diff, account.currency)}`}</span>
                  {diff !== 0 && canManage && <button className="small-button" onClick={() => fix(account, diff)}>Исправить</button>}
                </div>
              )}
            </div>
          );
        })}
        <div style={{ marginTop: 12 }}><ErrorNote text={error} /></div>
      </div>
    </Modal>
  );
}

export function AccountsPage() {
  const { canManage } = useLedger();
  const openAdd = useAddOperation();
  const navigate = useNavigate();
  const [showArchived, setShowArchived] = useState(false);
  const { data: accounts, isLoading, isError, refetch } = useAccounts(showArchived);
  const [modal, setModal] = useState<Account | 'new' | null>(null);
  const [reconciling, setReconciling] = useState(false);

  const active = (accounts ?? []).filter((account) => account.is_active);
  const totals = new Map<string, number>();
  for (const account of active) totals.set(account.currency, (totals.get(account.currency) ?? 0) + Number(account.balance));

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Ваши деньги" title="Счета" subtitle="Остатки, движение средств и сверка." action={canManage ? <button className="primary-button" onClick={() => setModal('new')}><Plus size={18} />Добавить счёт</button> : undefined} />
      <div className="accounts-total card">
        <div><p>На всех счетах</p><h2>{[...totals].map(([code, sum]) => money(sum, code)).join(' · ') || money(0)}</h2></div>
        <span><label><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Показать архив</label></span>
      </div>
      {isLoading ? <LoadingState /> : isError ? <ErrorState onRetry={() => refetch()} /> : accounts?.length === 0 ? <StateCard icon="💳" title="Счетов пока нет" text="Добавьте карту, вклад или наличные, чтобы видеть общий баланс." /> : (
        <div className="account-grid">
          {accounts?.map((account, index) => (
            <section className="card account-card" key={account.id}>
              <div className="account-head">
                <span className={`bank-logo ${COLORS[index % COLORS.length]}`}>{account.name[0]}</span>
                {canManage && <button aria-label={`Настроить счёт ${account.name}`} onClick={() => setModal(account)}><MoreHorizontal /></button>}
              </div>
              <p>{account.is_active ? KIND_LABEL[account.kind] : 'В архиве'}</p>
              <h3>{account.name}</h3>
              <h2>{money(account.balance, account.currency)}</h2>
              <span>{signedMoney(Number(account.month_change), account.currency)} за месяц</span>
              <div className="account-actions">
                <button disabled={!account.is_active} onClick={() => openAdd({ type: 'transfer', account_id: account.id })}><ArrowUpRight size={16} />Перевод</button>
                <button onClick={() => navigate(`/transactions?account_id=${account.id}`)}><Download size={16} />Выписка</button>
              </div>
            </section>
          ))}
        </div>
      )}
      {active.length > 0 && (
        <section className="card reconcile">
          <div>
            <span className="reconcile-icon"><ShieldCheck /></span>
            <div><h3>Сверка остатков</h3><p>Проверьте, совпадают ли суммы в Walletly с банковскими приложениями.</p></div>
          </div>
          <button className="secondary-button" onClick={() => setReconciling(true)}>Начать сверку</button>
        </section>
      )}
      {modal && <AccountModal account={modal === 'new' ? undefined : modal} onClose={() => setModal(null)} />}
      {reconciling && <ReconcileModal accounts={active} canManage={canManage} onClose={() => setReconciling(false)} />}
    </div>
  );
}
