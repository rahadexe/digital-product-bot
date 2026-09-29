'use client';

import { useCallback, useEffect, useState } from 'react';
import { Briefcase, CheckCircle2, Clock, XCircle, ExternalLink, Phone, Send } from 'lucide-react';
import { api, type ResellerApplication, type ResellerApplicationsSummary } from '@/lib/api';
import { EmptyRow, Modal, Pager, errorText, tone, when, type Say } from './ui';

const PAGE = 50;

type Tab = 'pending' | 'all' | 'approved' | 'rejected';

const TABS: { key: Tab; label: string }[] = [
  { key: 'pending', label: 'Waiting' },
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
      {/* Metric Summary Cards */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Pending Review</span>
            <Clock className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.pending ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Approved Resellers</span>
            <CheckCircle2 className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.approved ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Rejected</span>
            <XCircle className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.rejected ?? 0}</div>
        </div>

        <div className="stat-card">
          <div className="stat-card-top">
            <span className="stat-card-label">Total Applications</span>
            <Briefcase className="stat-card-icon" />
          </div>
          <div className="stat-card-value">{summary?.total ?? 0}</div>
        </div>
      </div>

      <div className="segmented" role="tablist" aria-label="Reseller applications filter">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={tab === item.key ? 'active' : ''}
            onClick={() => choose(item.key)}
          >
            {item.label}
            {item.key === 'pending' && summary && summary.pending > 0 ? (
              <span className="count" style={{ marginLeft: 6 }}>
                {summary.pending}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <section className="panel">
        <div className="scroll">
          <table className="mobile-records">
            <thead>
              <tr>
                <th>Applicant</th>
                <th>Contact</th>
                <th>Channel / Store</th>
                <th>Status</th>
                <th className="right" aria-label="Actions" />
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
                        ID: <code>{app.tg_user_id}</code> · {when(app.created_at)}
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
                        <small title={app.admin_notes} style={{ display: 'block', marginTop: 3 }}>
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

              {rows && rows.length === 0 ? (
                <EmptyRow columns={5}>
                  {tab === 'pending' ? 'No pending reseller applications.' : 'No applications found.'}
                </EmptyRow>
              ) : null}
              {!rows ? <EmptyRow columns={5}>Loading…</EmptyRow> : null}
            </tbody>
          </table>
        </div>
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
            Approving this application will automatically upgrade the user&apos;s rank to <b>Reseller</b>, enabling wholesale prices and API key generation. A confirmation message will be sent to the applicant via Telegram.
          </p>
        ) : (
          <p style={{ fontSize: '0.85em', color: 'var(--color-text-muted)' }}>
            Please state the reason for rejecting this application. This reason will be shared with the applicant via Telegram so they understand what is needed.
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
            {busy ? 'Processing…' : approve ? 'Confirm & Upgrade to Reseller' : 'Confirm Rejection'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
