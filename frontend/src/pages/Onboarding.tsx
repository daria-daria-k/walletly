import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, BadgeCheck, Check } from 'lucide-react';
import { useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { api, errorText } from '../api/client';
import type { AccountKind, Ledger } from '../api/types';
import { useAuth } from '../auth';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, PageHeading } from '../components/ui';
import { useCategoryGroups } from '../lib/data';
import { KIND_OPTIONS, plural } from '../lib/format';
import { CategoryIcon } from '../components/CategoryIcon';
import { useLedger } from '../ledger';

const STEPS = [
  { title: 'Знакомство', hint: 'Основные параметры' },
  { title: 'Счета', hint: 'Добавьте деньги' },
  { title: 'Категории', hint: 'Настройте бюджет' },
  { title: 'Готово', hint: 'Проверьте результат' },
];

const CURRENCIES = [
  { code: 'RUB', title: '₽ Российский рубль' },
  { code: 'USD', title: '$ Доллар США' },
  { code: 'EUR', title: '€ Евро' },
];

export function OnboardingPage() {
  const { user, reload } = useAuth();
  const { ledger, select } = useLedger();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: groups = [] } = useCategoryGroups();

  const [step, setStep] = useState(1);
  const [currency, setCurrency] = useState('RUB');
  const [family, setFamily] = useState(false);
  const [name, setName] = useState('');
  const [balance, setBalance] = useState('0');
  const [kind, setKind] = useState<AccountKind>('card');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Если счёт не создался, повторная попытка не должна заводить второе семейное пространство
  const createdLedger = useRef<number | null>(null);
  const initialBalance = balance.replace(/\s/g, '').replace(',', '.');

  if (user?.onboarding_completed) return <Navigate to="/" replace />;

  // Как в макете: в шаблоне сначала показываем расходы, с ними человек работает каждый день
  const ordered = [...groups].sort((a, b) => Number(a.type === 'income') - Number(b.type === 'income'));
  const categories = ordered.flatMap((group) => group.categories.map((category) => ({ name: category.name, iconKey: category.icon_key, type: group.type })));
  const finished = step === 4;

  async function finishSetup() {
    setBusy(true);
    setError(null);
    try {
      let ledgerId = createdLedger.current ?? ledger.id;
      if (family && createdLedger.current === null) {
        ledgerId = (await api<Ledger>('/ledgers', { method: 'POST', body: { name: 'Семья' } })).id;
        createdLedger.current = ledgerId;
      }
      await api(`/ledgers/${ledgerId}/accounts`, { method: 'POST', body: { name: name.trim(), kind, currency, initial_balance: initialBalance } });
      // Флаг ставим сразу: перезагрузка на последнем шаге не должна создать счёт повторно
      await api('/auth/me', { method: 'PATCH', body: { onboarding_completed: true } });
      if (createdLedger.current !== null) {
        await queryClient.invalidateQueries({ queryKey: ['ledgers'] });
        select(createdLedger.current);
      }
      setStep(4);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function next() {
    setError(null);
    if (step === 2 && (!name.trim() || initialBalance === '' || Number.isNaN(Number(initialBalance)))) {
      setError('Укажите название счёта и остаток числом');
      return;
    }
    if (step === 3) return finishSetup();
    if (step === 4) {
      setBusy(true);
      await reload();
      navigate('/', { replace: true });
      return;
    }
    setStep(step + 1);
  }

  return (
    <div className="prototype-page onboarding-page">
      <PageHeading eyebrow="Первый запуск" title="Настройка Walletly" subtitle="Четыре коротких шага — и приложение готово к работе." />
      <div className="onboarding-layout">
        <aside className="card onboarding-steps">
          {STEPS.map((item, index) => {
            const number = index + 1;
            return (
              <button key={item.title} className={number === step ? 'active' : number < step ? 'done' : ''} disabled={finished || number > step} onClick={() => setStep(number)}>
                <span>{number < step ? <Check size={15} /> : number}</span>
                <div><b>{item.title}</b><small>{item.hint}</small></div>
              </button>
            );
          })}
        </aside>
        <section className="card onboarding-card">
          {step === 1 && (
            <>
              <span className="onboarding-icon">👋</span>
              <h2>Добро пожаловать в Walletly</h2>
              <p>Выберите валюту и формат учёта.</p>
              <div className="choice-row three">
                {CURRENCIES.map((item) => (
                  <button key={item.code} className={currency === item.code ? 'selected' : ''} aria-pressed={currency === item.code} onClick={() => setCurrency(item.code)}>
                    <b>{item.title}</b><span>Валюта первого счёта</span>
                  </button>
                ))}
              </div>
              <div className="choice-row">
                <button className={family ? '' : 'selected'} aria-pressed={!family} onClick={() => setFamily(false)}><b>Личный бюджет</b><span>Только мои данные</span></button>
                <button className={family ? 'selected' : ''} aria-pressed={family} onClick={() => setFamily(true)}><b>Семейный бюджет</b><span>Общее пространство с близкими</span></button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <span className="onboarding-icon">💳</span>
              <h2>Добавьте первый счёт</h2>
              <p>Укажите карту, вклад или наличные, чтобы видеть общий баланс.</p>
              <div className="onboarding-form">
                <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} placeholder="Например, Сбер" autoFocus /></label>
                <label>Текущий остаток<input inputMode="decimal" value={balance} onChange={(e) => setBalance(e.target.value)} /></label>
                <label>Тип<StyledSelect ariaLabel="Тип счёта" value={kind} onChange={(value) => setKind(value as AccountKind)} options={KIND_OPTIONS} /></label>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <span className="onboarding-icon">🎯</span>
              <h2>Базовый набор категорий</h2>
              <p>Мы подготовили шаблон. Категории и лимиты можно менять в любое время.</p>
              <div className="template-preview">
                {categories.slice(0, 4).map((item) => <span key={item.name}><CategoryIcon name={item.name} iconKey={item.iconKey} type={item.type} size="small" /> {item.name}</span>)}
                {categories.length > 4 && <span>＋ Ещё {categories.length - 4}</span>}
              </div>
            </>
          )}
          {finished && (
            <>
              <span className="onboarding-icon">✨</span>
              <h2>Всё готово</h2>
              <p>Счёт добавлен, категории настроены. Теперь можно внести первую операцию.</p>
              <div className="ready-summary"><BadgeCheck /><div><b>Walletly настроен</b><span>1 счёт · {plural(categories.length, 'категория', 'категории', 'категорий')} · {currency}</span></div></div>
            </>
          )}
          <ErrorNote text={error} />
          <div className="onboarding-actions">
            <button className="secondary-button" disabled={step === 1 || finished || busy} onClick={() => setStep(step - 1)}>Назад</button>
            <button className="primary-button" disabled={busy} onClick={next}>{busy ? 'Подождите…' : finished ? 'Перейти к обзору' : 'Продолжить'}<ArrowRight size={17} /></button>
          </div>
        </section>
      </div>
    </div>
  );
}
