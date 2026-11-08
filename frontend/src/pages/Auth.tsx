import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { errorText } from '../api/client';
import { useAuth } from '../auth';
import { ErrorNote } from '../components/ui';

function useAfterAuth() {
  const [params] = useSearchParams();
  // Только внутренний путь: иначе ссылка вида ?next=//evil.ru увела бы на чужой сайт после входа
  const next = params.get('next');
  return next?.startsWith('/') && !next.startsWith('//') ? next : '/';
}

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const target = useAfterAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={target} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(target, { replace: true });
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-page" data-theme="violet">
      <section className="modal auth-card">
        <div className="brand"><span className="brand-mark">W</span><span>Walletly</span></div>
        <div className="modal-head"><h2>Вход</h2></div>
        <form onSubmit={submit} style={{ marginTop: 16 }}>
          <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
          <label>Пароль<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <ErrorNote text={error} />
          <button className="primary-button submit" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</button>
        </form>
        <p className="hint">Нет аккаунта? <Link to={`/register?next=${encodeURIComponent(target)}`}>Зарегистрироваться</Link></p>
      </section>
    </div>
  );
}

export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const target = useAfterAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={target} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, password, name);
      navigate(target, { replace: true });
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-page" data-theme="violet">
      <section className="modal auth-card">
        <div className="brand"><span className="brand-mark">W</span><span>Walletly</span></div>
        <div className="modal-head"><h2>Регистрация</h2></div>
        <form onSubmit={submit} style={{ marginTop: 16 }}>
          <label>Имя<input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} autoFocus /></label>
          <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль (от 8 символов)<input type="password" autoComplete="new-password" minLength={8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <ErrorNote text={error} />
          <button className="primary-button submit" disabled={busy}>{busy ? 'Создаём…' : 'Создать аккаунт'}</button>
        </form>
        <p className="hint">Уже есть аккаунт? <Link to={`/login?next=${encodeURIComponent(target)}`}>Войти</Link></p>
      </section>
    </div>
  );
}
