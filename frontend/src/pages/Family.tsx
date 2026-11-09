import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ShieldCheck, UserPlus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { AuthorTotal, Invitation, Ledger, Member, Summary } from '../api/types';
import { useAuth } from '../auth';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, Modal, PageHeading } from '../components/ui';
import { useAccounts } from '../lib/data';
import { initials, money, monthRange, monthTitle, ROLE_LABEL, shortDate } from '../lib/format';
import { useLedger } from '../ledger';

function CreateSpace() {
  const queryClient = useQueryClient();
  const { select } = useLedger();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const ledger = await api<Ledger>('/ledgers', { method: 'POST', body: { name } });
      await queryClient.invalidateQueries({ queryKey: ['ledgers'] });
      select(ledger.id);
      setName('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="card plain-card">
      <h3>Новое общее пространство</h3>
      <p>Отдельные счета, категории и операции, которые видят все участники.</p>
      <form className="inline-form" onSubmit={submit}>
        <input aria-label="Название пространства" placeholder="Например, Семья" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
        <button className="primary-button">Создать</button>
      </form>
      <div style={{ marginTop: 10 }}><ErrorNote text={error} /></div>
    </section>
  );
}

function InviteModal({ onClose }: { onClose: () => void }) {
  const { base } = useLedger();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api(`${base}/invitations`, { method: 'POST', body: { email } });
      await queryClient.invalidateQueries({ queryKey: [base] });
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Modal eyebrow="Семья" title="Пригласить участника" onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
        <ErrorNote text={error} />
        <button className="primary-button submit">Создать ссылку</button>
      </form>
    </Modal>
  );
}

function SharedSpace({ inviting, onCloseInvite, onInvite }: { inviting: boolean; onCloseInvite: () => void; onInvite: () => void }) {
  const { user } = useAuth();
  const { base, ledger, canManage } = useLedger();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const range = monthRange();

  const { data: accounts = [] } = useAccounts();
  const { data: members = [] } = useQuery({ queryKey: [base, 'members'], queryFn: () => api<Member[]>(`${base}/members`) });
  const { data: invitations = [] } = useQuery({ queryKey: [base, 'invitations'], queryFn: () => api<Invitation[]>(`${base}/invitations`), enabled: canManage });
  const { data: summary } = useQuery({ queryKey: [base, 'summary', range], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: range }) });
  const { data: authors = [] } = useQuery({ queryKey: [base, 'by-author', range], queryFn: () => api<AuthorTotal[]>(`${base}/analytics/by-author`, { query: range }) });

  async function run(action: () => Promise<unknown>, afterLedgers = false) {
    setError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: afterLedgers ? ['ledgers'] : [base] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  const inviteLink = (token: string) => `${window.location.origin}/invite/${token}`;
  const isOwner = ledger.role === 'owner';
  const balance = accounts.filter((a) => a.currency === 'RUB').reduce((sum, a) => sum + Number(a.balance), 0);
  const expense = Number(summary?.expense ?? 0);
  const split = authors.map((a) => `${a.name} — ${Math.round((Number(a.total) / expense) * 100)}%`).join(' · ');
  const pending = invitations.filter((i) => i.status === 'pending');

  return (
    <>
      <div className="family-hero card">
        <div><p>Общий баланс</p><h2>{money(balance)}</h2><span>Активных счетов: {accounts.length}</span></div>
        <div className="family-split"><p>Расходы, {monthTitle().split(' ')[0]}</p><b>{money(expense)}</b><small>{split || 'Расходов пока нет'}</small></div>
      </div>
      <ErrorNote text={error} />
      <div className="family-grid">
        <section className="card members-card">
          <div className="section-head"><div><h3>Участники</h3><p>Человек: {members.length}</p></div></div>
          {members.map((member) => (
            <div className="member-row" key={member.user_id}>
              <span>{initials(member.name)}</span>
              <div><b>{member.name}</b><small>{member.email}</small></div>
              {isOwner && member.role !== 'owner' ? (
                <StyledSelect ariaLabel={`Роль: ${member.name}`} value={member.role} onChange={(role) => run(() => api(`${base}/members/${member.user_id}`, { method: 'PATCH', body: { role } }))} options={[{ value: 'member', label: 'Участник' }, { value: 'admin', label: 'Администратор' }]} />
              ) : <em>{ROLE_LABEL[member.role]}</em>}
              {member.role !== 'owner' && (canManage || member.user_id === user?.id) ? (
                <button className="small-button danger" onClick={() => window.confirm(member.user_id === user?.id ? 'Выйти из пространства?' : `Исключить ${member.name}?`) && run(() => api(`${base}/members/${member.user_id}`, { method: 'DELETE' }), member.user_id === user?.id)}>
                  {member.user_id === user?.id ? 'Выйти' : 'Исключить'}
                </button>
              ) : <i />}
            </div>
          ))}
          {canManage && <button className="invite-row" onClick={onInvite}><UserPlus size={17} />Пригласить участника по email</button>}
          {pending.map((invitation) => (
            <div className="invite-line" key={invitation.id}>
              <div><b>{invitation.email}</b><small>до {shortDate(invitation.expires_at.slice(0, 10))}</small></div>
              <code>{inviteLink(invitation.token)}</code>
              <div className="row-actions">
                <button className="small-button" onClick={() => navigator.clipboard.writeText(inviteLink(invitation.token))}>Копировать</button>
                <button className="small-button danger" onClick={() => run(() => api(`${base}/invitations/${invitation.id}`, { method: 'DELETE' }))}>Отозвать</button>
              </div>
            </div>
          ))}
        </section>
        <section className="card permissions-card">
          <span className="reconcile-icon"><ShieldCheck /></span>
          <h3>Права доступа</h3>
          <p>Участники видят общие счета и операции. Данные личного пространства остаются приватными.</p>
          <ul>
            <li><Check />Общие операции</li>
            <li><Check />Категории и лимиты</li>
            <li><Check />Совместная аналитика</li>
          </ul>
          {isOwner && <button className="small-button danger" onClick={() => window.confirm(`Удалить «${ledger.name}» со всеми данными? Это нельзя отменить.`) && run(() => api(base, { method: 'DELETE' }), true)}>Удалить пространство</button>}
        </section>
      </div>
      {inviting && <InviteModal onClose={onCloseInvite} />}
    </>
  );
}

export function FamilyPage() {
  const { ledger, canManage } = useLedger();
  const [inviting, setInviting] = useState(false);
  const shared = ledger.type === 'shared';
  return (
    <div className="prototype-page page-stack">
      <PageHeading
        eyebrow="Совместный бюджет"
        title={shared ? ledger.name : 'Семья'}
        subtitle={shared ? 'Общие расходы видны всем участникам группы.' : 'Сейчас открыто личное пространство: его данные видите только вы.'}
        action={shared && canManage ? <button className="primary-button" onClick={() => setInviting(true)}><UserPlus size={18} />Пригласить</button> : undefined}
      />
      {shared && <SharedSpace inviting={inviting} onInvite={() => setInviting(true)} onCloseInvite={() => setInviting(false)} />}
      <CreateSpace />
    </div>
  );
}
