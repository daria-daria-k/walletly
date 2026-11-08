import { useQuery, useQueryClient } from '@tanstack/react-query';
import { UserPlus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Invitation, Ledger, Member } from '../api/types';
import { useAuth } from '../auth';
import { ErrorNote, PageHeading } from '../components/ui';
import { initials, ROLE_LABEL, shortDate } from '../lib/format';
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

function SharedSpace() {
  const { user } = useAuth();
  const { base, ledger, canManage } = useLedger();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: members = [] } = useQuery({ queryKey: [base, 'members'], queryFn: () => api<Member[]>(`${base}/members`) });
  const { data: invitations = [] } = useQuery({ queryKey: [base, 'invitations'], queryFn: () => api<Invitation[]>(`${base}/invitations`), enabled: canManage });

  async function run(action: () => Promise<unknown>, afterLedgers = false) {
    setError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: afterLedgers ? ['ledgers'] : [base] });
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    await run(() => api(`${base}/invitations`, { method: 'POST', body: { email } }));
    setEmail('');
  }

  const inviteLink = (token: string) => `${window.location.origin}/invite/${token}`;
  const isOwner = ledger.role === 'owner';

  return (
    <>
      <section className="card members-card">
        <div className="section-head"><div><h3>Участники</h3><p>{members.length} чел.</p></div></div>
        {members.map((member) => (
          <div className="member-row" key={member.user_id}>
            <span>{initials(member.name)}</span>
            <div><b>{member.name}</b><small>{member.email}</small></div>
            {isOwner && member.role !== 'owner' ? (
              <select aria-label={`Роль: ${member.name}`} value={member.role} onChange={(e) => run(() => api(`${base}/members/${member.user_id}`, { method: 'PATCH', body: { role: e.target.value } }))}>
                <option value="member">Участник</option><option value="admin">Администратор</option>
              </select>
            ) : <em>{ROLE_LABEL[member.role]}</em>}
            {member.role !== 'owner' && (canManage || member.user_id === user?.id) ? (
              <button className="small-button danger" onClick={() => window.confirm(member.user_id === user?.id ? 'Выйти из пространства?' : `Исключить ${member.name}?`) && run(() => api(`${base}/members/${member.user_id}`, { method: 'DELETE' }), member.user_id === user?.id)}>
                {member.user_id === user?.id ? 'Выйти' : 'Исключить'}
              </button>
            ) : <span />}
          </div>
        ))}
      </section>
      <ErrorNote text={error} />
      {canManage && (
        <section className="card plain-card">
          <h3><UserPlus size={17} style={{ display: 'inline', marginRight: 6 }} />Пригласить</h3>
          <p>Письма пока не отправляются: скопируйте ссылку и пришлите её человеку. Принять сможет только аккаунт с этим email.</p>
          <form className="inline-form" onSubmit={invite}>
            <input type="email" aria-label="Email приглашённого" placeholder="email@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <button className="primary-button">Создать ссылку</button>
          </form>
          <div style={{ marginTop: 12 }}>
            {invitations.filter((i) => i.status === 'pending').map((invitation) => (
              <div className="invite-line" key={invitation.id}>
                <div><b>{invitation.email}</b><small>до {shortDate(invitation.expires_at.slice(0, 10))}</small></div>
                <code>{inviteLink(invitation.token)}</code>
                <div className="row-actions">
                  <button className="small-button" onClick={() => navigator.clipboard.writeText(inviteLink(invitation.token))}>Копировать</button>
                  <button className="small-button danger" onClick={() => run(() => api(`${base}/invitations/${invitation.id}`, { method: 'DELETE' }))}>Отозвать</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {isOwner && (
        <section className="card plain-card">
          <h3>Удаление</h3>
          <p>Удалятся все счета, категории и операции этого пространства. Отменить нельзя.</p>
          <button className="small-button danger" onClick={() => window.confirm(`Удалить «${ledger.name}» со всеми данными?`) && run(() => api(base, { method: 'DELETE' }), true)}>Удалить пространство</button>
        </section>
      )}
    </>
  );
}

export function FamilyPage() {
  const { ledger } = useLedger();
  return (
    <div className="prototype-page page-stack">
      <PageHeading eyebrow="Совместный учёт" title={ledger.type === 'shared' ? ledger.name : 'Семья'} subtitle={ledger.type === 'shared' ? 'Общие операции видны всем участникам.' : 'Сейчас открыто личное пространство: его данные видите только вы.'} />
      {ledger.type === 'shared' && <SharedSpace />}
      <CreateSpace />
    </div>
  );
}
