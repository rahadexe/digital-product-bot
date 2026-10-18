import type { ReactNode } from 'react';
import { ChevronRight, Package } from 'lucide-react';

/** A mobile list item, intentionally independent of desktop table styles. */
export function MobileRecord({
  title, subtitle, meta, amount, status, tone = 'neutral', icon, label, onOpen,
}: {
  title: string;
  subtitle: string;
  meta?: string;
  amount: string;
  status: string;
  tone?: 'neutral' | 'good' | 'warn' | 'bad';
  icon?: ReactNode;
  label: string;
  onOpen: () => void;
}) {
  return (
    <button type="button" className="app-record" onClick={onOpen} aria-label={label}>
      <span className="app-record-icon" aria-hidden="true">{icon || <Package size={21} />}</span>
      <span className="app-record-copy">
        <strong className="app-record-title">{title}</strong>
        <span className="app-record-subtitle">{subtitle}</span>
        {meta ? <span className="app-record-meta">{meta}</span> : null}
      </span>
      <span className="app-record-tail">
        {amount ? <strong className="app-record-amount">{amount}</strong> : null}
        <span className={`app-record-status ${tone}`}>{status}</span>
        <ChevronRight size={15} className="app-record-chevron" aria-hidden="true" />
      </span>
    </button>
  );
}
