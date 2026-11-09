import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Palette, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, errorText, setAccessToken } from '../api/client';
import type { NotificationSettings, PaymentItem, PlanInfo } from '../api/types';
import { useAuth } from '../auth';
import { THEME_KEY } from '../components/Layout';
import { ErrorNote, PageHeading } from '../components/ui';
import { dateTime, initials, money, plural, shortDate } from '../lib/format';

const THEMES = [
  { id: 'violet', name: 'AI Violet', note: 'Технологичная и выразительная', colors: ['#241B4B', '#7C65E8', '#FF6B7A'] },
  { id: 'navy', name: 'Navy + Mint', note: 'Спокойная и универсальная', colors: ['#14233C', '#46D2AA', '#FF7867'] },
  { id: 'emerald', name: 'Emerald Fintech', note: 'Строгая финансовая', colors: ['#0F3D3E', '#2DD4A8', '#F06464'] },
  { id: 'warm', name: 'Тёплый', note: 'Мягкая и домашняя', colors: ['#292722', '#E9A23B', '#DF6C5B'] },
  { id: 'blue', name: 'Clean Blue', note: 'Чистая классическая', colors: ['#173F73', '#3478F6', '#F35F65'] },
  { id: 'lime', name: 'Graphite Lime', note: 'Контрастная и смелая', colors: ['#202824', '#B8E455', '#FF7065'] },
];

const SECTIONS = ['Профиль', 'Интерфейс', 'Уведомления', 'Безопасность', 'Подписка'];

const NOTIFICATIONS: { key: keyof NotificationSettings; title: string; text: string }[] = [
  { key: 'budget', title: 'Превышение бюджета', text: 'Когда категория достигает 80% и 100% лимита' },
  { key: 'unusual', title: 'Необычные траты', text: 'Если расход заметно отличается от привычного' },
  { key: 'weekly', title: 'Еженедельный отчёт', text: 'Краткая сводка по воскресеньям' },
  { key: 'family', title: 'Семейная группа', text: 'Новые операции и приглашения участников' },
];

const BENEFITS = {
  free: ['Счета и операции без ограничений', 'Семейная группа', 'Одна копилка', 'Подсказки, импорт и экспорт Excel'],
  premium: ['Всё из тарифа Free', 'Копилки без ограничений', 'Умные категории и прогнозы', 'Telegram-бот и разбор выписок'],
};

function currentTheme() {
  try {
    return localStorage.getItem(THEME_KEY) ?? 'violet';
  } catch {
    return 'violet';
  }
}

const PAYMENT_STATUS: Record<PaymentItem['status'], string> = { pending: 'Ожидает оплаты', succeeded: 'Оплачен', canceled: 'Отменён' };

function Billing() {
  const { reload } = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const { data: plan } = useQuery({ queryKey: ['billing-plan'], queryFn: () => api<PlanInfo>('/billing/plan') });
  const { data: payments } = useQuery({ queryKey: ['billing-payments'], queryFn: () => api<PaymentItem[]>('/billing/payments') });
  const returned = params.get('payment');

  useEffect(() => {
    if (!returned) return;
    // Вернулись со страницы оплаты: спрашиваем статус сами, уведомление могло ещё не дойти
    api(`/billing/payments/${returned}/sync`, { method: 'POST' })
      .then(() => Promise.all([reload(), queryClient.invalidateQueries({ queryKey: ['billing-payments'] })]))
      .catch((err) => setError(errorText(err)))
      .finally(() => setParams({}, { replace: true }));
  }, [returned, reload, queryClient, setParams]);

  async function pay() {
    setError(null);
    try {
      const { confirmation_url } = await api<{ confirmation_url: string }>('/billing/checkout', { method: 'POST' });
      window.location.href = confirmation_url;
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <>
      <div className="billing-row">
        <div><b>Premium: {plan ? money(plan.price) : '…'} за {plan?.period_days ?? 30} дней</b><span>{plan?.payments_enabled ? 'Безопасная оплата через ЮKassa. Без автосписаний.' : 'Оплата пока не настроена, тариф может выдать администратор.'}</span></div>
        <button className="primary-button" disabled={!plan?.payments_enabled} onClick={pay}>Оплатить</button>
      </div>
      <ErrorNote text={error} />
      {Boolean(payments?.length) && (
        <div className="payment-history">
          <b>История платежей</b>
          {payments?.map((item) => <div key={item.id}><span>{dateTime(item.created_at)}</span><span>{money(item.amount)}</span><em>{PAYMENT_STATUS[item.status]}</em></div>)}
        </div>
      )}
    </>
  );
}

export function SettingsPage() {
  const { user, reload, logout } = useAuth();
  const [section, setSection] = useState('Профиль');
  const [name, setName] = useState(user?.name ?? '');
  const [profileNote, setProfileNote] = useState<{ ok?: string; error?: string }>({});
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordNote, setPasswordNote] = useState<{ ok?: string; error?: string }>({});
  const [theme, setTheme] = useState(currentTheme);
  const [changingPassword, setChangingPassword] = useState(false);
  const [notifyError, setNotifyError] = useState<string | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: sessions } = useQuery({ queryKey: ['sessions'], queryFn: () => api<{ active: number }>('/auth/sessions'), enabled: section === 'Безопасность' });

  async function resendVerification() {
    try {
      await api('/auth/resend-verification', { method: 'POST' });
      setProfileNote({ ok: 'Письмо отправлено, проверьте почту' });
    } catch (err) {
      setProfileNote({ error: errorText(err) });
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    try {
      await api('/auth/me', { method: 'PATCH', body: { name } });
      await reload();
      setProfileNote({ ok: 'Сохранено' });
    } catch (err) {
      setProfileNote({ error: errorText(err) });
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    try {
      const tokens = await api<{ access_token: string }>('/auth/change-password', {
        method: 'POST',
        body: { current_password: currentPassword, new_password: newPassword },
      });
      setAccessToken(tokens.access_token);
      setCurrentPassword('');
      setNewPassword('');
      setPasswordNote({ ok: 'Пароль изменён. Другие устройства вышли из аккаунта.' });
    } catch (err) {
      setPasswordNote({ error: errorText(err) });
    }
  }

  async function toggleNotification(key: keyof NotificationSettings) {
    if (!user) return;
    setNotifyError(null);
    try {
      await api('/auth/me', { method: 'PATCH', body: { notifications: { ...user.notifications, [key]: !user.notifications[key] } } });
      await reload();
    } catch (err) {
      setNotifyError(errorText(err));
    }
  }

  async function revokeOthers() {
    setSessionsError(null);
    try {
      await api('/auth/sessions/revoke-others', { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    } catch (err) {
      setSessionsError(errorText(err));
    }
  }

  function chooseTheme(id: string) {
    setTheme(id);
    try {
      localStorage.setItem(THEME_KEY, id);
    } catch {
      // Без localStorage тема применится только до перезагрузки
    }
    window.dispatchEvent(new CustomEvent(THEME_KEY, { detail: id }));
  }

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Аккаунт" title="Профиль и настройки" subtitle="Личные данные, безопасность и параметры приложения." />
      <div className="settings-grid">
        <aside className="card settings-nav">
          {SECTIONS.map((item) => <button key={item} className={section === item ? 'active' : ''} onClick={() => setSection(item)}>{item}</button>)}
          <button onClick={logout}>Выйти</button>
        </aside>

        {section === 'Профиль' && (
          <section className="card settings-panel">
            <div className="profile-edit"><span>{initials(user?.name ?? '')}</span><div><h3>{user?.name}</h3><p>{user?.email}</p></div></div>
            <form onSubmit={saveProfile}>
              <div className="settings-form">
                <label className="wide">Имя<input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required /></label>
                <label className="wide">Email<input value={user?.email ?? ''} disabled /></label>
                {user && !user.email_verified_at && (
                  <p className="wide email-unverified">Адрес не подтверждён. <button type="button" onClick={resendVerification}>Отправить письмо ещё раз</button></p>
                )}
              </div>
              <div className="settings-actions"><button className="primary-button">Сохранить изменения</button></div>
              <ErrorNote text={profileNote.error} />
              {profileNote.ok && <p className="form-ok">{profileNote.ok}</p>}
            </form>
          </section>
        )}

        {section === 'Интерфейс' && (
          <section className="card settings-panel interface-panel">
            <div className="interface-heading"><span className="reconcile-icon"><Palette /></span><div><h3>Цветовая схема</h3><p>Выберите оформление, с которым вам комфортнее работать.</p></div></div>
            <div className="settings-theme-grid">
              {THEMES.map((option) => (
                <button key={option.id} className={theme === option.id ? 'selected' : ''} onClick={() => chooseTheme(option.id)} aria-pressed={theme === option.id}>
                  <span className="large-swatches">{option.colors.map((color) => <i key={color} style={{ background: color }} />)}</span>
                  <span><b>{option.name}</b><small>{option.note}</small></span>
                  {theme === option.id && <em><Check size={16} /></em>}
                </button>
              ))}
            </div>
          </section>
        )}

        {section === 'Уведомления' && (
          <section className="card settings-panel">
            <div className="interface-heading"><span className="reconcile-icon">🔔</span><div><h3>Уведомления</h3><p>Выберите, о каких событиях Walletly должен сообщать.</p></div></div>
            <div className="toggle-list">
              {NOTIFICATIONS.map((item) => (
                <div className="toggle-row" key={item.key}>
                  <div><b>{item.title}</b><span>{item.text}</span></div>
                  <button className={user?.notifications[item.key] ? 'enabled' : ''} aria-pressed={user?.notifications[item.key]} aria-label={item.title} onClick={() => toggleNotification(item.key)}><i /></button>
                </div>
              ))}
            </div>
            <ErrorNote text={notifyError} />
            <p className="settings-note" style={{ marginTop: 14 }}>Уведомления появляются в колокольчике, недельная сводка приходит ещё и на почту.</p>
          </section>
        )}

        {section === 'Безопасность' && (
          <section className="card settings-panel">
            <div className="interface-heading"><span className="reconcile-icon"><ShieldCheck /></span><div><h3>Безопасность</h3><p>Пароль и активные сессии.</p></div></div>
            <div className="security-list">
              <div>
                <span>🔑</span>
                <div><b>Пароль</b><small>Не менее 8 символов</small></div>
                <button className="secondary-button" onClick={() => setChangingPassword(!changingPassword)}>Изменить</button>
              </div>
              {changingPassword && (
                <form className="security-form" onSubmit={changePassword}>
                  <div className="settings-form">
                    <label>Текущий пароль<input type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required /></label>
                    <label>Новый пароль<input type="password" autoComplete="new-password" minLength={8} maxLength={128} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></label>
                  </div>
                  <div className="settings-actions"><button className="primary-button">Изменить пароль</button></div>
                </form>
              )}
              <div>
                <span>💻</span>
                <div><b>Активные сессии</b><small>{sessions ? plural(sessions.active, 'устройство', 'устройства', 'устройств') : '…'}</small></div>
                <button className="secondary-button" disabled={!sessions || sessions.active < 2} onClick={revokeOthers}>Завершить другие</button>
              </div>
            </div>
            <ErrorNote text={passwordNote.error ?? sessionsError} />
            {passwordNote.ok && <p className="form-ok">{passwordNote.ok}</p>}
          </section>
        )}

        {section === 'Подписка' && (
          <section className="card settings-panel subscription-settings">
            <div className="subscription-current">
              <div>
                <small>Текущий тариф</small>
                <h3>Walletly {user?.plan === 'premium' ? 'Premium' : 'Free'}</h3>
                <p>{user?.plan_expires_at ? `Активен до ${shortDate(user.plan_expires_at.slice(0, 10))}` : 'Бессрочно'}</p>
              </div>
              <span>{user?.plan === 'premium' ? 'PREMIUM' : 'FREE'}</span>
            </div>
            <div className="plan-benefits">
              <b>В тариф включено</b>
              <ul>{BENEFITS[user?.plan === 'premium' ? 'premium' : 'free'].map((item) => <li key={item}><Check />{item}</li>)}</ul>
            </div>
            <Billing />
          </section>
        )}
      </div>
    </div>
  );
}
