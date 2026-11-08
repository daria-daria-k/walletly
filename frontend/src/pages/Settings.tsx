import { Check, Palette, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText, setAccessToken } from '../api/client';
import { useAuth } from '../auth';
import { THEME_KEY } from '../components/Layout';
import { ErrorNote, PageHeading } from '../components/ui';
import { initials } from '../lib/format';

const THEMES = [
  { id: 'violet', name: 'AI Violet', note: 'Технологичная и выразительная', colors: ['#241B4B', '#7C65E8', '#FF6B7A'] },
  { id: 'navy', name: 'Navy + Mint', note: 'Спокойная и универсальная', colors: ['#14233C', '#46D2AA', '#FF7867'] },
  { id: 'emerald', name: 'Emerald Fintech', note: 'Строгая финансовая', colors: ['#0F3D3E', '#2DD4A8', '#F06464'] },
  { id: 'warm', name: 'Тёплый', note: 'Мягкая и домашняя', colors: ['#292722', '#E9A23B', '#DF6C5B'] },
  { id: 'blue', name: 'Clean Blue', note: 'Чистая классическая', colors: ['#173F73', '#3478F6', '#F35F65'] },
  { id: 'lime', name: 'Graphite Lime', note: 'Контрастная и смелая', colors: ['#202824', '#B8E455', '#FF7065'] },
];

const SECTIONS = ['Профиль', 'Интерфейс', 'Безопасность', 'Подписка'];

function currentTheme() {
  try {
    return localStorage.getItem(THEME_KEY) ?? 'violet';
  } catch {
    return 'violet';
  }
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

        {section === 'Безопасность' && (
          <section className="card settings-panel">
            <div className="interface-heading"><span className="reconcile-icon"><ShieldCheck /></span><div><h3>Смена пароля</h3><p>После смены другие устройства выйдут из аккаунта.</p></div></div>
            <form onSubmit={changePassword}>
              <div className="settings-form">
                <label>Текущий пароль<input type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required /></label>
                <label>Новый пароль (от 8 символов)<input type="password" autoComplete="new-password" minLength={8} maxLength={128} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></label>
              </div>
              <div className="settings-actions"><button className="primary-button">Изменить пароль</button></div>
              <ErrorNote text={passwordNote.error} />
              {passwordNote.ok && <p className="form-ok">{passwordNote.ok}</p>}
            </form>
          </section>
        )}

        {section === 'Подписка' && (
          <section className="card settings-panel">
            <h3 className="settings-panel-title">Тариф: {user?.plan === 'premium' ? 'Premium' : 'Free'}</h3>
            <p className="settings-note">Оплата подключится на этапе 5. Сейчас тариф меняет администратор.</p>
          </section>
        )}
      </div>
    </div>
  );
}
