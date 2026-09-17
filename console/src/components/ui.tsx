'use client';

// The handful of pieces every screen is built from, so each screen only says what it shows.

import { X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

/** The value once typing has paused, so a search box asks the server once rather than per keystroke. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const wait = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(wait);
  }, [value, delay]);
  return settled;
}

export type Say = (message: string, kind?: 'good' | 'bad') => void;

export function useConfirm() {
  const [request, setRequest] = useState<{ title: string; message: string; confirmLabel: string } | null>(null);
  const resolver = useRef<((confirmed: boolean) => void) | null>(null);

  const confirm = (title: string, message: string, confirmLabel = 'Confirm') =>
    new Promise<boolean>((resolve) => {
      resolver.current = resolve;
      setRequest({ title, message, confirmLabel });
    });

  const close = (confirmed: boolean) => {
    resolver.current?.(confirmed);
    resolver.current = null;
    setRequest(null);
  };

  const dialog = request ? (
    <Modal
      title={request.title}
      onClose={() => close(false)}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={() => close(false)}>Cancel</button>
          <button type="button" className="btn danger" onClick={() => close(true)}>{request.confirmLabel}</button>
        </>
      }
    >
      <p className="confirm-message">{request.message}</p>
    </Modal>
  ) : null;

  return [confirm, dialog] as const;
}

export const errorText = (cause: unknown, fallback = 'That did not work.') =>
  cause instanceof Error && cause.message ? cause.message : fallback;

/** "3m ago", "5h ago", then the date: when something happened matters more than its timestamp. */
export function when(iso?: string | null): string {
  if (!iso) return '';
  const then = new Date(iso.includes('T') || iso.includes('Z') ? iso : `${iso.replace(' ', 'T')}Z`).getTime();
  if (Number.isNaN(then)) return iso.slice(0, 16);
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(then).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export const who = (row: { username?: string | null; first_name?: string | null; tg_user_id: number }) =>
  row.username ? `@${row.username}` : row.first_name || `User ${row.tg_user_id}`;

/** An on/off setting. A switch says "this is on right now"; a tick box reads like a form to fill in. */
export function Switch({
  on,
  onChange,
  label,
  danger = false,
  disabled = false,
}: {
  on: boolean;
  onChange: (on: boolean) => void;
  label: string;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      className={`switch${on ? ' on' : ''}${danger ? ' danger' : ''}`}
      onClick={() => onChange(!on)}
    >
      <span />
    </button>
  );
}

export function FlagRow({
  label,
  hint,
  on,
  onChange,
  danger = false,
}: {
  label: string;
  hint?: string;
  on: boolean;
  onChange: (on: boolean) => void;
  danger?: boolean;
}) {
  return (
    <div className="flag-row">
      <div>
        <strong>{label}</strong>
        {hint ? <small>{hint}</small> : null}
      </div>
      <Switch label={label} on={on} onChange={onChange} danger={danger} />
    </div>
  );
}

export function Pager({ total, offset, size, onChange }: { total: number; offset: number; size: number; onChange: (offset: number) => void }) {
  if (total <= size) return null;
  return (
    <div className="pager">
      <span>
        {offset + 1}–{Math.min(offset + size, total)} of {total}
      </span>
      <span className="spacer" />
      <button type="button" className="mini" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - size))}>
        Previous
      </button>
      <button type="button" className="mini" disabled={offset + size >= total} onClick={() => onChange(offset + size)}>
        Next
      </button>
    </div>
  );
}

/** A table row that says there is nothing, spanning every column. */
export function EmptyRow({ columns, children }: { columns: number; children: React.ReactNode }) {
  return (
    <tr>
      <td className="empty" colSpan={columns}>
        {children}
      </td>
    </tr>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide = false,
  onSubmit,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
  onSubmit?: (event: React.FormEvent) => void;
}) {
  useEffect(() => {
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', escape);
    const priorOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', escape);
      document.body.style.overflow = priorOverflow;
    };
  }, [onClose]);

  const content = (
    <>
      <header>
        <h2>{title}</h2>
        <button type="button" className="close" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      <div className="body">{children}</div>
      {footer ? <footer>{footer}</footer> : null}
    </>
  );

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      {onSubmit ? (
        <form className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} onSubmit={onSubmit}>
          {content}
        </form>
      ) : (
        <div className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
          {content}
        </div>
      )}
    </div>
  );
}

/** Status words mapped to the three tones a pill can have. */
export function tone(status?: string | null): '' | 'good' | 'bad' | 'warn' {
  switch (status) {
    case 'completed':
    case 'approved':
    case 'available':
    case 'delivered':
    case 'active':
      return 'good';
    case 'rejected':
    case 'failed':
    case 'refunded':
    case 'banned':
    case 'expired':
      return 'bad';
    case 'pending':
    case 'created':
    case 'queued':
    case 'processing':
    case 'sending':
      return 'warn';
    default:
      return '';
  }
}
