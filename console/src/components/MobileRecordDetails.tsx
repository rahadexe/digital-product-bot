'use client';

import { useRef, useState, type ComponentProps, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { MobileRecord } from './MobileRecord';
import { Modal } from './ui';

/** Secondary fields and existing actions stay one tap away from a compact row. */
export function MobileRecordDetails({
  fields, children, ...record
}: Omit<ComponentProps<typeof MobileRecord>, 'onOpen'> & {
  fields: [string, ReactNode][];
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);
  return <>
    <div ref={anchor} className="app-detail-trigger">
      <MobileRecord {...record} onOpen={() => setOpen(true)} />
    </div>
    {open && typeof document !== 'undefined' ? createPortal(
      <Modal title={record.title} className="record-drawer" onClose={() => setOpen(false)}>
        <dl className="record-details">
          {fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>)}
        </dl>
        {children ? <div className="app-review-actions" onClick={event => {
          if ((event.target as HTMLElement).closest('button:not(:disabled)')) setOpen(false);
        }}>{children}</div> : null}
      </Modal>, anchor.current?.closest('.console-root') || document.body
    ) : null}
  </>;
}
