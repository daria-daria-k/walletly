import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { InvitationPreview } from '../api/types';
import { useAuth } from '../auth';
import { ErrorNote } from '../components/ui';

export function InvitePage() {
  const { token } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading, error: loadError } = useQuery({ queryKey: ['invitation', token], queryFn: () => api<InvitationPreview>(`/invitations/${token}`) });

  async function act(action: 'accept' | 'decline') {
    setError(null);
    try {
      await api(`/invitations/${token}/${action}`, { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['ledgers'] });
      navigate(action === 'accept' ? '/family' : '/', { replace: true });
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="auth-page" data-theme="violet">
      <section className="modal auth-card">
        <div className="brand"><img className="brand-mark" src="/brand/walletly-mark.svg" alt="" /><span>Walletly</span></div>
        {isLoading && <p>Загрузка…</p>}
        <ErrorNote text={loadError ? errorText(loadError) : error} />
        {data && (
          <>
            <div className="modal-head"><h2>Приглашение в «{data.ledger_name}»</h2></div>
            <p className="hint" style={{ textAlign: 'left' }}>Приглашение для {data.invited_email}. Вы вошли как {user?.email}.</p>
            {data.status === 'pending' ? (
              <div className="row-actions" style={{ marginTop: 18 }}>
                <button className="primary-button" onClick={() => act('accept')}>Принять</button>
                <button className="secondary-button" onClick={() => act('decline')}>Отклонить</button>
              </div>
            ) : <p className="hint">Приглашение уже обработано или истекло.</p>}
          </>
        )}
        <p className="hint"><Link to="/">На главную</Link></p>
      </section>
    </div>
  );
}
