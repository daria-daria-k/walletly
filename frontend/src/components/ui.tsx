import { useIsFetching } from '@tanstack/react-query';
import { CloudOff, Inbox, LoaderCircle, SearchX, ShieldX, WalletCards, X } from 'lucide-react';
import { Component, useEffect, useState, type ReactNode } from 'react';
import { storedTheme } from '../lib/theme';

export function PageHeading({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="heading-row page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Metric({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="summary-metric">
      <p>{label}</p>
      <b className={tone}>{value}</b>
      {note && <small>{note}</small>}
    </div>
  );
}

export function Modal({ eyebrow, title, onClose, children }: { eyebrow: string; title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h2>{title}</h2>
          </div>
          <button onClick={onClose} aria-label="Закрыть">
            <X />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function ErrorNote({ text }: { text: string | null | undefined }) {
  return text ? <p className="form-error" role="alert">{text}</p> : null;
}

const STATE_ICONS = { empty: Inbox, loading: LoaderCircle, offline: CloudOff, locked: ShieldX, missing: SearchX };

export type StateType = keyof typeof STATE_ICONS;

export function StateCard({ type, title, text, children }: { type: StateType; title: string; text: string; children?: ReactNode }) {
  const Icon = STATE_ICONS[type];
  return (
    <section className="card state-card">
      <div className="state-icon-wrap">
        <span className={`state-visual ${type}`} aria-hidden="true">
          <span className="state-orbit" />
          <Icon className="state-main-icon" />
          <WalletCards className="state-wallet-mark" />
        </span>
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </section>
  );
}

export function LoadingState() {
  return <StateCard type="loading" title="Загружаем данные" text="Синхронизируем счета и пересчитываем аналитику." />;
}

// continued — продолжение прелоадера с предыдущего этапа загрузки, без повторного появления
export function WalletlyPreloader({ continued }: { continued?: boolean }) {
  return (
    // Свой data-theme: первые этапы загрузки идут до Layout, где тема применяется ко всему приложению
    <div className={`walletly-preloader${continued ? ' continued' : ''}`} data-theme={storedTheme()} role="status" aria-live="polite" aria-label="Walletly загружает данные">
      <div className="preloader-glass">
        <div className="coin-stage" aria-hidden="true">
          <span className="coin coin-one">₽</span>
          <span className="coin coin-two">W</span>
          <span className="coin coin-three">$</span>
          <span className="coin-shadow" />
        </div>
        <div className="preloader-copy"><b>Walletly</b><span>Собираем финансовую картину</span></div>
        <div className="preloader-progress"><i /></div>
      </div>
    </div>
  );
}

// Минимум: иначе на быстром соединении прелоадер мелькнёт и будет выглядеть как сбой.
// К этому моменту запросы экрана уже стартовали, поэтому счётчик запросов можно проверять
const FIRST_LOAD_MIN_MS = 500;
// Предел: медленный фоновый запрос не должен навсегда закрыть рабочий интерфейс
const FIRST_LOAD_MAX_MS = 8000;

export function FirstLoadPreloader() {
  const fetching = useIsFetching();
  const [minPassed, setMinPassed] = useState(false);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const min = window.setTimeout(() => setMinPassed(true), FIRST_LOAD_MIN_MS);
    const max = window.setTimeout(() => setFinished(true), FIRST_LOAD_MAX_MS);
    return () => {
      window.clearTimeout(min);
      window.clearTimeout(max);
    };
  }, []);

  useEffect(() => {
    if (minPassed && fetching === 0) setFinished(true);
  }, [minPassed, fetching]);

  return finished ? null : <WalletlyPreloader continued />;
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <StateCard type="offline" title="Не удалось загрузить" text="Проверьте соединение и попробуйте ещё раз.">
      <button className="secondary-button" onClick={onRetry}>Повторить</button>
    </StateCard>
  );
}

export function State({ children }: { children: ReactNode }) {
  return <div className="state">{children}</div>;
}

// Ошибка при отрисовке иначе оставила бы пользователя с пустым белым экраном
export class CrashBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="state-page" data-theme="violet">
        <ErrorState onRetry={() => window.location.reload()} />
      </div>
    );
  }
}
