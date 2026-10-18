'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, Phone, Send, RefreshCw } from 'lucide-react';
import { api, type ResellerApplication, type ResellerApplicationsSummary } from '@/lib/api';
import { Modal, Pager, errorText, tone, when, type Say } from './ui';
import { MobileRecordDetails } from './MobileRecordDetails';

const PAGE = 50;

type Tab = 'pending' | 'all' | 'approved' | 'rejected';

const TABS: { key: Tab; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'all', label: 'All' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
];

export function ResellerApps({
  say,
  onPendingChange,
}: {
  say: Say;
  onPendingChange?: (count: number) => void;
}) {
  const [tab, setTab] = useState<Tab>('pending');
  const [summary, setSummary] = useState<ResellerApplicationsSummary | null>(null);
  const [rows, setRows] = useState<ResellerApplication[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [review, setReview] = useState<{ app: ResellerApplication; approve: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await api.resellerApplications(tab === 'all' ? undefined : tab, offset, PAGE);
      setRows(result.applications);
      setTotal(result.total);
      if (result.summary) {
        setSummary(result.summary);
        onPendingChange?.(result.summary.pending);
      }
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [tab, offset, onPendingChange, say]);

  useEffect(() => {
    void load();
  }, [load]);

  const choose = (next: Tab) => {
    setTab(next);
    setOffset(0);
  };

  return (
    <>
      <section className="panel queue-panel reseller-requests">
        <header>
          <div className="queue-tabs" aria-label="Reseller request filters">
            {TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={tab === item.key}
                className={tab === item.key ? 'active' : ''}
                onClick={() => choose(item.key)}
              >
                {item.label}
                <span className="count">{summary ? summary[item.key === 'all' ? 'total' : item.key] : null}</span>
              </button>
            ))}
          </div>
          <button type="button" className="mini ghost reseller-refresh" aria-label="Refresh requests" onClick={() => void load()}>
            <RefreshCw size={15} aria-hidden="true" />
          </button>
        </header>
        <div className="app-list-heading"><span>{total} {total === 1 ? 'request' : 'requests'}</span></div>
        <ul className="app-record-list reseller-feed" aria-label="Reseller requests">
          {(rows ?? []).map(app => {
            const tgHandle = app.telegram_handle.replace(/^@/, '');
            const channelUrl = app.channel_link.startsWith('http') ? app.channel_link : app.channel_link.startsWith('@') ? `https://t.me/${app.channel_link.slice(1)}` : `https://${app.channel_link}`;
            return <li key={app.id}>
              <MobileRecordDetails title={app.full_name} subtitle={`@${tgHandle}`} amount="" status={app.status} tone={tone(app.status) || 'neutral'} label={`Review reseller ${app.full_name}`} fields={[
                ['Telegram ID', app.tg_user_id], ['Telegram', <a key="tg" href={`https://t.me/${tgHandle}`} target="_blank" rel="noopener noreferrer">@{tgHandle}</a>],
                ['Phone', app.phone_number], ['Store', <a key="store" href={channelUrl} target="_blank" rel="noopener noreferrer">{app.channel_link}</a>],
                ['Status', app.status], ['Applied', when(app.created_at)], ['Admin note', app.admin_notes || ''],
              ]}>
                {app.status === 'pending' ? <>
                  <button type="button" className="btn" disabled={busy === app.id} onClick={() => setReview({ app, approve: true })}>Approve reseller</button>
                  <button type="button" className="btn ghost danger" disabled={busy === app.id} onClick={() => setReview({ app, approve: false })}>Reject request</button>
                </> : null}
              </MobileRecordDetails>
            </li>;
          })}
          {!rows || !rows.length ? <li className="app-list-empty">{!rows ? 'Loading requests…' : 'No reseller requests in this view.'}</li> : null}
        </ul>
        <div className="scroll desktop-record-scroll">
          <table className="mobile-records reseller-table">
            <thead>
              <tr>
                <th>Applicant</th>
                <th>Contact</th>
                <th>Channel / Store</th>
                <th>Status</th>
                <th className="right" >Actions</th>
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((app) => {
                const tgHandle = app.telegram_handle.replace(/^@/, '');
                const tgUrl = `https://t.me/${tgHandle}`;
                const channelUrl = app.channel_link.startsWith('http')
                  ? app.channel_link
                  : app.channel_link.startsWith('@')
                  ? `https://t.me/${app.channel_link.slice(1)}`
                  : `https://${app.channel_link}`;

                return (
                  <tr key={app.id}>
                    <td className="name">
                      <strong>{app.full_name}</strong>
                      <small>
                        ID: <code>{app.tg_user_id}</code>, {when(app.created_at)}
                      </small>
                    </td>

                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <a
                          href={tgUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none', color: 'inherit' }}
                        >
                          <Send size={13} style={{ opacity: 0.7 }} />
                          <code>@{tgHandle}</code>
                        </a>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.85em', opacity: 0.85 }}>
                          <Phone size={12} style={{ opacity: 0.6 }} />
                          {app.phone_number}
                        </span>
                      </div>
                    </td>

                    <td>
                      <a
                        href={channelUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="button-link"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 5,
                          maxWidth: 260,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={app.channel_link}
                      >
                        <ExternalLink size={13} />
                        <span>{app.channel_link}</span>
                      </a>
                    </td>

                    <td>
                      <span className={`pill ${tone(app.status)}`}>{app.status}</span>
                      {app.admin_notes ? (
                        <small title={app.admin_notes} className="reseller-note">
                          {app.admin_notes}
                        </small>
                      ) : null}
                    </td>

                    <td>
                      {app.status === 'pending' ? (
                        <div className="row-actions">
                          <button
                            type="button"
                            className="mini primary"
                            disabled={busy === app.id}
                            onClick={() => setReview({ app, approve: true })}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="mini danger"
                            disabled={busy === app.id}
                            onClick={() => setReview({ app, approve: false })}
                          >
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}

            </tbody>
          </table>
        </div>
        {!rows || rows.length === 0 ? (
          <p className="reseller-empty" role="status">
            {!rows ? 'Loading requests…' : tab === 'pending'
              ? 'No pending requests. New reseller applications will appear here.'
              : 'No requests in this view.'}
          </p>
        ) : null}
        <Pager total={total} offset={offset} size={PAGE} onChange={setOffset} />
      </section>

      {review ? (
        <ResellerReviewDialog
          review={review}
          onClose={() => setReview(null)}
          onDone={async (message) => {
            setReview(null);
            say(message);
            await load();
          }}
          say={say}
        />
      ) : null}
    </>
  );
}

function ResellerReviewDialog({
  review,
  onClose,
  onDone,
  say,
}: {
  review: { app: ResellerApplication; approve: boolean };
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  say: Say;
}) {
  const { app, approve } = review;
  const [note, setNote] = useState(
    approve ? '' : 'Did not meet eligibility criteria at this time.'
  );
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (approve) {
        await api.approveResellerApplication(app.id, note);
        await onDone(`Approved application for ${app.full_name}. User promoted to Reseller.`);
      } else {
        await api.rejectResellerApplication(app.id, note);
        await onDone(`Rejected application for ${app.full_name}.`);
      }
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={approve ? `Approve Reseller: ${app.full_name}` : `Reject Application: ${app.full_name}`}
      onClose={onClose}
    >
      <form onSubmit={submit} className="stack">
        <div style={{ fontSize: '0.9em', opacity: 0.9, lineHeight: 1.5 }}>
          <div>
            <strong>Applicant:</strong> {app.full_name} (<code>@{app.telegram_handle.replace(/^@/, '')}</code>)
          </div>
          <div>
            <strong>Telegram ID:</strong> <code>{app.tg_user_id}</code>
          </div>
          <div>
            <strong>Phone / WhatsApp:</strong> {app.phone_number}
          </div>
          <div>
            <strong>Channel / Store:</strong>{' '}
            <a href={app.channel_link} target="_blank" rel="noopener noreferrer">
              {app.channel_link}
            </a>
          </div>
        </div>

        {approve ? (
          <p style={{ fontSize: '0.85em', color: 'var(--color-text-muted)' }}>
            Enables reseller prices and notifies the applicant.
          </p>
        ) : (
          <p style={{ fontSize: '0.85em', color: 'var(--color-text-muted)' }}>
            The reason is sent to the applicant.
          </p>
        )}

        <label className="field">
          <span>{approve ? 'Admin Note (Optional)' : 'Rejection Reason'}</span>
          <textarea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={approve ? 'Internal notes or special agreement terms…' : 'Explain why the application was declined…'}
            required={!approve}
          />
        </label>

        <div className="dialog-actions">
          <button type="button" className="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            className={approve ? 'primary' : 'danger'}
            disabled={busy}
          >
            {busy ? 'Processing…' : approve ? 'Approve reseller' : 'Reject request'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
