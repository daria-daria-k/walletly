import { X } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';

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

export function State({ children }: { children: ReactNode }) {
  return <div className="state">{children}</div>;
}
