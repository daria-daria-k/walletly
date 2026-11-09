import { X } from 'lucide-react';
import { Component, useEffect, type ReactNode } from 'react';

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

export function StateCard({ icon, title, text, loading, children }: { icon: string; title: string; text: string; loading?: boolean; children?: ReactNode }) {
  return (
    <section className="card state-card">
      <span className={loading ? 'spin' : ''}>{icon}</span>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </section>
  );
}

export function LoadingState() {
  return <StateCard icon="⏳" title="Загружаем данные" text="Синхронизируем счета и пересчитываем аналитику." loading />;
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <StateCard icon="⚠️" title="Не удалось загрузить" text="Проверьте соединение и попробуйте ещё раз.">
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
