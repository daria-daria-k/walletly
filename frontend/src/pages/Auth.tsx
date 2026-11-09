import { ArrowRight, BadgeCheck } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { api, errorText } from '../api/client';
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
            {isLogin && <Link className="auth-forgot" to="/forgot-password">Забыли пароль?</Link>}
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

function SmallAuthCard({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <div className="state-page" data-theme="violet">
      <section className="card auth-card auth-card-single">
        <h2>{title}</h2>
        <p>{text}</p>
        {children}
      </section>
    </div>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api('/auth/forgot-password', { method: 'POST', body: { email }, noRefresh: true });
      setSent(true);
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (sent) {
    return (
      <SmallAuthCard title="Проверьте почту" text="Если такой адрес зарегистрирован, мы отправили на него ссылку для сброса пароля. Она действует 1 час.">
        <Link className="secondary-button" to="/login">Вернуться ко входу</Link>
      </SmallAuthCard>
    );
  }
  return (
    <SmallAuthCard title="Сброс пароля" text="Укажите email, и мы пришлём ссылку для нового пароля.">
      <form className="auth-form" onSubmit={submit}>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
        <ErrorNote text={error} />
        <button className="primary-button wide-button">Отправить ссылку</button>
        <Link className="auth-forgot" to="/login">Вернуться ко входу</Link>
      </form>
    </SmallAuthCard>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api('/auth/reset-password', { method: 'POST', body: { token, new_password: password }, noRefresh: true });
      setDone(true);
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (done) {
    return (
      <SmallAuthCard title="Пароль изменён" text="Все устройства вышли из аккаунта. Войдите с новым паролем.">
        <Link className="primary-button" to="/login">Войти</Link>
      </SmallAuthCard>
    );
  }
  return (
    <SmallAuthCard title="Новый пароль" text="Придумайте пароль не короче 8 символов.">
      <form className="auth-form" onSubmit={submit}>
        <label>Новый пароль<input type="password" autoComplete="new-password" minLength={8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus /></label>
        <ErrorNote text={error} />
        <button className="primary-button wide-button" disabled={!token}>Сохранить пароль</button>
      </form>
    </SmallAuthCard>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [state, setState] = useState<'wait' | 'ok' | 'error'>('wait');
  // StrictMode вызывает эффект дважды, а ссылка одноразовая: второй запрос показал бы ошибку
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    api('/auth/verify-email', { method: 'POST', body: { token }, noRefresh: true })
      .then(() => setState('ok'))
      .catch(() => setState('error'));
  }, [token]);

  const title = state === 'wait' ? 'Проверяем ссылку…' : state === 'ok' ? 'Email подтверждён' : 'Ссылка устарела';
  const text = state === 'error' ? 'Отправьте письмо ещё раз в настройках профиля.' : state === 'ok' ? 'Спасибо! Теперь можно пользоваться всеми функциями.' : 'Это займёт секунду.';
  return (
    <SmallAuthCard title={title} text={text}>
      {state !== 'wait' && <Link className="primary-button" to="/">Открыть Walletly</Link>}
    </SmallAuthCard>
  );
}
