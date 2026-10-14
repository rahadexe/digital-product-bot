'use client';

import { useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Modal } from './ui';

/** Keep list rows scannable without making secondary information inaccessible. */
export function RecordDetails({ label, title, fields, children }: {
  label: string;
  title: string;
  fields: [string, ReactNode][];
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={trigger} type="button" className="record-link" title={label} aria-label={`View details: ${label}`} onClick={() => setOpen(true)}>
        {label}
      </button>
      {open && typeof document !== 'undefined' && createPortal(
        <Modal title={title} className="record-drawer" onClose={() => setOpen(false)}>
          <dl className="record-details">
            {fields.map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value ?? '—'}</dd>
              </div>
            ))}
          </dl>
          {children && (
            <div
              className="record-detail-actions"
              onClick={(event) => {
                if ((event.target as HTMLElement).closest('button:not(:disabled)')) setOpen(false);
              }}
            >
              {children}
            </div>
          )}
        </Modal>,
        trigger.current?.closest('.console-root') || document.body
      )}
    </>
  );
}
