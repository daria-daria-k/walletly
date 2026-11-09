import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MoreHorizontal, PiggyBank, Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Account, ContributionItem, Goal } from '../api/types';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, ErrorState, LoadingState, Modal, PageHeading, StateCard } from '../components/ui';
import { useAccounts, useRefreshLedgerData } from '../lib/data';
import { KIND_LABEL, money, plural } from '../lib/format';
import { useLedger } from '../ledger';

const amount = (text: string) => text.replace(/\s/g, '').replace(',', '.');
const monthLabel = (iso: string) => new Date(iso).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
const savingsOnly = (items: Account[] = []) => items.filter((item) => item.kind !== 'card' && item.is_active);

function useAct(onClose: () => void) {
  const refresh = useRefreshLedgerData();
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
  return { act, error, saving };
}

function MoveBlock({ goal, onClose }: { goal: Goal; onClose: () => void }) {
  const { ledgers, ledger, base } = useLedger();
  const { act, error, saving } = useAct(onClose);
  const targets = ledgers.filter((item) => item.id !== ledger.id && item.role !== 'member');
  const [targetId, setTargetId] = useState(targets[0] ? String(targets[0].id) : '');
  const [accountId, setAccountId] = useState('');
  const { data: accounts } = useQuery({
    queryKey: ['goal-move-accounts', targetId],
    queryFn: () => api<Account[]>(`/ledgers/${targetId}/accounts`),
    enabled: Boolean(targetId),
  });
  const options = savingsOnly(accounts).map((item) => ({ value: String(item.id), label: `${item.name} · ${KIND_LABEL[item.kind]}` }));
  if (targets.length === 0) return null;

  return (
    <div className="goal-move">
      <h4>Сделать {ledger.type === 'personal' ? 'общей' : 'личной'}</h4>
      <label>Пространство<StyledSelect ariaLabel="Пространство" value={targetId} onChange={(value) => { setTargetId(value); setAccountId(''); }} options={targets.map((item) => ({ value: String(item.id), label: item.name }))} /></label>
      <label>Счёт в этом пространстве<StyledSelect ariaLabel="Счёт" value={accountId} onChange={setAccountId} options={options} placeholder={options.length ? 'Выберите счёт' : 'Нет подходящих счетов'} disabled={!options.length} /></label>
      <ErrorNote text={error} />
      <button type="button" className="secondary-button" disabled={saving || !accountId} onClick={() => act(() => api(`${base}/goals/${goal.id}/move`, { method: 'POST', body: { target_ledger_id: Number(targetId), account_id: Number(accountId) } }))}>Перенести</button>
    </div>
  );
}

function GoalModal({ goal, onClose }: { goal?: Goal; onClose: () => void }) {
  const { base } = useLedger();
  const { data: accounts } = useAccounts(false);
  const { act, error, saving } = useAct(onClose);
  const [name, setName] = useState(goal?.name ?? '');
  const [target, setTarget] = useState(goal?.target_amount ?? '');
  const [monthly, setMonthly] = useState(goal?.monthly_contribution ?? '');
  const [day, setDay] = useState(String(goal?.reminder_day ?? 1));
  const [accountId, setAccountId] = useState(goal ? String(goal.account_id) : '');
  const options = savingsOnly(accounts).map((item) => ({ value: String(item.id), label: `${item.name} · ${KIND_LABEL[item.kind]}` }));

  function submit(event: FormEvent) {
    event.preventDefault();
    const body = { name, target_amount: amount(target), monthly_contribution: amount(monthly), reminder_day: Number(day), account_id: Number(accountId) };
    act(() => (goal ? api(`${base}/goals/${goal.id}`, { method: 'PATCH', body }) : api(`${base}/goals`, { method: 'POST', body })));
  }

  return (
    <Modal eyebrow="Копилка" title={goal ? 'Настройки копилки' : 'Новая копилка'} onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>На что копим<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        <label>Цель<input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} required /></label>
        <label>Плановый взнос в месяц<input inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} required /></label>
        <label>Где лежат деньги<StyledSelect ariaLabel="Где лежат деньги" value={accountId} onChange={setAccountId} options={options} placeholder={options.length ? 'Выберите счёт' : 'Сначала создайте вклад, накопительный счёт или наличные'} disabled={!options.length} /></label>
        <label>Напоминать, начиная с числа<input type="number" min={1} max={28} value={day} onChange={(e) => setDay(e.target.value)} required /></label>
        <ErrorNote text={error} />
        <button className="primary-button submit" disabled={saving || !accountId}>Сохранить</button>
        {goal && <button type="button" className="danger-button" disabled={saving} onClick={() => window.confirm(`Удалить копилку «${goal.name}»? История пополнений тоже удалится, деньги останутся на счёте.`) && act(() => api(`${base}/goals/${goal.id}`, { method: 'DELETE' }))}>Удалить копилку</button>}
      </form>
      {goal && <MoveBlock goal={goal} onClose={onClose} />}
    </Modal>
  );
}

function ContributeModal({ goal, onClose }: { goal: Goal; onClose: () => void }) {
  const { base, canManage } = useLedger();
  const { data: accounts } = useAccounts(false);
  const refresh = useRefreshLedgerData();
  const queryClient = useQueryClient();
  const { act, error, saving } = useAct(onClose);
  const [value, setValue] = useState(goal.monthly_contribution);
  const [source, setSource] = useState('');
  const historyKey = [base, 'goal-contributions', goal.id];
  const { data: history } = useQuery({ queryKey: historyKey, queryFn: () => api<ContributionItem[]>(`${base}/goals/${goal.id}/contributions`) });
  const sources = (accounts ?? []).filter((item) => item.id !== goal.account_id && item.currency === goal.currency && item.is_active);

  async function remove(id: number) {
    await api(`${base}/goals/${goal.id}/contributions/${id}`, { method: 'DELETE' });
    await Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: historyKey })]);
  }

  return (
    <Modal eyebrow={goal.name} title="Пополнить копилку" onClose={onClose}>
      <form style={{ marginTop: 16 }} onSubmit={(event) => { event.preventDefault(); act(() => api(`${base}/goals/${goal.id}/contributions`, { method: 'POST', body: { amount: amount(value), from_account_id: source ? Number(source) : null } })); }}>
        <label>Сумма<input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} required autoFocus /></label>
        <label>Откуда<StyledSelect ariaLabel="Откуда" value={source} onChange={setSource} options={[{ value: '', label: `Уже на счёте «${goal.account_name}»` }, ...sources.map((item) => ({ value: String(item.id), label: `Перевести со счёта «${item.name}»` }))]} /></label>
        <ErrorNote text={error} />
        <button className="primary-button submit" disabled={saving}>Пополнить</button>
      </form>
      {Boolean(history?.length) && (
        <div className="goal-history">
          <h4>История</h4>
          {history?.map((item) => (
            <div key={item.id}>
              <span>{new Date(item.contributed_on).toLocaleDateString('ru-RU')} · {item.user_name}</span>
              <b>{money(item.amount, goal.currency)}</b>
              {canManage && <button type="button" aria-label="Удалить пополнение" onClick={() => window.confirm('Удалить пополнение? Связанный перевод тоже отменится.') && remove(item.id)}>×</button>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function GoalCard({ goal, canManage, onEdit, onContribute }: { goal: Goal; canManage: boolean; onEdit: () => void; onContribute: () => void }) {
  const reached = goal.months_left === 0;
  return (
    <section className="card goal-card">
      <div className="goal-head">
        <span className="goal-icon"><PiggyBank size={20} /></span>
        <div><h3>{goal.name}</h3><p>{goal.account_name}</p></div>
        {canManage && <button aria-label={`Настройки копилки ${goal.name}`} onClick={onEdit}><MoreHorizontal /></button>}
      </div>
      <h2>{money(goal.saved, goal.currency)}<small> из {money(goal.target_amount, goal.currency)}</small></h2>
      <div className="goal-progress" role="progressbar" aria-valuenow={goal.progress_percent} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${goal.progress_percent}%` }} /></div>
      {reached ? <p className="goal-forecast done">Цель достигнута 🎉</p> : (
        <p className="goal-forecast">Осталось {money(goal.remaining, goal.currency)}: {plural(goal.months_left, 'взнос', 'взноса', 'взносов')} по {money(goal.monthly_contribution, goal.currency)}, цель к <b>{monthLabel(goal.forecast_month as string)}</b></p>
      )}
      {goal.missed_last_month && <p className="goal-note">В прошлом месяце пополнения не было, прогноз пересчитан.</p>}
      {goal.reminder_due && <p className="goal-note due">Пора отложить деньги в этом месяце.</p>}
      {!reached && <button className="secondary-button" onClick={onContribute}>Пополнить</button>}
    </section>
  );
}

export function GoalsPage() {
  const { base, canManage } = useLedger();
  const { data: goals, isLoading, isError, refetch } = useQuery({ queryKey: [base, 'goals'], queryFn: () => api<Goal[]>(`${base}/goals`) });
  const [editing, setEditing] = useState<Goal | 'new' | null>(null);
  const [contributing, setContributing] = useState<Goal | null>(null);

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Цели" title="Копилка" subtitle="Копите на важное и смотрите, когда цель будет достигнута." action={canManage ? <button className="primary-button" onClick={() => setEditing('new')}><Plus size={17} />Новая копилка</button> : undefined} />
      {isLoading ? <LoadingState /> : isError ? <ErrorState onRetry={() => refetch()} /> : goals?.length === 0 ? <StateCard type="empty" title="Копилок пока нет" text="Создайте первую: укажите цель и сколько готовы откладывать в месяц." /> : (
        <div className="goal-grid">
          {goals?.map((goal) => <GoalCard key={goal.id} goal={goal} canManage={canManage} onEdit={() => setEditing(goal)} onContribute={() => setContributing(goal)} />)}
        </div>
      )}
      {editing && <GoalModal goal={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      {contributing && <ContributeModal goal={contributing} onClose={() => setContributing(null)} />}
    </div>
  );
}
