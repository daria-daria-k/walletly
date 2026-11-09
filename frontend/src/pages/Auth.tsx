import { ArrowRight, BadgeCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { errorText } from '../api/client';
import { useAuth } from '../auth';
import { ErrorNote } from '../components/ui';

function useAfterAuth() {
  const [params] = useSearchParams();
  // Только внутренний путь: иначе ссылка вида ?next=//evil.ru увела бы на чужой сайт после входа
  const next = params.get('next');
  return next?.startsWith('/') && !next.startsWith('//') ? next : '/';
}

function AuthScreen({ mode }: { mode: 'login' | 'register' }) {
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const target = useAfterAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isLogin = mode === 'login';

  if (user) return <Navigate to={target} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isLogin) await login(email, password);
      else await register(email, password, name);
      navigate(target, { replace: true });
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  function switchTo(next: 'login' | 'register') {
    setError(null);
    navigate(`/${next}?next=${encodeURIComponent(target)}`, { replace: true });
  }

  return (
    <div className="auth-page" data-theme="violet">
      <div className="auth-layout">
        <section className="auth-story">
          <div className="brand"><img className="brand-mark" src="/brand/walletly-mark.svg" alt="" /><span>Walletly</span></div>
          <p>Финансы без лишнего шума</p>
          <h2>Все счета, расходы и цели — в одном понятном пространстве.</h2>
          <ul>
            <li><BadgeCheck size={17} />Данные защищены</li>
            <li><BadgeCheck size={17} />Настройка за несколько минут</li>
            <li><BadgeCheck size={17} />Подсказки по вашим расходам</li>
          </ul>
        </section>
        <section className="card auth-card">
          <div className="auth-switch">
            <button type="button" className={isLogin ? 'active' : ''} onClick={() => switchTo('login')}>Войти</button>
            <button type="button" className={isLogin ? '' : 'active'} onClick={() => switchTo('register')}>Регистрация</button>
          </div>
          <h2>{isLogin ? 'С возвращением' : 'Создайте аккаунт'}</h2>
          <p>{isLogin ? 'Введите данные, чтобы продолжить.' : 'Начните вести бюджет вместе с Walletly.'}</p>
          <form className="auth-form" onSubmit={submit}>
            {!isLogin && <label>Имя<input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} autoFocus /></label>}
            <label>Email<input type="email" autoComplete="username" placeholder="name@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus={isLogin} /></label>
            <label>Пароль<input type="password" autoComplete={isLogin ? 'current-password' : 'new-password'} placeholder={isLogin ? undefined : 'Не менее 8 символов'} minLength={isLogin ? undefined : 8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            <ErrorNote text={error} />
            <button className="primary-button wide-button" disabled={busy}>
              {busy ? 'Подождите…' : isLogin ? 'Войти' : 'Создать аккаунт'}<ArrowRight size={17} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}

export function LoginPage() {
  return <AuthScreen mode="login" />;
}

export function RegisterPage() {
  return <AuthScreen mode="register" />;
}
